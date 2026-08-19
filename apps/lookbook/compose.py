"""화보 마감. AI가 만든 사진을 전면에 깔고 그 위에 타이포와 캡션을 얹는다.

**사진을 상자에 가두지 않는다.** 예전에는 회색 판 위에 사진을 네모로 붙였는데
잘린 자국이 그대로 보여 화보가 아니라 콜라주처럼 보였다. 지금은 사진이 화면을
가득 채우고 타이포만 그 위에 떠 있다.

**타이포는 그리지 않고 오려 쓴다.** 기획 시안의 MCM 레터링은 찢긴 종이 질감이라
폰트로는 재현이 안 된다. 시안에서 밝기로 키잉해 뽑아둔 typography.png를 그대로 올린다.
반면 캡션(N.011)은 방문마다 값이 달라 오릴 수 없으므로 폰트로 그린다.

**글자를 AI에게 맡기지 않는 이유**는 명세와 같다 — 이미지 모델은
"AUTUMN/WINTER 2026"을 "AUTUNM/WNTER 2O26"으로 그린다.
"""

import io
from pathlib import Path

from django.conf import settings
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# 누끼 경계를 살짝 흐려 잘라낸 티를 줄인다. MediaPipe 실루엣은 가장자리가 거칠다.
CUTOUT_FEATHER_PX = 2

# 시안에서 오려낸 레터링. 없으면 폰트로 흉내 낸다.
TYPOGRAPHY_NAME = "typography.png"
BRAND_TEXT = "MCM"
SIDE_TEXT = "50 YEARS OF MCM: THE F/W 2026 COLLECTION"

CAPTION_LEFT = 0.06
CAPTION_BOTTOM = 0.055
# 캡션이 밝은 사진 위에서 묻히지 않도록 아래쪽에 어둠을 깐다.
SCRIM_TOP = 0.72
SCRIM_ALPHA = 150

# 누끼 모드에서만 쓴다. AI 경로는 상품이 이미 인물에 들려 있어 따로 얹지 않는다.
PRODUCT_BOX = (0.60, 0.58, 0.96, 0.86)

# 서버에 어떤 폰트가 깔려 있을지 모른다. 없으면 Pillow 내장 폰트로 떨어진다 —
# 글자가 안 나오는 것보다 낫다.
FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
)


