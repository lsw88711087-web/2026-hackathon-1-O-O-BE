"""크롤링 CSV를 seed_demo가 읽는 fixtures/demo.json으로 변환한다.

**CSV 행 순서가 곧 진열 순서다.** 배포된 "60개 목록" PDF의 `전시존-상품` 번호가
CSV 행 순서와 1:1로 맞는 것을 확인하고 그대로 쓴다(9·9·9·18·6·6·3 = 60).
순서가 바뀐 CSV를 받으면 이 가정부터 다시 확인해야 한다.

CSV에는 취향 분석 축 8개가 없다. 이름·소재·가격에서 규칙으로 뽑는다. 규칙이 여기
한곳에 모여 있어야 "왜 이 상품이 미니멀인가"를 나중에 되짚을 수 있다.
"""

import csv
import html
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

DEFAULT_CSV = "mcm_60.csv"
FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo.json"

STORE = {"id": "s_mcm", "name": "MCM 스토어"}

# PDF의 전시존 구성. 합이 CSV 행 수와 다르면 매칭이 어긋난 것이므로 중단한다.
SCENES = (
    ("sc_01", 1, "토트백", 9),
    ("sc_02", 2, "백팩", 9),
    ("sc_03", 3, "쇼퍼백", 9),
    ("sc_04", 4, "악세서리", 18),
    ("sc_05", 5, "여성의류", 6),
    ("sc_06", 6, "남성의류", 6),
    ("sc_07", 7, "F/W 신상", 3),
)

# 상품 이미지는 CSV의 `cutout_image`(1-Photoroom.png)를 쓴다. 우리가 직접 준비한
# 배경 제거 PNG다.
#
# MCM CDN URL(`images` 컬럼)을 쓰지 않는 이유는 남의 서버에 의존하기 때문이다.
# 핫링크가 막히거나 상품이 내려가면 데모 당일 이미지가 통째로 사라진다.
#
# ⚠️ 이 PNG 60개를 어딘가에 올려야 화면에 뜬다. 어디에 두느냐로 경로가 갈린다.
#
#   프론트(Netlify) public/media/products/  → 상대 경로 그대로. --base-url 없이 실행
#   백엔드 MEDIA_ROOT/products/             → --base-url https://hello1423.site
#
# 상대 경로는 브라우저가 **페이지 주소 기준**으로 푼다. 프론트가 Netlify라 백엔드에
# 파일을 두면서 상대 경로로 내려보내면 Netlify에서 파일을 찾다가 404가 난다.
PRODUCT_IMAGE_PATH = "/media/products/"

# CSV 색상 → 분석 축 색상. 축은 9개로 고정이라 그 밖의 색은 가장 가까운 값으로 접는다.
# 원본 색상명("lotus pink", "khaki moss")은 attributes.color에 그대로 남긴다.
COLOR_MAP = {
    "black": "black",
    "white": "white",
    "cognac": "cognac",
    "beige": "beige",
    "red": "red",
    "pink": "pink",
    "blue": "navy",
    "brown": "cognac",
    "gold": "metallic",
    "orange": "red",
    "dark grey": "black",
    "green": "beige",  # khaki moss 1건. 축에 초록이 없어 가장 가까운 값으로 접는다
}

WALLET_WORDS = ("지갑", "카드홀더", "카드 홀더", "카드케이스", "카드 케이스")

MATERIAL_RULES = (
    ("비세토스", "coated_canvas"),
    ("코티드", "coated_canvas"),
    ("나파", "smooth_leather"),
    ("엠보스드", "grained_leather"),
    ("그레인", "grained_leather"),
    ("econyl", "nylon"),
    ("나일론", "nylon"),
    ("스웨이드", "suede"),
)

MOOD_RULES = (
    ("디스코", "bold_statement"),
    ("시퀸", "bold_statement"),
    ("루렉스", "bold_statement"),
    ("스터드", "bold_statement"),
    ("별자리", "y2k_street"),
    ("불독", "y2k_street"),
    ("닥스훈트", "y2k_street"),
    ("래빗", "y2k_street"),
    ("애니멀", "y2k_street"),
    ("비세토스", "classic_heritage"),
    ("모노그램", "classic_heritage"),
    ("로레토스", "classic_heritage"),
)


