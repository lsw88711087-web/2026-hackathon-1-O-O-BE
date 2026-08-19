from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from api.permissions import IsVisitAuthenticated
from apps.analysis import services
from apps.analysis.models import Report, ReportStatus
from apps.analysis.serializers import (
    FinishRequestSerializer,
    FinishResponseSerializer,
    ReportDetailSerializer,
)
from apps.visits.models import Visit


class VisitFinishView(APIView):
    """POST /api/v1/visits/{visit_id}/finish — 관람 종료.

    분석은 대기열로 넘기고 slug만 즉시 돌려준다. 같은 visit_id로 다시 호출해도
    같은 slug가 나온다(멱등).

    종료된 방문에서도 호출할 수 있어야 하므로 IsOpenVisit을 쓰지 않는다. 재전송이
    401을 맞으면 프론트는 slug를 영영 못 받는다.
    """

    permission_classes = [IsVisitAuthenticated]

    @extend_schema(
        request=FinishRequestSerializer,
        responses={202: FinishResponseSerializer},
        tags=["Report"],
    )
    def post(self, request, visit_id: str):
        serializer = FinishRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        visit = request.auth
        self._assert_owns(visit, visit_id)

        report, event_result, is_new = services.finish(visit, serializer.validated_data["events"])
        if is_new:
            services.enqueue(report)

        return Response(
            {"slug": report.pk, "status": report.status, "events": event_result},
            status=status.HTTP_202_ACCEPTED,
        )

    def _assert_owns(self, visit: Visit, visit_id: str) -> None:
        """토큰이 가리키는 방문만 종료할 수 있다. 클라이언트가 보낸 visit_id를 믿지 않는다."""
        if visit_id == visit.id:
            return
        if not Visit.objects.filter(pk=visit_id).exists():
            raise NotFound("존재하지 않는 방문입니다.")
        raise PermissionDenied("다른 방문을 종료할 수 없습니다.")


class ReportDetailView(APIView):
    """GET /api/v1/reports/{slug} — 박제된 리포트.

    **인증이 없다.** 매장을 떠난 뒤 집에서 열어야 하는데 그때는 visit_token이 없다.
    추측하기 어려운 slug가 곧 열쇠다.

    재계산하지 않는다. 추천 로직을 나중에 고쳐도 이미 공유된 링크의 내용은 그대로다.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(responses={200: ReportDetailSerializer}, auth=[], tags=["Report"])
    def get(self, request, slug: str):
        report = get_object_or_404(Report, pk=slug)
        response = Response(self._body(report), status=status.HTTP_200_OK)
        # 개인 리포트가 검색엔진에 걸리면 사고다. 무인증 공개라 이 헤더가 유일한 방어선이다.
        response["X-Robots-Tag"] = "noindex"
        return response

    def _body(self, report: Report) -> dict:
        """분석 중·실패일 때는 payload가 없다. 상태만 주고 프론트가 화면을 고른다."""
        if report.status != ReportStatus.READY:
            return {"status": report.status}
        return {"status": report.status, **report.payload}
