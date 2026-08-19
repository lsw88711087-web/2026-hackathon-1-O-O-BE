"""완성 화보 응답 조립. 화보 흐름에서 DB를 읽는 곳은 여기뿐이다.

이미지는 이 응답을 지나가지 않는다. URL 문자열만 넘기고 브라우저가 직접 받는다 —
올릴 때와 마찬가지로 내려받을 때도 서버를 우회한다.

**URL은 반드시 절대 주소로 나간다.** DB에는 `/media/lookbooks/...` 상대 경로가
저장되는데, 프론트가 Netlify라 그대로 주면 브라우저가 netlify.app에서 찾다가 404를
받는다. 저장 시점이 아니라 응답 시점에 절대화하는 이유는 두 가지다 — 워커에는 요청
컨텍스트가 없어 도메인을 모르고, 도메인이 바뀌어도 옛 행이 안 깨진다.
버킷으로 옮기면 이미 절대 URL이 저장되는데 build_absolute_uri는 그걸 그대로 통과시킨다.
"""

from apps.catalog.models import Product
from apps.lookbook import snapshot
from apps.lookbook.models import Lookbook


def build(lookbook: Lookbook, request) -> dict:
    """P03 화보 화면과 P04 공유 화면이 함께 쓰는 본문."""
    stored = lookbook.mood_payload if isinstance(lookbook.mood_payload, dict) else {}

    return {
        "share_slug": lookbook.share_slug,
        "attempt": lookbook.attempt,
        "image_url": request.build_absolute_uri(lookbook.image_url) if lookbook.image_url else "",
        "width": lookbook.width,
        "height": lookbook.height,
        "muse_no": stored.get("muse_no"),
        "muse_label": stored.get("muse_label"),
        "venue": stored.get("venue"),
        "season": stored.get("season"),
        "mood": snapshot.mood_of(stored),
        # label까지 서버가 내려주므로 프론트는 순회만 하면 된다.
        # 항목이 늘어도 API를 고칠 필요가 없다.
        "stats": snapshot.stats_of(stored),
        "products": _products(lookbook.product_ids, request),
        "report_slug": lookbook.report_id,
        "created_at": lookbook.created_at,
    }


def _products(product_ids: list, request) -> list[dict]:
    """화보에 담긴 상품. 상세로 넘어갈 링크가 있어야 구매로 이어진다."""
    products = Product.objects.filter(id__in=product_ids or [])
    return [
        {
            "product_id": product.id,
            "name": product.name,
            "image_url": request.build_absolute_uri(product.thumbnail) if product.thumbnail else None,
            "price": product.price,
            "detail_url": product.external_url,
        }
        for product in products
    ]