def build(*, person: bytes, product: bytes | None, caption: dict, size: tuple[int, int]) -> bytes:
    """최종 화보 PNG. person이 화면을 채우고 타이포·캡션이 그 위에 얹힌다."""
    width, height = size
    canvas = _cover(person, width, height)

    if product:
        _paste_contain(canvas, product, _box(PRODUCT_BOX, width, height))

    _draw_scrim(canvas, width, height)
    canvas.alpha_composite(_typography(width, height))
    _draw_caption(canvas, caption, width, height)

    buffer = io.BytesIO()
    canvas.convert("RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def cutout(photo: bytes, mask: bytes) -> bytes:
    """사진에서 인물만 남긴 투명 PNG.

    **AI를 부르지 않는다.** 프론트(MediaPipe)가 올린 실루엣을 알파로 옮기면 끝이고,
    그래서 얼굴·체형이 100% 원본 그대로다.

    마스크 극성은 imagegen과 같은 규약이다 — 흰색이 인물이고, 뒤집혀 오면
    LOOKBOOK_MASK_INVERT로 되돌린다.
    """
    with Image.open(io.BytesIO(photo)) as source:
        person = source.convert("RGBA")

    with Image.open(io.BytesIO(mask)) as source:
        silhouette = source.convert("RGBA")

    if silhouette.size != person.size:
        silhouette = silhouette.resize(person.size, Image.LANCZOS)

    alpha = silhouette.getchannel("A")
    if alpha.getextrema() == (255, 255):  # 알파가 통째로 불투명하면 정보가 없다
        alpha = silhouette.convert("L")
    if settings.LOOKBOOK_MASK_INVERT:
        alpha = Image.eval(alpha, lambda value: 255 - value)

    person.putalpha(alpha.filter(ImageFilter.GaussianBlur(CUTOUT_FEATHER_PX)))
    buffer = io.BytesIO()
    person.save(buffer, format="PNG")
    return buffer.getvalue()


def _cover(data: bytes, width: int, height: int) -> Image.Image:
    """비율을 지키며 화면을 가득 채운다. 남는 쪽은 잘라낸다.

    여백을 두면 사진이 상자에 갇혀 보이고, 늘리면 얼굴이 일그러진다. 누끼처럼 투명한
    이미지가 들어올 수 있어 바탕을 먼저 깐다.
    """
    canvas = Image.new("RGBA", (width, height), (26, 26, 26, 255))
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGBA")

    scale = max(width / image.width, height / image.height)
    resized = image.resize((round(image.width * scale), round(image.height * scale)), Image.LANCZOS)
    canvas.alpha_composite(resized, ((width - resized.width) // 2, (height - resized.height) // 2))
    return canvas


def _typography(width: int, height: int) -> Image.Image:
    """시안에서 오려낸 레터링. 파일이 없으면 폰트로 흉내 낸다."""
    path = Path(settings.MEDIA_ROOT) / "lookbooks" / TYPOGRAPHY_NAME
    if not path.exists():
        return _drawn_typography(width, height)
    with Image.open(path) as image:
        return image.convert("RGBA").resize((width, height), Image.LANCZOS)


def _drawn_typography(width: int, height: int) -> Image.Image:
    """오려낸 타이포가 없을 때의 대체물. 찢긴 종이 질감까지는 흉내 낼 수 없다."""
    layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(
        (int(width * 0.01), int(height * 0.05)),
        BRAND_TEXT,
        font=_font(int(height * 0.20)),
        fill=(238, 236, 230, 255),
    )

    strip = Image.new("RGBA", (int(height * 0.60), int(height * 0.04)), (0, 0, 0, 0))
    ImageDraw.Draw(strip).text(
        (0, 0), SIDE_TEXT, font=_font(int(height * 0.022)), fill=(238, 236, 230, 255)
    )
    layer.alpha_composite(strip.rotate(90, expand=True), (int(width * 0.31), int(height * 0.05)))
    return layer


def _draw_scrim(canvas: Image.Image, width: int, height: int) -> None:
    """아래로 갈수록 어두워지는 막. 캡션이 어떤 사진 위에서도 읽힌다."""
    top = int(height * SCRIM_TOP)
    scrim = Image.new("RGBA", (width, height - top), (0, 0, 0, 0))
    draw = ImageDraw.Draw(scrim)
    for offset in range(scrim.height):
        draw.line(
            [(0, offset), (width, offset)],
            fill=(0, 0, 0, round(SCRIM_ALPHA * offset / scrim.height)),
        )
    canvas.alpha_composite(scrim, (0, top))


def _draw_caption(canvas: Image.Image, caption: dict, width: int, height: int) -> None:
    """N.011 / 매장 / 시즌. 방문마다 값이 다르므로 오려 쓸 수 없고 매번 그린다."""
    values = (caption.get("muse_label"), caption.get("venue"), caption.get("season"))
    lines = [str(value) for value in values if value]
    if not lines:
        return

    draw = ImageDraw.Draw(canvas)
    font = _font(int(height * 0.020))
    step = int(height * 0.026)
    x = int(width * CAPTION_LEFT)
    y = height - int(height * CAPTION_BOTTOM) - step * len(lines)
    for index, line in enumerate(lines):
        draw.text((x, y + index * step), line, font=font, fill=(240, 238, 232, 255))


def _box(ratios: tuple[float, float, float, float], width: int, height: int) -> tuple[int, int, int, int]:
    left, top, right, bottom = ratios
    return int(width * left), int(height * top), int(width * right), int(height * bottom)


def _paste_contain(canvas: Image.Image, data: bytes, box: tuple[int, int, int, int]) -> None:
    """비율을 지키며 상자 안에 맞춰 넣는다."""
    left, top, right, bottom = box
    max_width, max_height = right - left, bottom - top
    if max_width <= 0 or max_height <= 0:
        return

    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGBA")

    scale = min(max_width / image.width, max_height / image.height)
    target = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    resized = image.resize(target, Image.LANCZOS)
    x = left + (max_width - resized.width) // 2
    y = top + (max_height - resized.height) // 2
    canvas.alpha_composite(resized, (x, y))


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size=size)
