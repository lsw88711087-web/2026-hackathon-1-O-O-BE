from django.urls import path

from apps.lookbook.views import (
    LookbookCandidateView,
    LookbookCreateView,
    LookbookDetailView,
    LookbookJobView,
    UploadPresignView,
    UploadReceiveView,
)

urlpatterns = [
    path(
        "reports/<str:slug>/lookbook/candidates",
        LookbookCandidateView.as_view(),
        name="lookbook-candidates",
    ),
    path("lookbooks/jobs/<str:job_id>", LookbookJobView.as_view(), name="lookbook-job"),
    path("reports/<str:slug>/lookbook", LookbookCreateView.as_view(), name="lookbook-create"),
    path("lookbooks/<str:share_slug>", LookbookDetailView.as_view(), name="lookbook-detail"),
    path("uploads/presign", UploadPresignView.as_view(), name="upload-presign"),
    # ⚠️ presign보다 아래에 둔다. <path:key>가 "presign"까지 삼키기 때문이다.
    path("uploads/<path:key>", UploadReceiveView.as_view(), name="upload-put"),
]
