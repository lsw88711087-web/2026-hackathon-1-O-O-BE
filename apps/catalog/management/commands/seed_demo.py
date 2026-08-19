"""매장·전시존·상품 시드. 크롤링 데이터가 오면 fixtures/demo.json만 교체하면 된다."""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.catalog.models import PresetKey, Product, Scene, Store

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "demo.json"
# 이 8개가 취향 분석의 축이다. 하나라도 비면 그 상품은 분석에서 빠진다.
ANALYSIS_AXES = (
    "category",
    "color",
    "material",
    "pattern",
    "silhouette",
    "mood",
    "price_band",
    "use_case",
)
PRODUCT_FIELDS = (
    "no",
    "name",
    "price",
    "external_url",
    "story",
    "images",
    "cutout_url",
    "category",
    "color",
    "material",
    "pattern",
    "silhouette",
    "mood",
    "price_band",
    "use_case",
    "is_new",
    "attributes",
    "preset_answers",
    "llm_context",
)


class Command(BaseCommand):
    help = "전시존·상품 시드 데이터를 적재한다 (여러 번 실행해도 안전)."

    def add_arguments(self, parser):
        parser.add_argument("--file", default=str(DEFAULT_FIXTURE), help="적재할 JSON 경로")

    def handle(self, *args, **options):
        path = Path(options["file"])
        if not path.exists():
            raise CommandError(f"시드 파일이 없습니다: {path}")

        data = json.loads(path.read_text(encoding="utf-8"))
        with transaction.atomic():
            store = self._upsert_store(data["store"])
            scene_count, product_count = self._upsert_scenes(store, data["scenes"])

        self.stdout.write(
            self.style.SUCCESS(f"{store.name}: 전시존 {scene_count}개 · 상품 {product_count}개 적재 완료")
        )
        for label, ids in (
            ("분류 축이 빈 상품", self._products_missing_axes()),
            ("프리셋 답변이 빠진 상품", self._products_missing_presets()),
        ):
            if ids:
                self.stdout.write(self.style.WARNING(f"{label} {len(ids)}개: {ids}"))

    def _upsert_store(self, payload: dict) -> Store:
        store, _ = Store.objects.update_or_create(id=payload["id"], defaults={"name": payload["name"]})
        return store

    def _upsert_scenes(self, store: Store, scenes: list[dict]) -> tuple[int, int]:
        product_count = 0
        for scene_payload in scenes:
            scene, _ = Scene.objects.update_or_create(
                id=scene_payload["id"],
                defaults={"store": store, "no": scene_payload["no"], "name": scene_payload["name"]},
            )
            for product_payload in scene_payload["products"]:
                defaults = {field: product_payload[field] for field in PRODUCT_FIELDS}
                defaults["scene"] = scene
                Product.objects.update_or_create(id=product_payload["id"], defaults=defaults)
                product_count += 1
        return len(scenes), product_count

    def _products_missing_presets(self) -> list[str]:
        """프리셋 3종이 없으면 상품 클릭 시 버튼이 비어 보인다."""
        return [
            product.id
            for product in Product.objects.all()
            if any(not product.preset_answers.get(key) for key in PresetKey.values)
        ]

    def _products_missing_axes(self) -> list[str]:
        """축이 하나라도 비면 그 상품은 취향 분석에서 사라지므로 적재 직후에 알려준다."""
        blank_any_axis = Q()
        for axis in ANALYSIS_AXES:
            blank_any_axis |= Q(**{axis: ""})
        return list(Product.objects.filter(blank_any_axis).values_list("id", flat=True))
