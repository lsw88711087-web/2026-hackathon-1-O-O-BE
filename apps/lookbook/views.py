from django.conf import settings
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.parsers import BaseParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsVisitAuthenticated
from apps.analysis.models import Report, ReportStatus
from apps.lookbook import candidates, detail, generate, jobs, mocks, progress, storage, worker
from apps.lookbook.errors import LookbookNotReady, ReportPending
from apps.lookbook.models import Lookbook, LookbookStatus
from apps.lookbook.serializers import (
    CandidateListSerializer,
    JobStatusSerializer,
    LookbookCreateResponseSerializer,
    LookbookCreateSerializer,
    LookbookDetailSerializer,
    PresignRequestSerializer,
    PresignResponseSerializer,
)


class LookbookCandidateView(APIView):
    """GET /api/v1/reports/{slug}/lookbook/candidates — 화보에 담을 상품 후보 6개.

    화보는 관람이 끝난 뒤(`/finish` 이후) 열리는 화면이라 종료된 방문에서도
    호출된다. 그래서 IsOpenVisit이 아니라 IsVisitAuthenticated를 쓴다.
    """

    permission_classes = [IsVisitAuthenticated]

    @extend_schema(responses={200: CandidateListSerializer}, tags=["Lookbook"])
    def get(self, request, slug: str):
        report = get_object_or_404(Report.objects.select_related("visit"), pk=slug)
        self._assert_owns(request.auth, report)
        self._assert_ready(report)
        return Response(candidates.build(report, request), status=status.HTTP_200_OK)

    def _assert_owns(self, visit, report: Report) -> None:
        """slug는 추측하기 어렵지만 열쇠를 두 개 요구한다. 남의 리포트로 후보를 뽑지 못한다."""
        if report.visit_id != visit.id:
            raise PermissionDenied("이 리포트의 방문이 아닙니다.")

    def _assert_ready(self, report: Report) -> None:
        if report.status == ReportStatus.READY:
            return
        if report.status == ReportStatus.PENDING:
            raise ReportPending()
        raise NotFound("리포트 분석에 실패해 후보를 만들 수 없습니다.")


