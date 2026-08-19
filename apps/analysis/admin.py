"""16유형 문구·이미지는 기획이 채운다. 그 입력 화면이 이 파일의 목적이다."""

from django.contrib import admin

from apps.analysis.models import Character, Report


@admin.register(Character)
class CharacterAdmin(admin.ModelAdmin):
    list_display = ("type_code", "name", "one_liner")
    list_editable = ("name", "one_liner")
    ordering = ("type_code",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    """리포트는 박제물이라 읽기 전용이다. 실패한 방문을 찾는 용도로만 쓴다."""

    list_display = ("slug", "visit", "status", "created_at")
    list_filter = ("status",)
    readonly_fields = ("slug", "visit", "status", "payload", "failure_reason")
    list_select_related = ("visit",)
