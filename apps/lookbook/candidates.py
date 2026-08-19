"""화보 후보 6개를 뽑는다. DB 읽기는 여기까지고, 점수 계산은 scoring.py가 한다.

이 API는 **DB만 읽는다.** 워커도 스토리지도 이미지 생성 API도 쓰지 않아서
화보 기능 중 가장 먼저 만들 수 있다.
"""

from django.db.models import Count

from apps.analysis.models import Report
from apps.catalog.models import ANALYSIS_AXES, Product, axis_label
from apps.events.models import Event, EventType
from apps.lookbook import scoring
from apps.lookbook.scoring import ProductSignals, ScoredCandidate
from apps.visits.models import Visit

DWELL_KEY = "dwell_ms"
PREFERENCE_TAGS_KEY = "preference_tags"
AVOID_TAGS_KEY = "avoid_tags"


def build(report: Report, request) -> dict:
    """P01 응답 본문. items는 항상 정확히 6개다.

    request를 받는 이유는 이미지 URL을 절대 주소로 내보내기 위해서다 — 프론트가
    다른 도메인이라 상대 경로를 주면 자기 사이트에서 찾다가 404가 난다.
    """
    visit = report.visit
    products = list(Product.objects.select_related("scene"))
    signals = _collect_signals(visit, products)

    scored = [scoring.score(product.id, signals[product.id]) for product in products]
    fillers = _fillers(products, signals)
    ranked = scoring.rank(scored, fillers)

    products_by_id = {product.id: product for product in products}
    items = [_item(products_by_id[item.product_id], item, request) for item in ranked]

    return {
        "max_select": scoring.MAX_SELECT,
        "min_select": scoring.MIN_SELECT,
        # 1순위를 미리 골라둔다. 6칸 중 무엇을 눌러야 할지 헤매지 않게 하는 장치다.
        "preselected": [items[0]["product_id"]] if items else [],
        "items": items,
    }


def _collect_signals(visit: Visit, products: list[Product]) -> dict[str, ProductSignals]:
    dwell, views = _behaviour(visit)
    mentions = _chat_mentions(visit)
    prefer_tags, avoid_tags = _tags(visit)
    popularity = _popularity()

    signals = {}
    for product in products:
        values = {getattr(product, axis) for axis in ANALYSIS_AXES}
        signals[product.id] = ProductSignals(
            dwell_ms=dwell.get(product.id, 0),
            views=views.get(product.id, 0),
            chat_mentions=mentions.get(product.id, 0),
            matched_tags=len(values & prefer_tags),
            avoided_tags=len(values & avoid_tags),
            is_new=product.is_new,
            popularity=popularity.get(product.id, 0.0),
        )
    return signals


def _behaviour(visit: Visit) -> tuple[dict[str, int], dict[str, int]]:
    """체류시간 합과 조회 횟수. 이벤트는 한 번만 읽고 두 값을 함께 만든다."""
    dwell: dict[str, int] = {}
    views: dict[str, int] = {}
    rows = visit.events.filter(product__isnull=False).values_list("event_type", "product_id", "metadata")

    for event_type, product_id, metadata in rows:
        if event_type == EventType.PRODUCT_VIEW:
            views[product_id] = views.get(product_id, 0) + 1
        elif event_type == EventType.PRODUCT_DWELL:
            dwell[product_id] = dwell.get(product_id, 0) + _dwell_of(metadata)
    return dwell, views


def _dwell_of(metadata: dict) -> int:
    value = metadata.get(DWELL_KEY, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _chat_mentions(visit: Visit) -> dict[str, int]:
    rows = (
        visit.chat_logs.filter(product__isnull=False).values("product_id").annotate(count=Count("message_id"))
    )
    return {row["product_id"]: row["count"] for row in rows}


def _tags(visit: Visit) -> tuple[set[str], set[str]]:
    """AI가 뽑아 리포트에 박제한 선호·비선호 태그.

    대화가 없던 방문은 두 값이 비어 있고, 그러면 행동 신호만으로 순위가 정해진다.
    후보 6개는 그래도 항상 채워진다.
    """
    payload = visit.report.payload if hasattr(visit, "report") else {}
    return _tag_set(payload.get(PREFERENCE_TAGS_KEY)), _tag_set(payload.get(AVOID_TAGS_KEY))


def _tag_set(value) -> set[str]:
    return {str(tag) for tag in value} if isinstance(value, list) else set()


def _popularity() -> dict[str, float]:
    """전체 방문 기준 조회 인기도. 후보가 부족할 때 자리를 채우는 데만 쓴다."""
    rows = (
        Event.objects.filter(event_type=EventType.PRODUCT_VIEW, product__isnull=False)
        .values("product_id")
        .annotate(count=Count("event_id"))
    )
    counts = {row["product_id"]: row["count"] for row in rows}
    peak = max(counts.values(), default=0)
    if peak == 0:
        return {}
    return {product_id: round(count / peak, 4) for product_id, count in counts.items()}


def _fillers(products: list[Product], signals: dict[str, ProductSignals]) -> list[ScoredCandidate]:
    """신호가 없는 상품을 인기순으로 세운 예비 명단. 점수는 0으로 둔다."""
    ordered = sorted(
        products,
        key=lambda product: (-signals[product.id].popularity, product.id),
    )
    return [
        ScoredCandidate(product_id=product.id, score=0.0, reason_code=scoring.ReasonCode.POPULAR)
        for product in ordered
    ]


def _item(product: Product, scored: ScoredCandidate, request) -> dict:
    return {
        "product_id": product.id,
        "name": product.name,
        "category": axis_label("category", product.category),
        "thumbnail": request.build_absolute_uri(product.thumbnail) if product.thumbnail else None,
        "cutout_url": request.build_absolute_uri(product.cutout_url) if product.cutout_url else "",
        "score": scored.score,
        "reason_code": scored.reason_code,
        "reason": scored.reason,
    }
