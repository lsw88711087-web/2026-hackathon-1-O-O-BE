"""구도 마스터를 화면에서 손보게 한다.

레퍼런스 이미지와 프롬프트는 기획이 채우는 값이다. 코드에 박아두면 문구 한 줄
바꾸는 데 배포가 필요해서, 원 설계대로 DB에 두고 admin에서 편집한다.
"""

from django.contrib import admin

from apps.lookbook.models import Composition, Lookbook


@admin.register(Composition)
class CompositionAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "min_face", "max_face", "has_reference")
    fields = ("code", "name", "min_face", "max_face", "reference_url", "prompt")

    @admin.display(boolean=True, description="레퍼런스")
    def has_reference(self, obj: Composition) -> bool:
        """비어 있으면 그 구도는 참조 없이 생성된다. 한눈에 보여야 채울 수 있다."""
        return bool(obj.reference_url)


@admin.register(Lookbook)
class LookbookAdmin(admin.ModelAdmin):
    """생성 결과 확인용. 실패했을 때 error_code를 여기서 본다."""

    list_display = ("share_slug", "attempt", "status", "error_code", "created_at")
    list_filter = ("status",)
    readonly_fields = [field.name for field in Lookbook._meta.fields]
