"""취향 좌표 계산.

축값은 **누적이 아니라 함수**다. 같은 입력(관심 상품 집합 + 회피 데이터)에서 항상
같은 결과가 나오므로 저장하지 않는다. 방문 중 화면에 보여줄 때와 퇴장 후 워커가
확정할 때 같은 함수를 돌린다. 그래서 행동 점수가 이중 계산될 여지가 없다.

저장하는 것은 events에 없는 것들뿐이다 — 손님이 확인·발화로 준 답(TasteProfile.vector).
"""

from dataclasses import dataclass, field

from django.db.models import Count

from apps.analysis.models import TasteProfile
from apps.catalog.models import Color, Mood, Pattern, Product, UseCase
from apps.events.models import EventType
from apps.visits.models import Visit

# 관심 상품 집합 진입 기준. 질문 트리거(30초)보다 낮다 —
# 질문은 더 강한 신호일 때만 던지고, 데이터는 더 넓게 모은다.
INTEREST_DWELL_MS = 20_000
REVISIT_COUNT = 2

SHRINKAGE = 2  # 축값 = 비율 × n/(n+SHRINKAGE). 표본 1개가 1.0이 되는 것을 막는다
CAMP_GAP = 0.25  # 진영 격차가 이보다 작으면 "그 축은 안 가린다"
# 유효성은 비율만 보므로 표본 크기가 반영되지 않는다. 집합이 1개면 그 축은 항상
# 격차 1.0이 되어 상품 하나로 4축이 전부 확정된다. 그래서 최소 크기를 따로 둔다.
MIN_INTEREST_FOR_AXIS = 3

# 16유형 4축. 각 축은 두 진영의 대결이다.
CAMPS: dict[str, dict[str, tuple[str, ...]]] = {
    "mood": {
        "C": (Mood.CLASSIC_HERITAGE, Mood.MINIMAL),
        "T": (Mood.Y2K_STREET, Mood.BOLD_STATEMENT),
    },
    "color": {
        # cognac(갈색)은 차분한 계열이다. 빠뜨렸더니 코냑을 많이 본 손님이
        # "눈에 띄는 색"으로 판정됐다 — 진영에 없는 값은 조용히 반대편을 이롭게 한다.
        "N": (Color.BLACK, Color.WHITE, Color.COGNAC, Color.BEIGE, Color.NAVY),
        "V": (Color.RED, Color.PINK, Color.METALLIC, Color.VISETOS_MIX),
    },
    "pattern": {
        "P": (Pattern.SOLID, Pattern.LOGO_PRINT),
        "O": (Pattern.VISETOS_MONOGRAM, Pattern.STUDDED),
    },
    "use_case": {
        "D": (UseCase.DAILY, UseCase.WORK),
        "S": (UseCase.TRAVEL, UseCase.GOING_OUT),
    },
}
CORE_AXES = tuple(CAMPS)
# 추천 스코어링에 쓰는 축과 가중치. 손님이 말하는 감각에 가까운 축을 무겁게 본다.
AXIS_WEIGHTS = {
    "mood": 3,
    "color": 3,
    "material": 2,
    "use_case": 2,
    "pattern": 1,
    "silhouette": 1,
    "price_band": 1,
}
ALL_AXES = tuple(AXIS_WEIGHTS)


@dataclass
class Taste:
    """한 방문의 취향 좌표. 화면·추천·리포트가 모두 이 객체를 본다."""

    values: dict[str, dict[str, float]] = field(default_factory=dict)  # 축 → 값 → 점수
    ratios: dict[str, dict[str, float]] = field(default_factory=dict)  # 보정 전 비율
    locks: dict[str, str] = field(default_factory=dict)  # 축 → 손님이 확정한 값
    valid_axes: tuple[str, ...] = ()
    interest_size: int = 0

    def score(self, axis: str, value: str) -> float:
        return self.values.get(axis, {}).get(value, 0.0)

    def camp_of(self, axis: str) -> str | None:
        """그 축에서 우세한 진영. 무효 축이면 None(판정 보류)."""
        if axis not in self.valid_axes:
            return None
        sums = _camp_sums(self.ratios.get(axis, {}), axis, self.locks.get(axis))
        winner = max(sums, key=lambda camp: sums[camp])
        return winner

    @property
    def confidence(self) -> float:
        """유효 축 개수 + lock 개수 + 집합 크기. 셋 다 적으면 "탐색 중"이 된다."""
        axes = len(self.valid_axes) / len(CORE_AXES)
        locked = min(1.0, len(self.locks) / 2)
        volume = min(1.0, self.interest_size / 6)
        return round(0.5 * axes + 0.2 * locked + 0.3 * volume, 2)


def profile_of(visit: Visit) -> TasteProfile:
    profile, _ = TasteProfile.objects.get_or_create(visit=visit, defaults={"vector": {}})
    return profile


