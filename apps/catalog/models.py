"""매장 · 전시존 · 상품.

취향 분석에 쓰는 8개 축은 JSON이 아니라 컬럼으로 둔다. SQLite에서는 JSON 내부
값으로 group by·집계를 하기가 매우 아프고, /admin/cohorts가 색상·소재별 분포를
뽑아야 하기 때문이다.
"""

from django.db import models

from common.ids import gen_id


def new_store_id() -> str:
    return gen_id("s")


def new_scene_id() -> str:
    return gen_id("sc")


def new_product_id() -> str:
    return gen_id("p")


class Category(models.TextChoices):
    BACKPACK = "backpack", "백팩"
    TOTE = "tote", "토트백"
    CROSSBODY = "crossbody", "크로스백"
    SHOULDER = "shoulder", "숄더백"
    WALLET = "wallet", "지갑"
    ACCESSORY = "accessory", "액세서리"
    # 5·6단이 의류다. 가방만 있는 분류로는 15개 상품이 어디에도 못 들어간다.
    CLOTHING = "clothing", "의류"


class Color(models.TextChoices):
    BLACK = "black", "블랙"
    WHITE = "white", "화이트"
    COGNAC = "cognac", "코냑"
    BEIGE = "beige", "베이지"
    NAVY = "navy", "네이비"
    RED = "red", "레드"
    PINK = "pink", "핑크"
    METALLIC = "metallic", "메탈릭"
    VISETOS_MIX = "visetos_mix", "비세토스 배색"


class Material(models.TextChoices):
    COATED_CANVAS = "coated_canvas", "코팅 캔버스"
    SMOOTH_LEATHER = "smooth_leather", "스무스 레더"
    GRAINED_LEATHER = "grained_leather", "그레인 레더"
    NYLON = "nylon", "나일론"
    SUEDE = "suede", "스웨이드"
    MIXED = "mixed", "혼합"


class Pattern(models.TextChoices):
    VISETOS_MONOGRAM = "visetos_monogram", "비세토스 모노그램"
    LOGO_PRINT = "logo_print", "로고 프린트"
    SOLID = "solid", "솔리드"
    STUDDED = "studded", "스터드"


class Silhouette(models.TextChoices):
    STRUCTURED = "structured", "구조적"
    SLOUCHY = "slouchy", "슬라우치"
    BOXY = "boxy", "박시"
    COMPACT = "compact", "컴팩트"


class Mood(models.TextChoices):
    CLASSIC_HERITAGE = "classic_heritage", "클래식 헤리티지"
    MINIMAL = "minimal", "미니멀"
    Y2K_STREET = "y2k_street", "Y2K 스트리트"
    BOLD_STATEMENT = "bold_statement", "볼드 스테이트먼트"


class PriceBand(models.TextChoices):
    ENTRY = "entry", "60만원 미만"
    MID = "mid", "60~120만원"
    HIGH = "high", "120만원 초과"


class UseCase(models.TextChoices):
    DAILY = "daily", "데일리"
    WORK = "work", "출근"
    TRAVEL = "travel", "여행"
    GOING_OUT = "going_out", "나들이·모임"


class PresetKey(models.TextChoices):
    """상품을 클릭하면 뜨는 프리셋 버튼. LLM 생성이 아니라 미리 작성해 둔 문구다."""

    PRICE = "price", "가격"
    MATERIAL = "material", "재질"
    DESIGN_INTENT = "design_intent", "디자인 의도"


# 취향 분석의 축 8개. 값 목록의 진실은 위 TextChoices이고, 이 표가 그것을 가리킨다.
# 분석·시드·리포트 키워드가 모두 이 표를 통해 축을 돈다.
ANALYSIS_AXES: dict[str, type[models.TextChoices]] = {
    "category": Category,
    "color": Color,
    "material": Material,
    "pattern": Pattern,
    "silhouette": Silhouette,
    "mood": Mood,
    "price_band": PriceBand,
    "use_case": UseCase,
}


def axis_label(axis: str, value: str) -> str:
    """축 값의 한국어 라벨. 리포트의 취향 키워드가 "black"이 아니라 "블랙"이어야 한다."""
    return dict(ANALYSIS_AXES[axis].choices).get(value, value)


class Store(models.Model):
    id = models.CharField(primary_key=True, max_length=32, default=new_store_id, editable=False)
    name = models.CharField(max_length=100)
    # 뮤즈 번호(N.014) 발급용 카운터. 마지막으로 나간 번호를 들고 있다.
    muse_counter = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.name


class Scene(models.Model):
    """전시존(매대). 좌표·도면은 갖지 않는다 — 맵은 프론트가 직접 만든다."""

    id = models.CharField(primary_key=True, max_length=32, default=new_scene_id, editable=False)
    store = models.ForeignKey(Store, related_name="scenes", on_delete=models.CASCADE)
    no = models.PositiveSmallIntegerField()  # 챗봇이 "1번 진열대"로 안내하는 데 쓴다
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["no"]
        constraints = [models.UniqueConstraint(fields=["store", "no"], name="uniq_store_scene_no")]

    def __str__(self) -> str:
        return f"{self.no}번 진열대 {self.name}"


class Product(models.Model):
    id = models.CharField(primary_key=True, max_length=32, default=new_product_id, editable=False)
    scene = models.ForeignKey(Scene, related_name="products", on_delete=models.PROTECT)
    no = models.PositiveSmallIntegerField()  # 전시존 안에서의 번호
    name = models.CharField(max_length=200)
    price = models.PositiveIntegerField()
    external_url = models.URLField(max_length=2048)  # 리포트의 '구매하기' → 본사 사이트
    story = models.TextField()
    images = models.JSONField(default=list)
    # 배경을 제거한 상품 PNG. 화보 합성에 쓴다. 생성 시점에 배경 제거를 돌리면
    # 대기시간이 몇 배가 되므로 상품 데이터 준비 단계에서 미리 만들어 둔다.
    # external_url과 같은 이유로 2048이다. CDN 컷아웃 주소는 200자를 쉽게 넘고,
    # 넘치면 seed_demo 전체가 DataError로 롤백된다.
    cutout_url = models.URLField(max_length=2048, blank=True)

    category = models.CharField(max_length=20, choices=Category.choices)
    color = models.CharField(max_length=20, choices=Color.choices)
    material = models.CharField(max_length=20, choices=Material.choices)
    pattern = models.CharField(max_length=20, choices=Pattern.choices)
    silhouette = models.CharField(max_length=20, choices=Silhouette.choices)
    mood = models.CharField(max_length=20, choices=Mood.choices)
    price_band = models.CharField(max_length=10, choices=PriceBand.choices)
    use_case = models.CharField(max_length=20, choices=UseCase.choices)
    is_new = models.BooleanField(default=False)  # 추천 점수의 신상품 10%

    attributes = models.JSONField(default=dict)  # 화면 표기용 색상·소재·크기·수납력
    preset_answers = models.JSONField(default=dict)  # PresetKey -> 문구
    llm_context = models.TextField()  # 챗봇 프롬프트용. 응답에 절대 내려주지 않는다

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["scene__no", "no"]
        constraints = [models.UniqueConstraint(fields=["scene", "no"], name="uniq_scene_product_no")]

    def __str__(self) -> str:
        return self.name

    @property
    def thumbnail(self) -> str | None:
        return self.images[0] if self.images else None
