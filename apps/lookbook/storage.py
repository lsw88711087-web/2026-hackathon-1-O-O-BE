"""업로드 키 생성과 presign URL 발급.

사진 바이트는 Django를 지나가지 않는다. 서버로 받으면 매장 와이파이에서 500KB
올리는 3초 동안 워커 프로세스가 통째로 묶이기 때문이다. 서버는 URL만 발급하고
브라우저가 스토리지로 직행한다.
"""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

PHOTO_PREFIX = "photos"
MASK_SUFFIX = "_mask"
MASK_CONTENT_TYPE = "image/png"

# 확장자는 선언된 content_type에서 뽑는다. 클라이언트 파일명은 쓰지 않는다.
EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
ALLOWED_CONTENT_TYPES = tuple(EXTENSIONS)

BACKEND_DEV = "dev"
BACKEND_LOCAL = "local"
BACKEND_S3 = "s3"

# 로컬 백엔드가 파일을 쓰기 전에 통과시켜야 하는 유일한 관문. 서명을 붙이지 않기로 했으므로
# 키 모양이 곧 방어선이고, `../`나 절대경로로 저장 위치를 벗어나는 시도가 여기서 끊긴다.
KEY_PATTERN = re.compile(r"^photos/\d{4}/\d{2}/\d{2}/[0-9a-f]{16}(_mask)?\.(jpg|png|webp)$")


class InvalidKey(ValueError):
    """서버가 발급한 적 없는 모양의 키다."""


@dataclass(frozen=True)
class UploadTarget:
    key: str
    upload_url: str
    content_type: str


def new_photo_key(content_type: str) -> str:
    """서버가 만든다. 클라이언트 파일명을 쓰면 경로 조작(../../)과 한글·이모지 파일명이
    그대로 들어오는데, UUID로 덮으면 그 문제가 통째로 사라지고 키를 추측할 수 없게 되는
    효과도 함께 온다."""
    today = timezone.now()
    name = uuid.uuid4().hex[:16]
    return f"{PHOTO_PREFIX}/{today:%Y/%m/%d}/{name}{EXTENSIONS[content_type]}"


def mask_key_for(photo_key: str) -> str:
    """마스크는 사진과 같은 이름에 접미사만 붙인다. 둘이 짝이라는 게 키에서 읽힌다."""
    base = photo_key.rsplit(".", 1)[0]
    return f"{base}{MASK_SUFFIX}.png"


def presign_put(key: str, content_type: str, base_url: str = "") -> UploadTarget:
    """PUT용 업로드 URL. 만료는 settings.UPLOAD_URL_TTL_SEC.

    base_url은 local 백엔드에서만 쓴다. 호출한 요청의 scheme+host를 그대로 되돌려주면
    localhost든 배포 도메인이든 설정을 고치지 않아도 맞는 주소가 나간다.
    """
    if settings.STORAGE_BACKEND == BACKEND_S3:
        url = _presign_s3(key, content_type)
    elif settings.STORAGE_BACKEND == BACKEND_LOCAL:
        url = _presign_local(key, base_url)
    else:
        url = _presign_dev(key)
    return UploadTarget(key=key, upload_url=url, content_type=content_type)


def _presign_local(key: str, base_url: str) -> str:
    """버킷이 없을 때 Django가 직접 받는다.

    presign → PUT 흐름과 응답 필드는 s3와 똑같이 유지한다. 프론트가 이 단계에서 쓴 코드가
    나중에 버킷이 생겨도 그대로 살아야 하기 때문이다. 바뀌는 건 URL이 가리키는 곳뿐이다.

    **서명이 없으므로 만료도 없다.** expires_in은 계약을 지키려고 그대로 내려가지만
    local에서는 강제되지 않는다. 데모용으로 감수한 부분이다.
    """
    base = (base_url or settings.UPLOAD_LOCAL_BASE_URL).rstrip("/")
    return f"{base}{reverse('upload-put', kwargs={'key': key})}"


def _presign_dev(key: str) -> str:
    """버킷이 없는 개발 환경용. 계약(키·URL·만료)을 그대로 확인할 수 있게 하되,
    **실제로 PUT을 받지는 않는다.** 받는 척하면 업로드가 됐다고 착각하게 된다."""
    return f"{settings.UPLOAD_DEV_BASE_URL}/{key}?dev-unsigned=1&expires_in={settings.UPLOAD_URL_TTL_SEC}"


def _presign_s3(key: str, content_type: str) -> str:
    """R2·S3 공통(R2가 S3 호환 API를 쓴다). boto3는 이 백엔드를 켤 때만 필요하다."""
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    )
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": settings.STORAGE_BUCKET, "Key": key, "ContentType": content_type},
        ExpiresIn=settings.UPLOAD_URL_TTL_SEC,
    )


