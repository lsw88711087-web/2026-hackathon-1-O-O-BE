from django.urls import path

from apps.analysis.views import ReportDetailView, VisitFinishView

urlpatterns = [
    path("visits/<str:visit_id>/finish", VisitFinishView.as_view(), name="visit-finish"),
    path("reports/<str:slug>", ReportDetailView.as_view(), name="report-detail"),
]
