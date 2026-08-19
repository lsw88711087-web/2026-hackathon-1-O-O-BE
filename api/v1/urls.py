from django.urls import include, path

urlpatterns = [
    path("", include("apps.visits.urls")),
    path("", include("apps.catalog.urls")),
    path("", include("apps.events.urls")),
    path("", include("apps.chat.urls")),
    path("", include("apps.analysis.urls")),
    path("", include("apps.lookbook.urls")),
    path("admin/", include("apps.dashboard.urls")),
]