# 파일 앞부분 시그니처. presign의 content_type은 클라이언트가 선언한 값이라 실제 내용과
# 무관하다. image/jpeg라고 해놓고 아무거나 올릴 수 있어서 바이트로 확인한다.
MAGIC_BYTES = 12
_SIGNATURES = (
    (b"\xff\xd8\xff", 0),  # JPEG
    (b"\x89PNG\r\n\x1a\n", 0),  # PNG
    (b"WEBP", 8),  # RIFF....WEBP
)


class UploadNotFound(LookupError):
    """presign만 받고 실제로 올리지 않았다."""


class NotAnImage(ValueError):
    """올라온 바이트가 이미지가 아니다."""


def local_path(key: str) -> Path:
    """키를 UPLOAD_LOCAL_ROOT 아래 실제 경로로 바꾼다. 형식이 어긋나면 파일을 만지기 전에 끊는다.

    **MEDIA_ROOT가 아니다.** nginx가 /media/를 통째로 공개 서빙하므로 거기 두면 얼굴 사진이
    URL만 알면 열리는 파일이 된다. 명세의 `photos/ 비공개, 워커만 접근`을 지키려면
    웹서버가 모르는 디렉터리여야 한다.
    """
    if not KEY_PATTERN.match(key):
        raise InvalidKey(key)
    return Path(settings.UPLOAD_LOCAL_ROOT) / key


def save_local(key: str, data: bytes) -> None:
    """local 백엔드의 PUT 수신부. 날짜 디렉터리는 처음 올라올 때 생긴다."""
    path = local_path(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def verify_upload(key: str) -> None:
    """실제로 올라왔는지, 진짜 이미지인지 확인한다.

    dev 백엔드는 확인할 대상이 없으므로 건너뛴다. 없는 것을 있다고 답하면 안 되고,
    없다고 400을 내면 버킷이 생기기 전까지 생성 자체를 못 하게 된다.
    """
    if settings.STORAGE_BACKEND == BACKEND_LOCAL:
        _verify_local(key)
        return
    if settings.STORAGE_BACKEND != BACKEND_S3:
        return

    import boto3
    from botocore.exceptions import ClientError

    client = boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    )
    try:
        head = client.get_object(Bucket=settings.STORAGE_BUCKET, Key=key, Range=f"bytes=0-{MAGIC_BYTES - 1}")
    except ClientError as error:
        raise UploadNotFound(key) from error

    if not is_image(head["Body"].read(MAGIC_BYTES)):
        raise NotAnImage(key)


def _verify_local(key: str) -> None:
    """디스크에서 앞 12바이트만 읽는다. 5MB를 통째로 메모리에 올릴 이유가 없다."""
    try:
        path = local_path(key)
    except InvalidKey as error:
        raise UploadNotFound(key) from error

    try:
        with path.open("rb") as file:
            head = file.read(MAGIC_BYTES)
    except OSError as error:
        raise UploadNotFound(key) from error

    if not is_image(head):
        raise NotAnImage(key)


def is_image(head: bytes) -> bool:
    """앞 12바이트로 판정한다. 순수 함수라 테스트가 쉽다."""
    return any(head[offset : offset + len(sig)] == sig for sig, offset in _SIGNATURES)


LOOKBOOK_PREFIX = "lookbooks"


def read_bytes(key: str) -> bytes:
    """올라온 사진을 통째로 읽는다. 워커가 벤더에 넘길 재료다."""
    if settings.STORAGE_BACKEND == BACKEND_LOCAL:
        try:
            return local_path(key).read_bytes()
        except (OSError, InvalidKey) as error:
            raise UploadNotFound(key) from error

    if settings.STORAGE_BACKEND != BACKEND_S3:
        raise UploadNotFound(key)

    from botocore.exceptions import ClientError

    try:
        obj = _s3_client().get_object(Bucket=settings.STORAGE_BUCKET, Key=key)
    except ClientError as error:
        raise UploadNotFound(key) from error
    return obj["Body"].read()


def save_public(key: str, data: bytes, content_type: str = "image/png") -> str:
    """완성 화보를 공개 위치에 저장하고 URL을 돌려준다.

    사진(photos/)과 반대다. 화보는 공유 링크로 남이 열어야 하므로 공개여야 하고,
    그래서 local에서는 nginx가 서빙하는 MEDIA_ROOT에 쓴다.
    """
    if settings.STORAGE_BACKEND == BACKEND_S3:
        _s3_client().put_object(
            Bucket=settings.STORAGE_BUCKET, Key=key, Body=data, ContentType=content_type
        )
        base = (settings.STORAGE_PUBLIC_BASE_URL or "").rstrip("/")
        return f"{base}/{key}" if base else key

    path = Path(settings.MEDIA_ROOT) / key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return f"{settings.MEDIA_URL}{key}"


def _s3_client():
    """s3 호출 3곳이 같은 설정을 쓴다. 한 군데만 고쳐도 되게 모았다."""
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=settings.STORAGE_ENDPOINT_URL or None,
        aws_access_key_id=settings.STORAGE_ACCESS_KEY,
        aws_secret_access_key=settings.STORAGE_SECRET_KEY,
        region_name=settings.STORAGE_REGION,
    )