class LookbookJobView(APIView):
    """GET /api/v1/lookbooks/jobs/{job_id} — 화보 생성 진행 상태 (폴링).

    **인증이 없다.** job_id는 추측하기 어려운 값이고, 로딩 화면은 토큰이 만료된
    뒤에도 열려 있을 수 있다. 여기서 나가는 정보는 진행률뿐이라 잃을 게 없다.

    **DB에 가지 않는다.** 화보 하나당 폴링이 8~9번이라 동시 100명이면 초당 33회가
    전부 똑같은 답을 가져오게 된다. 휘발성 값은 캐시에서 읽는다.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: JobStatusSerializer}, auth=[], tags=["Lookbook"])
    def get(self, request, job_id: str):
        state = mocks.apply(job_id, jobs.read(job_id))
        if state is None:
            raise NotFound("진행 상태를 찾을 수 없습니다. 만료되었거나 없는 작업입니다.")
        return Response(jobs.as_response(state), status=status.HTTP_200_OK)


class UploadPresignView(APIView):
    """POST /api/v1/uploads/presign — 사진·마스크 업로드 URL 2개를 한 번에 발급한다.

    마스크는 인물 실루엣이다. 화보 생성 때 그 영역을 건드리지 않아야 체형과 얼굴이
    보존되므로, 사진과 짝으로 올릴 자리를 함께 내준다.
    """

    permission_classes = [IsVisitAuthenticated]

    @extend_schema(
        request=PresignRequestSerializer,
        responses={200: PresignResponseSerializer},
        tags=["Lookbook"],
    )
    def post(self, request):
        serializer = PresignRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        content_type = serializer.validated_data["content_type"]

        # local 백엔드는 이 URL이 우리 서버를 가리킨다. 요청에서 scheme+host를 그대로 떼어
        # 쓰면 localhost든 sslip.io든 설정을 고치지 않아도 맞는 주소가 나가고,
        # SECURE_PROXY_SSL_HEADER 덕분에 배포에서는 https로 나간다(mixed content 회피).
        base_url = request.build_absolute_uri("/")[:-1]

        photo = storage.presign_put(storage.new_photo_key(content_type), content_type, base_url)
        mask = storage.presign_put(storage.mask_key_for(photo.key), storage.MASK_CONTENT_TYPE, base_url)

        return Response(
            {
                "photo_key": photo.key,
                "photo_upload_url": photo.upload_url,
                "mask_key": mask.key,
                "mask_upload_url": mask.upload_url,
                "headers": {
                    "photo": {"Content-Type": photo.content_type},
                    "mask": {"Content-Type": mask.content_type},
                },
                "expires_in": settings.UPLOAD_URL_TTL_SEC,
            },
            status=status.HTTP_200_OK,
        )


class RawBodyParser(BaseParser):
    """PUT 본문을 그대로 바이트로 받는다.

    DRF는 content_type에 맞는 파서가 없으면 415를 낸다. 여기 오는 건 image/jpeg 같은
    원본 바이트라 파싱할 게 없다. 상한을 넘겨 읽어두고 뷰에서 크기를 판정한다 —
    딱 상한만큼 읽으면 5MB짜리와 5MB+1바이트짜리를 구분할 수 없다.
    """

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read(settings.PHOTO_MAX_BYTES + 1)


class UploadReceiveView(APIView):
    """PUT /api/v1/uploads/{key} — local 백엔드에서 사진·마스크 바이트를 받는다.

    버킷이 없을 때 presign이 내주는 URL의 도착지다. **s3 백엔드에서는 열리지 않는다.**
    그때는 브라우저가 R2로 직행하므로 이 경로가 살아 있으면 안 쓰는 문이 남는 셈이다.

    **인증이 없다.** presign URL은 프론트가 헤더 없이 그대로 PUT하는 값이고, 버킷이
    생기면 실제로 그렇게 동작한다. 여기만 토큰을 요구하면 s3로 옮기는 날 프론트를 다시
    고쳐야 한다. 대신 키를 서버가 발급한 모양으로 못박고(KEY_PATTERN), 크기와 실제
    바이트를 확인한다.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [RawBodyParser]

    @extend_schema(request=bytes, responses={200: None}, auth=[], tags=["Lookbook"])
    def put(self, request, key: str):
        if settings.STORAGE_BACKEND != storage.BACKEND_LOCAL:
            raise NotFound("이 서버는 업로드를 직접 받지 않습니다.")

        data = request.data if isinstance(request.data, bytes) else b""
        if not data:
            raise ValidationError({"file": ["empty_body"]})
        if len(data) > settings.PHOTO_MAX_BYTES:
            raise ValidationError({"file": ["file_too_large"]})
        # 선언한 content_type이 아니라 실제 바이트를 본다. presign 때의 image/jpeg는
        # 클라이언트가 말한 값일 뿐이라 아무거나 올릴 수 있다.
        if not storage.is_image(data[: storage.MAGIC_BYTES]):
            raise ValidationError({"file": ["not_an_image"]})

        try:
            storage.save_local(key, data)
        except storage.InvalidKey:
            raise ValidationError({"key": ["invalid_key"]}) from None

        return Response({"key": key, "byte_size": len(data)}, status=status.HTTP_200_OK)


class LookbookCreateView(APIView):
    """POST /api/v1/reports/{slug}/lookbook — 화보 생성·재생성.

    큐에 넣고 즉시 202를 돌려준다. [다시 돌리기]도 같은 엔드포인트를 같은 값으로
    재호출하면 되고, 매번 새 share_slug를 발급한다 — 이미 공유한 링크의 이미지가
    바뀌면 남이 열었을 때 다른 화보가 보이기 때문이다.
    """

    permission_classes = [IsVisitAuthenticated]

    @extend_schema(
        request=LookbookCreateSerializer,
        responses={202: LookbookCreateResponseSerializer},
        tags=["Lookbook"],
    )
    def post(self, request, slug: str):
        serializer = LookbookCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = get_object_or_404(Report.objects.select_related("visit"), pk=slug)
        lookbook = generate.accept(report, request.auth, serializer.validated_data)
        worker.enqueue(lookbook)

        return Response(
            {
                "job_id": lookbook.job_id,
                "share_slug": lookbook.share_slug,
                "attempt": lookbook.attempt,
                "remaining_regenerations": generate.remaining_regenerations(lookbook.attempt),
                "poll_after_ms": progress.POLL_SLOW_MS,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class LookbookDetailView(APIView):
    """GET /api/v1/lookbooks/{share_slug} — 완성 화보.

    **인증이 없다.** 남이 열어도 보여야 하는 공유 링크라 slug가 곧 열쇠다.
    박제된 값을 그대로 내고 재계산하지 않는다.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: LookbookDetailSerializer}, auth=[], tags=["Lookbook"])
    def get(self, request, share_slug: str):
        lookbook = get_object_or_404(Lookbook, pk=share_slug)
        if lookbook.status != LookbookStatus.READY:
            # "없음"과 "아직"은 프론트가 다르게 처리해야 한다.
            raise LookbookNotReady()
        return Response(detail.build(lookbook, request), status=status.HTTP_200_OK)
