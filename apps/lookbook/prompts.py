"""화보 프롬프트 조립. 순수 함수만 둔다 — 네트워크도 DB도 여기서 만지지 않는다.

**모델에 넣는 이미지마다 역할을 말해줘야 한다.** 사진·레퍼런스·상품을 그냥 나란히
넣으면 모델은 뭘 보존하고 뭘 참고할지 모른다. 그래서 몇 번째 이미지가 무엇인지
문장으로 붙인다. 순서는 worker가 넣는 순서와 반드시 같아야 한다.

**레퍼런스에는 글자가 가득하다.** 기획 시안이 완성 레이아웃(MCM 타이포·캡션·프레임)
이라서다. 명세는 텍스트·프레임을 프론트 캔버스가 얹기로 정했으므로, AI가 그걸 따라
그리면 안 된다. 그래서 "글자·로고·프레임은 베끼지 말라"를 따로 못박는다.

재생성은 구도·자세만 흔들고 무드는 유지한다. 매번 다른 세계관이 나오면 "다시 돌리기"가
아니라 "다른 서비스"가 된다.
"""

# 기획 시안(화보 시리즈 8장)에서 뽑은 팔레트. 인물·구도는 같고 배경색만 달랐다.
# 리포트에 무드가 실려 오면 그 값을 쓰고, 없으면 seed로 고른다 — 지금 분석 워커가
# 무드를 만들지 않아서 비워두면 배경 지시가 통째로 빠진다.
MOODS = (
    ("ivory", "warm ivory and cream", "soft warm light, calm and classic"),
    ("brown", "tan and deep brown", "warm earthy light, heritage feel"),
    ("charcoal", "charcoal grey and black", "high-contrast moody light"),
    ("coral", "apricot and coral", "bright airy light, playful"),
)

# 재생성마다 흔드는 값. seed로 고르므로 같은 회차는 항상 같은 문구가 나온다.
VARIATIONS = (
    "a relaxed three-quarter stance",
    "a straight-on frontal stance",
    "a slight turn of the shoulders with the gaze off-camera",
    "a subtle contrapposto with weight on one leg",
)

# 왼쪽 띠는 비워야 한다. 그 자리에 MCM 레터링이 얹히는데, 인물이 가운데 있으면
# 글자가 얼굴을 가로지른다. 시안도 인물이 오른쪽이고 왼쪽이 타이포 자리다.
FRAMING = (
    "Place the person on the right side of the frame. Leave the left third of the image "
    "as clean empty background with no part of the person, product or props in it."
)

# 배경의 공통 소재. 시안 전체에 성당 실루엣이 깔려 있었다.
BACKDROP = (
    "Background: a seamless studio backdrop with a faint gothic cathedral silhouette, "
    "styled like a fashion magazine editorial."
)

BASE_RULES = (
    "Photorealistic editorial fashion photography with natural skin texture. "
    "Absolutely no text, no typography, no lettering, no logos, no watermarks, "
    "no torn-paper frames and no collage borders anywhere in the image."
)


def build(
    *,
    mood: dict,
    composition_prompt: str,
    product_names: list[str],
    venue: str,
    season: str,
    seed: int,
    attempt: int,
    has_reference: bool,
    has_product_image: bool = False,
) -> str:
    """이미지 편집 프롬프트 한 덩어리. 문장 단위로 이어 붙인다."""
    parts = [
        f"Editorial fashion lookbook photograph for {season} at {venue}.",
        _roles(has_reference, has_product_image),
        _mood_sentence(mood, seed),
        FRAMING,
        BACKDROP,
        _product_sentence(product_names, has_product_image),
        composition_prompt.strip(),
        _variation_sentence(seed, attempt),
        BASE_RULES,
    ]
    return " ".join(part for part in parts if part)


def _roles(has_reference: bool, has_product_image: bool) -> str:
    """몇 번째 이미지가 무엇인지. worker가 넣는 순서와 같아야 한다.

    사진 → 레퍼런스 → 상품 순이고, 없는 것은 번호에서 빠진다. 번호가 밀리면
    모델이 상품 사진을 보존 대상으로 오해한다.
    """
    lines = [
        "Image 1 is the person to keep: this must be the same identifiable person. "
        "Preserve their facial features, face shape, eyes, nose, mouth, hairstyle, "
        "body proportions and skin tone exactly as they are — do not substitute a "
        "different-looking model.",
    ]
    index = 2
    if has_reference:
        lines.append(
            f"Image {index} is a style reference: follow only its camera angle, framing, "
            "color palette and lighting mood. Do not copy its text, typography, graphics, "
            "frames or layout, and do not copy the person or clothing shown in it."
        )
        index += 1
    if has_product_image:
        lines.append(
            f"Image {index} is the product: place it on the person naturally and keep its "
            "shape, color, hardware and pattern faithful to the reference."
        )
    return " ".join(lines)


def _mood_sentence(mood: dict, seed: int) -> str:
    """리포트에서 박제된 무드가 있으면 그것을, 없으면 seed로 고른 팔레트를 쓴다.

    같은 방문은 seed가 고정이라 재생성해도 팔레트가 유지된다 — "무드는 비슷하게"를
    무드 데이터 없이도 지킨다.
    """
    name = (mood.get("name") or "").strip()
    palette = mood.get("palette") or []
    if name or palette:
        sentence = f"Overall mood: {name}." if name else ""
        if palette:
            sentence += f" Color palette: {', '.join(str(color) for color in palette)}."
        return sentence.strip()

    _, colors, light = MOODS[seed % len(MOODS)]
    return f"Color palette: {colors}. Lighting: {light}."


def _product_sentence(product_names: list[str], has_product_image: bool) -> str:
    """상품이 주인공이다. 사진이 없으면 이름만으로라도 형태를 지정한다."""
    if not product_names:
        return ""
    names = ", ".join(product_names)
    if has_product_image:
        return f"The product is: {names}."
    return f"The person is styled with: {names}. Keep the product's shape, color and details faithful."


def _variation_sentence(seed: int, attempt: int) -> str:
    """첫 컷은 흔들지 않는다. 재생성일 때만 자세·구도를 바꾼다."""
    if attempt <= 1:
        return ""
    return f"Vary the framing and pose from previous versions: use {VARIATIONS[seed % len(VARIATIONS)]}."
