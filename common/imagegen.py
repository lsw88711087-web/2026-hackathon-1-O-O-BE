"""이미지 생성 게이트웨이. 화보 합성 호출을 이 파일 한 곳에서 통제한다.

common/llm.py와 같은 규칙이다 — 앱 코드는 OpenAI SDK를 직접 import하지 않는다.
모델 교체·재시도·실패 분류가 여기서만 일어나야 벤더를 갈아끼울 때 워커를 안 건드린다.

**마스크 규약이 이 파일의 핵심이다.** OpenAI는 마스크의 *투명한* 영역을 고쳐 그린다.
인물을 보존하려면 인물이 불투명해야 한다. 프론트(MediaPipe)가 주는 실루엣은 인물이
흰색이므로, 그 밝기를 알파로 옮기면 규약이 맞는다. 뒤집히면 얼굴만 새로 그려진다.
"""

import base64
import io
import logging

from django.conf import settings
from openai import APITimeoutError, OpenAI, OpenAIError, RateLimitError
from PIL import Image

logger = logging.getLogger(__name__)

# jobs.py의 에러 코드와 같은 값을 쓴다. 여기서 문자열을 만들고 워커가 그대로 넘긴다.
TIMEOUT_ERROR = "GEN_TIMEOUT"
RATE_LIMITED_ERROR = "GEN_RATE_LIMITED"
UPSTREAM_ERROR = "GEN_UPSTREAM"
BLOCKED_ERROR = "GEN_CONTENT_BLOCKED"

# 벤더가 정책으로 막았을 때 보내는 신호. 얼굴 사진이라 이 분기가 실제로 발생한다.
_BLOCKED_HINTS = ("content_policy", "safety", "moderation_blocked", "rejected")


class ImageGenError(RuntimeError):
    """생성 실패. error_code로 재시도 가능 여부가 갈린다."""

    def __init__(self, error_code: str, message: str = ""):
        super().__init__(message or error_code)
        self.error_code = error_code


def edit(
    *, photo: bytes, mask: bytes | None, references: list[bytes], prompt: str, quality: str = ""
) -> bytes:
    """사진을 재료로 화보를 합성해 PNG 바이트를 돌려준다.

    references는 레이아웃 참조용이다. **비어 있으면 아무것도 넘기지 않는다** —
    빈 자리를 채우려고 아무 이미지나 붙이면 구도가 그쪽으로 끌려간다.
    """
    if not settings.OPENAI_API_KEY:
        raise ImageGenError(UPSTREAM_ERROR, "OPENAI_API_KEY가 설정되지 않았습니다.")

    base, size = _to_png(photo)
    # 첫 번째 이미지가 사용자 사진이어야 한다. 마스크는 첫 이미지에만 적용된다.
    images = [("photo.png", base, "image/png")]
    images += [(f"ref_{index}.png", _to_png(item)[0], "image/png") for index, item in enumerate(references)]

    client = OpenAI(api_key=settings.OPENAI_API_KEY, timeout=settings.LOOKBOOK_GEN_TIMEOUT_SEC)
    params = {
        "model": settings.LOOKBOOK_IMAGE_MODEL,
        "image": images,
        "prompt": prompt,
        "size": settings.LOOKBOOK_GEN_SIZE,
        "quality": quality or settings.LOOKBOOK_GEN_QUALITY,
        "output_format": "png",
    }
    if mask:
        params["mask"] = ("mask.png", _to_mask(mask, size), "image/png")

    try:
        result = client.images.edit(**params)
    except APITimeoutError as error:
        raise ImageGenError(TIMEOUT_ERROR, str(error)) from error
    except RateLimitError as error:
        raise ImageGenError(RATE_LIMITED_ERROR, str(error)) from error
    except OpenAIError as error:
        logger.exception("이미지 생성 실패")
        raise ImageGenError(_classify(error), str(error)) from error

    return base64.b64decode(result.data[0].b64_json)


def _classify(error: Exception) -> str:
    """정책 차단과 일시적 장애를 가른다. 차단을 retryable로 두면 재생성 3회를 헛되이 쓴다."""
    text = str(error).lower()
    return BLOCKED_ERROR if any(hint in text for hint in _BLOCKED_HINTS) else UPSTREAM_ERROR


def _to_png(data: bytes) -> tuple[bytes, tuple[int, int]]:
    """무엇이 올라오든 RGBA PNG로 맞춘다. 브라우저가 보낸 건 jpeg/webp일 수 있다."""
    with Image.open(io.BytesIO(data)) as image:
        converted = image.convert("RGBA")
        buffer = io.BytesIO()
        converted.save(buffer, format="PNG")
        return buffer.getvalue(), converted.size


def _to_mask(data: bytes, size: tuple[int, int]) -> bytes:
    """마스크를 사진과 같은 크기의 알파 PNG로 만든다.

    알파가 이미 의미를 갖고 있으면 그대로 쓰고, 없으면 밝기를 알파로 옮긴다
    (흰색=인물=불투명=보존). LOOKBOOK_MASK_INVERT로 뒤집을 수 있게 열어둔 이유는
    프론트의 실루엣 극성이 반대로 올 수 있고, 그때 배포 없이 되돌려야 하기 때문이다.
    """
    with Image.open(io.BytesIO(data)) as image:
        source = image.convert("RGBA")
        if source.size != size:
            source = source.resize(size)

        alpha = source.getchannel("A")
        if alpha.getextrema() == (255, 255):  # 알파가 통째로 불투명하면 정보가 없다
            alpha = source.convert("L")
        if settings.LOOKBOOK_MASK_INVERT:
            alpha = Image.eval(alpha, lambda value: 255 - value)

        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        canvas.putalpha(alpha)
        buffer = io.BytesIO()
        canvas.save(buffer, format="PNG")
        return buffer.getvalue()


def size_of(data: bytes) -> tuple[int, int]:
    """저장된 결과의 실제 크기. 프론트가 자리를 잡아야 화면이 안 튄다."""
    with Image.open(io.BytesIO(data)) as image:
        return image.size