def read(visit: Visit) -> Taste:
    """지금까지의 좌표를 계산한다."""
    stored = profile_of(visit).vector
    locks = {**stored.get("spoken", {}), **stored.get("locks", {})}
    avoided = stored.get("avoided", {})
    products = interest_products(visit, stored)

    taste = Taste(locks=locks, interest_size=len(products))
    for axis in ALL_AXES:
        ratios = _ratios(products, axis)
        taste.ratios[axis] = ratios
        taste.values[axis] = _values(ratios, len(products), avoided.get(axis, {}), locks.get(axis))
    taste.valid_axes = tuple(a for a in CORE_AXES if _is_valid(taste, a))
    return taste


def interest_products(visit: Visit, stored: dict | None = None) -> list[Product]:
    """관심 상품 집합. 여러 상품의 공통점이 곧 취향이다."""
    stored = stored if stored is not None else profile_of(visit).vector
    ids = _behaviour_ids(visit) | set(stored.get("confirmed", []))
    ids -= set(stored.get("rejected", []))
    return list(Product.objects.filter(id__in=ids))


def _behaviour_ids(visit: Visit) -> set[str]:
    events = visit.events.filter(product__isnull=False)
    ids = set(events.filter(event_type=EventType.PRODUCT_SAVE).values_list("product_id", flat=True))
    ids |= {
        row["product_id"]
        for row in events.filter(event_type=EventType.PRODUCT_VIEW)
        .values("product_id")
        .annotate(n=Count("event_id"))
        if row["n"] >= REVISIT_COUNT
    }
    ids |= {
        event.product_id
        for event in events.filter(event_type=EventType.PRODUCT_DWELL)
        if event.metadata.get("dwell_ms", 0) >= INTEREST_DWELL_MS
    }
    return ids


def _ratios(products: list[Product], axis: str) -> dict[str, float]:
    if not products:
        return {}
    counts: dict[str, int] = {}
    for product in products:
        # 빈 축은 "이 값이다"가 아니라 "아직 모른다"는 뜻이다. 상품 데이터가 덜 채워진
        # 단(악세서리·의류)이 있어 실제로 절반 가까이 비어 있는데, 이걸 하나의 값으로
        # 세면 취향 벡터에 ''가 최빈값으로 남는다. 분모는 그대로 둬서 근거가 적을수록
        # 비율이 낮게 나오게 한다 — 단서가 적으면 판정을 보류하는 쪽이 맞다.
        value = getattr(product, axis)
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return {value: count / len(products) for value, count in counts.items()}


def _values(ratios: dict[str, float], size: int, avoided: list[str], locked: str | None) -> dict[str, float]:
    shrink = size / (size + SHRINKAGE) if size else 0.0
    values = {value: ratio * shrink for value, ratio in ratios.items()}
    for value in avoided:
        values[value] = values.get(value, 0.0) - 1.0
    if locked:
        values[locked] = 1.0  # 손님이 직접 답한 축은 행동이 흔들지 못한다
    return values


def _camp_sums(ratios: dict[str, float], axis: str, locked: str | None) -> dict[str, float]:
    sums = {}
    for camp, members in CAMPS[axis].items():
        total = sum(ratios.get(value, 0.0) for value in members)
        if locked in members:
            total += 1.0
        sums[camp] = total
    return sums


def _is_valid(taste: Taste, axis: str) -> bool:
    """진영 격차로 판정한다.

    값 단위(top1 − top2)로 보면 "black 0.3 · navy 0.3 · pink 0.3"이 무효로 나온다.
    무채색을 두 종류나 골랐는데 "색을 안 가린다"는 건 틀린 판정이다.
    """
    if axis in taste.locks:
        return True  # 손님이 직접 답했으면 표본 크기와 무관하게 유효하다
    if taste.interest_size < MIN_INTEREST_FOR_AXIS:
        return False
    sums = _camp_sums(taste.ratios.get(axis, {}), axis, None)
    ordered = sorted(sums.values(), reverse=True)
    return len(ordered) >= 2 and (ordered[0] - ordered[1]) >= CAMP_GAP


def character_code(taste: Taste) -> str:
    """16유형 코드. 무효 축은 소문자로 표시해 "판정 보류"를 드러낸다."""
    code = ""
    for axis in CORE_AXES:
        camps = tuple(CAMPS[axis])
        camp = taste.camp_of(axis)
        code += camp if camp else camps[0].lower()
    return code


def missing_camp_values() -> dict[str, list[str]]:
    """진영에 빠진 축 값을 찾는다.

    값이 어느 진영에도 없으면 그 값을 고른 손님이 조용히 반대 진영으로 분류된다.
    에러도 안 나고 결과만 틀리므로 기동 시 검사한다(apps.py의 system check).
    """
    from apps.catalog.models import Color, Mood, Pattern, UseCase

    enums = {"mood": Mood, "color": Color, "pattern": Pattern, "use_case": UseCase}
    missing = {}
    for axis, enum in enums.items():
        covered = {value for members in CAMPS[axis].values() for value in members}
        gap = [value for value in enum.values if value not in covered]
        if gap:
            missing[axis] = gap
    return missing
