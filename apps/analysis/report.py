"""⑦ 리포트 조립. 결과를 박제해 slug로 언제 열어도 같은 화면이 나오게 만든다.

상품 정보를 **복사해서** 넣는 이유는, 집에서 리포트를 열 때는 visit_token이 없어
`GET /products/{id}`를 부를 수 없기 때문이다. 나중에 가격이 바뀌어도 리포트는
그대로인데, 그게 의도된 동작이다.
"""

from apps.analysis import scoring
from apps.analysis.insight import Insight
from apps.analysis.models import Character
from apps.analysis.signals import ProductFacts, ScoredProduct, VisitSignals
from apps.analysis.vector import split_key
from apps.catalog.models import axis_label

# 캐릭터 시드가 아직 안 들어왔을 때. 리포트의 가장 눈에 띄는 자리가 비지 않게 한다.
UNKNOWN_CHARACTER_NAME = "분석 중인 타입"
UNKNOWN_CHARACTER_ONE_LINER = "취향을 조금 더 모으는 중이에요."
DEFAULT_SUMMARY = "이번 관람에서 살펴본 상품을 바탕으로 취향을 정리했어요."


def build_payload(
    *,
    signals: VisitSignals,
    interest: dict[str, float],
    vector: dict[str, float],
    confidence: float,
    type_code: str,
    scored: list[ScoredProduct],
    insight: Insight | None,
) -> dict:
    """프론트가 이 payload 하나만으로 리포트 화면을 그릴 수 있어야 한다."""
    hero, recommendations = _split_hero(scored)
    facts_by_id = {item.facts.product_id: item.facts for item in scored}

    return {
        "character": _character_of(type_code),
        "is_exploring": confidence < scoring.CONFIDENCE_EXPLORING,
        "top_keywords": _top_keywords(vector),
        "summary": insight.summary if insight and insight.summary else DEFAULT_SUMMARY,
        "hero": _card(hero, vector) if hero else None,
        "recommendations": [_card(item, vector) for item in recommendations],
        "interested": _interested(signals, interest, facts_by_id),
        "confidence": confidence,
        "visit_summary": {
            "scenes_viewed": signals.scenes_viewed,
            "products_viewed": len(signals.products),
            "questions": signals.questions,
        },
    }


def _character_of(type_code: str) -> dict:
    """⑦ 캐릭터 조회. 이름과 한 줄 설명만 쓴다.

    이미지는 내려주지 않는다. 사전 제작 16장은 사용자 사진 기반 화보로 대체됐다.
    """
    character = Character.objects.filter(pk=type_code).first()
    if character is None:
        return {
            "type_code": type_code,
            "name": UNKNOWN_CHARACTER_NAME,
            "one_liner": UNKNOWN_CHARACTER_ONE_LINER,
        }
    return {
        "type_code": character.type_code,
        "name": character.name,
        "one_liner": character.one_liner,
    }


def _split_hero(scored: list[ScoredProduct]) -> tuple[ScoredProduct | None, list[ScoredProduct]]:
    """가장 잘 맞는 1개를 크게, 나머지를 그리드로. 프론트가 배열 0번을 꺼내 쓰는
    암묵적 규칙보다 자리를 나눠주는 편이 어긋날 여지가 없다."""
    if not scored:
        return None, []
    return scored[0], scored[1 : 1 + scoring.REPORT_RECOMMENDATION_COUNT]


def _card(item: ScoredProduct, vector: dict[str, float]) -> dict:
    return {
        "product_id": item.facts.product_id,
        "name": item.facts.name,
        "thumbnail": item.facts.thumbnail,
        "price": item.facts.price,
        "external_url": item.facts.external_url,
        "scene_no": item.facts.scene_no,
        "product_no": item.facts.product_no,
        "reason": _recommend_reason(item.facts, vector),
        "score": item.score,
        "is_viewed": item.is_viewed,
    }


def _recommend_reason(facts: ProductFacts, vector: dict[str, float]) -> str:
    """왜 추천했는지를 항상 함께 준다. 근거 없는 추천은 신뢰를 못 얻는다."""
    best = max(
        facts.axis_values(),
        key=lambda pair: vector.get(f"{pair[0]}:{pair[1]}", 0.0),
        default=None,
    )
    if best is None or vector.get(f"{best[0]}:{best[1]}", 0.0) <= 0:
        return "새로 발견할 만한 상품이에요."
    axis, value = best
    return f"선호하신 {axis_label(axis, value)}와(과) 결이 같아요."


def _top_keywords(vector: dict[str, float]) -> list[str]:
    positives = sorted(
        ((key, score) for key, score in vector.items() if score > 0),
        key=lambda pair: (-pair[1], pair[0]),
    )
    return [axis_label(*split_key(key)) for key, _ in positives[: scoring.REPORT_KEYWORD_COUNT]]


def _interested(
    signals: VisitSignals,
    interest: dict[str, float],
    facts_by_id: dict[str, ProductFacts],
) -> list[dict]:
    """관심을 보인 상품과 그렇게 판단한 근거. 수치를 그대로 보여줘야 납득이 된다."""
    ranked = sorted(
        (signal for signal in signals.products if signal.product_id in facts_by_id),
        key=lambda signal: (-interest.get(signal.product_id, 0.0), signal.product_id),
    )
    cards = []
    for signal in ranked[: scoring.REPORT_INTERESTED_COUNT]:
        facts = facts_by_id[signal.product_id]
        cards.append(
            {
                "product_id": facts.product_id,
                "name": facts.name,
                "thumbnail": facts.thumbnail,
                "price": facts.price,
                "external_url": facts.external_url,
                "reason": _interest_reason(signal),
            }
        )
    return cards


def _interest_reason(signal) -> str:
    parts = []
    if signal.dwell_ms:
        parts.append(f"체류 {round(signal.dwell_ms / 1000)}초")
    if signal.views > 1:
        parts.append(f"재조회 {signal.views}회")
    if signal.saves:
        parts.append("찜")
    if signal.chat_mentions:
        parts.append(f"챗봇 대화 {signal.chat_mentions}회")
    return " + ".join(parts) if parts else "상품 조회"