class Command(BaseCommand):
    help = "크롤링 CSV를 fixtures/demo.json으로 변환한다 (적재는 seed_demo가 한다)."

    def add_arguments(self, parser):
        parser.add_argument("--csv", default=DEFAULT_CSV, help="입력 CSV 경로")
        parser.add_argument("--out", default=str(FIXTURE), help="출력 JSON 경로")
        parser.add_argument(
            "--base-url",
            default="",
            help="상품 이미지 앞에 붙일 호스트. 백엔드에 파일을 둘 때만 쓴다 "
            "(예: https://hello1423.site). 비우면 상대 경로 - 프론트가 같은 곳에서 서빙할 때.",
        )

    def handle(self, *args, **options):
        rows = self._read(Path(options["csv"]))
        expected = sum(count for *_, count in SCENES)
        if len(rows) != expected:
            raise CommandError(
                f"CSV {len(rows)}행인데 전시존 정원은 {expected}입니다. 매칭 가정이 깨졌습니다."
            )

        base_url = options["base_url"].rstrip("/")
        scenes, cursor = [], 0
        for scene_id, scene_no, scene_name, count in SCENES:
            # id·no는 전시존 안에서 매긴다. 기존 DB가 쓰던 체계라 같은 규칙을 지켜야
            # 행이 새로 생기지 않고 제자리에서 갱신된다.
            products = [
                self._product(row, index, scene_no, base_url)
                for index, row in enumerate(rows[cursor : cursor + count], start=1)
            ]
            scenes.append({"id": scene_id, "no": scene_no, "name": scene_name, "products": products})
            cursor += count

        payload = {
            "_comment": "import_products_csv가 생성한다. 직접 고치지 말고 CSV를 고친 뒤 다시 돌릴 것.",
            "store": STORE,
            "scenes": scenes,
        }
        out = Path(options["out"])
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        total = sum(len(scene["products"]) for scene in scenes)
        where = base_url or "상대 경로(프론트가 서빙)"
        self.stdout.write(self.style.SUCCESS(f"{out} 생성: 전시존 {len(scenes)}개 · 상품 {total}개"))
        self.stdout.write(f"상품 이미지 위치: {where}{PRODUCT_IMAGE_PATH}")

    def _read(self, path: Path) -> list[dict]:
        if not path.exists():
            raise CommandError(f"CSV가 없습니다: {path}")
        text = path.read_bytes().decode("utf-8-sig")
        return list(csv.DictReader(text.splitlines()))

    def _product(self, row: dict, no: int, scene_no: int, base_url: str) -> dict:
        name = clean(row["name"])
        price = int(row["price_krw"])
        category = self._category(name, scene_no)
        cutout = row["cutout_image"].strip()
        image_url = base_url + PRODUCT_IMAGE_PATH + cutout if cutout else ""
        return {
            "id": f"p_{scene_no}{no:02d}",
            "no": no,
            "name": name,
            "price": price,
            "external_url": row["url"].strip(),
            "story": clean(row["summary"]),
            "images": [image_url] if image_url else [],
            "cutout_url": image_url,
            "is_new": scene_no == 7,
            "attributes": {
                "color": clean(row["color"]),
                "material": clean(row["material"]),
                "dimensions": clean(row["dimensions"]),
                "size": clean(row["size"]),
                "lining": clean(row["lining"]),
                "origin": clean(row["origin"]),
                "collection": clean(row["collection"]),
                "availability": clean(row["availability"]),
                "sku": row["product_id"].strip(),
            },
            "preset_answers": self._presets(row, price),
            "llm_context": self._context(row, name),
            "category": category,
            "color": COLOR_MAP.get(row["color"].strip().lower(), "black"),
            "material": self._material(row),
            "pattern": self._pattern(row, name),
            "silhouette": self._silhouette(name, row, category),
            "mood": self._mood(name, row),
            "price_band": self._price_band(price),
            "use_case": self._use_case(category),
        }

    def _presets(self, row: dict, price: int) -> dict:
        """상품을 누르면 뜨는 버튼 3개의 답변. LLM이 아니라 미리 써둔 문구다."""
        material = clean(row["material"])
        lining = clean(row["lining"])
        origin = clean(row["origin"])
        stock = "품절 상태예요." if "품절" in row["availability"] else "지금 구매하실 수 있어요."
        material_parts = [
            f"{material}로 만들었어요." if material else "",
            f"안감은 {lining}입니다." if lining else "",
            f"{origin}에서 제작했어요." if origin else "",
        ]
        return {
            "price": f"{price:,}원입니다. {stock}",
            "material": " ".join(part for part in material_parts if part),
            "design_intent": clean(row["summary"]) or clean(row["description"])[:120],
        }

    def _context(self, row: dict, name: str) -> str:
        """챗봇이 읽는 근거 문단. 사람이 읽을 문장으로 이어 붙인다."""
        features = " ".join(f"{item.strip()}." for item in row["features"].split("|") if item.strip())
        material = clean(row["material"])
        lining = clean(row["lining"])
        dimensions = clean(row["dimensions"])
        parts = [
            f"{name}.",
            clean(row["summary"]),
            clean(row["description"]),
            f"소재는 {material}이고 안감은 {lining}입니다." if material else "",
            f"크기는 {dimensions}입니다." if dimensions else "",
            clean(features),
        ]
        return " ".join(part for part in parts if part).strip()

    def _category(self, name: str, scene_no: int) -> str:
        if scene_no in (5, 6):
            return "clothing"
        if scene_no == 4:
            # "카드"만 보면 "로레토스 자카드 스카프"가 지갑이 된다. 한국어는 부분문자열이
            # 이렇게 겹치므로 지갑을 가리키는 낱말을 통째로 본다.
            return "wallet" if any(word in name for word in WALLET_WORDS) else "accessory"
        if "백팩" in name:
            return "backpack"
        if "보스턴" in name:
            return "shoulder"
        if "크로스" in name:
            return "crossbody"
        return "tote"

    def _material(self, row: dict) -> str:
        text = (row["material"] + " " + row["name"]).lower()
        for needle, value in MATERIAL_RULES:
            if needle in text:
                return value
        return "mixed"

    def _pattern(self, row: dict, name: str) -> str:
        text = (row["material"] + " " + name).lower()
        if "비세토스" in text or "로레토스" in text:
            return "visetos_monogram"
        if "스터드" in text:
            return "studded"
        if "모노그램" in text or "로고" in text or "m50" in text:
            return "logo_print"
        return "solid"

    def _silhouette(self, name: str, row: dict, category: str) -> str:
        if "미니" in row["size"] or "참" in name or "스카프" in name:
            return "compact"
        if "드로우스트링" in name:
            return "slouchy"
        if category == "clothing":
            return "structured" if ("재킷" in name or "팬츠" in name) else "slouchy"
        if "쇼퍼" in name:
            return "boxy"
        return "structured"

    def _mood(self, name: str, row: dict) -> str:
        text = (name + " " + row["material"] + " " + row["collection"]).lower()
        for needle, value in MOOD_RULES:
            if needle in text:
                return value
        return "minimal"

    def _price_band(self, price: int) -> str:
        if price < 600_000:
            return "entry"
        return "mid" if price <= 1_200_000 else "high"

    def _use_case(self, category: str) -> str:
        if category in ("accessory", "wallet"):
            return "going_out"
        if category in ("clothing", "backpack"):
            return "daily"
        if category == "shoulder":
            return "travel"
        return "work"


def clean(value: str) -> str:
    """CSV에 &reg; &lsquo; 같은 HTML 엔티티가 그대로 들어 있다."""
    return html.unescape((value or "").strip())
