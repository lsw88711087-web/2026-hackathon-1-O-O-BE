from rest_framework import serializers

from apps.catalog.models import Product, Scene, Store


class StoreBriefSerializer(serializers.ModelSerializer):
    store_id = serializers.CharField(source="id")

    class Meta:
        model = Store
        fields = ("store_id", "name")


class ProductBriefSerializer(serializers.ModelSerializer):
    """목록용 간략 정보. 상세 정보는 GET /products/{id}가 준다."""

    product_id = serializers.CharField(source="id")
    thumbnail = serializers.CharField(allow_null=True)

    class Meta:
        model = Product
        fields = ("product_id", "no", "name", "thumbnail", "price")


class SceneSerializer(serializers.ModelSerializer):
    """전시존 구성. 좌표·도면은 내려주지 않는다 — 맵은 프론트가 직접 만든다.

    no를 함께 주는 이유는 챗봇이 "1번 진열대 3번 상품"처럼 번호로 안내해야 하기 때문이다.
    """

    scene_id = serializers.CharField(source="id")
    products = ProductBriefSerializer(many=True)

    class Meta:
        model = Scene
        fields = ("scene_id", "no", "name", "products")


class ProductDetailSerializer(serializers.ModelSerializer):
    """상세 화면용. 분석 내부용 필드(8개 축·llm_context)는 내려주지 않는다."""

    product_id = serializers.CharField(source="id")
    scene_id = serializers.CharField(source="scene.id")
    cutout_url = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "product_id",
            "name",
            "images",
            "cutout_url",
            "price",
            "attributes",
            "story",
            "scene_id",
            "external_url",
            "preset_answers",
        )

    def get_cutout_url(self, product: Product) -> str:
        """배경 제거 PNG의 절대 주소.

        DB에는 `/media/cutouts/...` 상대 경로가 들어 있다. 프론트가 다른 도메인(Netlify)
        이라 그대로 주면 자기 사이트에서 찾다가 404가 난다. 응답 시점에 요청의 호스트를
        붙이는 이유는 두 가지다 — 도메인이 바뀌어도 데이터를 다시 넣을 필요가 없고,
        버킷으로 옮겨 절대 URL이 저장되면 build_absolute_uri가 그대로 통과시킨다.
        """
        if not product.cutout_url:
            return ""
        return self.context["request"].build_absolute_uri(product.cutout_url)
