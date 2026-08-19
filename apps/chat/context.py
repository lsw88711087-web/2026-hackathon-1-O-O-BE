"""프롬프트 조립. 클라이언트가 문맥을 다시 보내지 않아도 서버가 chat_logs에서 만든다.

이게 O&O 챗봇의 핵심이다. 사용자는 "이 상품의 디자이너 의도 설명해줘"처럼
상품명을 말하지 않아도 되고, 서버가 지금 어떤 상품 얘기 중인지 알고 있다.
"""

from apps.analysis import taste as taste_module
from apps.analysis.recommend import Suggestion
from apps.analysis.taste import Taste
from apps.catalog.models import PresetKey, Product
from apps.chat.messages import current_context, timeline
from apps.chat.models import Role
from apps.chat.prompts import (
    CANDIDATE_HEADER,
    CONTEXT_HEADER,
    GUARDRAIL_PROMPT,
    NO_CANDIDATE_NOTE,
    STORE_SCOPE_HEADER,
    SYSTEM_PROMPT,
    TASTE_HEADER,
    TIMELINE_HEADER,
)
from apps.chat.wording import say, say_axis
from apps.visits.models import Visit

TIMELINE_WINDOW = 12  # 프롬프트에 넣는 최근 메시지 수. 토큰을 아끼면서 흐름은 유지한다.

ROLE_TO_OPENAI = {
    Role.USER: "user",
    Role.USER_ACTION: "user",  # 클릭도 손님의 행동이므로 user 쪽에 둔다
    Role.ASSISTANT: "assistant",
    Role.PRESET: "assistant",  # 프리셋 답변도 챗봇이 이미 한 말이다
}


def build_messages(
    visit: Visit,
    question: str,
    override: dict | None = None,
    taste: Taste | None = None,
    candidates: list[Suggestion] | None = None,
) -> list[dict]:
    """system + 상품 문맥 + 취향 좌표 + 추천 후보 + 최근 타임라인 + 이번 질문."""
    context = override or current_context(visit)
    product = _target_product(context)
    taste = taste if taste is not None else taste_module.read(visit)

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.append({"role": "system", "content": _describe_store(visit)})
    if product is not None:
        messages.append({"role": "system", "content": _describe(product)})
    if summary := _describe_taste(taste):
        messages.append({"role": "system", "content": summary})
    if candidates:
        messages.append({"role": "system", "content": _describe_candidates(candidates)})
    elif product is None:
        # 지목할 상품이 하나도 없는 상태. 빈칸을 두면 모델이 지어낸다.
        messages.append({"role": "system", "content": NO_CANDIDATE_NOTE})
    messages.append({"role": "system", "content": _describe_visitor(visit)})
    messages.extend(_recent_turns(visit))
    # 가드레일은 질문 바로 앞에 둔다. 타임라인이 길어지면 앞선 지시가 흐려지고,
    # 조작 문장은 대개 이번 질문 안에 들어온다.
    messages.append({"role": "system", "content": GUARDRAIL_PROMPT})
    messages.append({"role": "user", "content": question})
    return messages


def _describe_taste(taste: Taste) -> str:
    """확정된 축과 유효 축만 넣는다. 애매한 축을 넣으면 LLM이 단정해버린다."""
    lines = [f"- {say_axis(axis)}: {say(value)} (손님이 확인)" for axis, value in taste.locks.items()]
    for axis in taste.valid_axes:
        if axis in taste.locks:
            continue
        values = taste.values.get(axis, {})
        if not values:
            continue
        top = max(values, key=lambda value: values[value])
        if values[top] > 0:
            lines.append(f"- {say_axis(axis)}: {say(top)} 쪽으로 보임")
    return f"{TASTE_HEADER}\n" + "\n".join(lines) if lines else ""


def _describe_candidates(candidates: list[Suggestion]) -> str:
    """후보는 서버가 고른다. LLM은 이 목록 밖의 상품·번호를 말할 수 없다."""
    lines = [
        f"- {item.product.name} ({item.product.scene.no}번 진열대 {item.product.no}번) — {item.reason}"
        for item in candidates
    ]
    return f"{CANDIDATE_HEADER}\n" + "\n".join(lines)


def _describe_store(visit: Visit) -> str:
    """매장의 실제 범위. 상품 문맥과 추천 후보가 모두 없을 때 유일한 사실 근거가 된다.

    이게 없으면 모델이 빈칸을 사전지식으로 채운다 — 다른 브랜드 상품과 없는 진열대
    번호가 나온다. 명품 매장에서 즉시 사고가 되는 종류의 오답이다.
    """
    scenes = list(visit.store.scenes.prefetch_related("products"))
    categories = sorted(
        {product.get_category_display() for scene in scenes for product in scene.products.all()}
    )
    lines = [
        STORE_SCOPE_HEADER,
        f"- 매장 이름: {visit.store.name}",
        "- 진열대: " + " · ".join(f"{scene.no}번 {scene.name}" for scene in scenes),
        "- 취급 분류: " + (" · ".join(categories) if categories else "준비 중"),
        "- 위에 없는 브랜드·상품·진열대 번호는 이 매장에 없습니다.",
    ]
    return "\n".join(lines)


def _target_product(context: dict) -> Product | None:
    product_id = context.get("product_id")
    if not product_id:
        return None
    return Product.objects.select_related("scene").filter(id=product_id).first()


def _describe(product: Product) -> str:
    """상품에 대해 서버가 아는 사실을 전부 넣는다.

    llm_context만 넣었더니 "디자이너 의도는 정보에 없다"는 답이 나왔다. 스토리와
    프리셋 문구에 그 답이 들어 있었다. 프리셋은 브랜드가 직접 작성한 문장이라
    근거로 삼기에 가장 안전하다. 이 내용은 프롬프트 안에서만 쓰이고 응답으로는 나가지 않는다.
    """
    lines = [
        CONTEXT_HEADER,
        f"- 이름: {product.name}",
        f"- 위치: {product.scene.no}번 진열대 {product.no}번",
        f"- 가격: {product.price:,}원",
        f"- 설명: {product.llm_context}",
        f"- 브랜드 스토리: {product.story}",
        f"- 특징: {product.get_color_display()} / {product.get_material_display()} / "
        f"{product.get_pattern_display()} / {product.get_silhouette_display()} / "
        f"{product.get_mood_display()} / {product.get_use_case_display()}",
    ]
    # attributes는 브랜드가 적어 준 표기값이다(색상·소재·치수·사이즈). 분석 축은
    # "그레인 레더"처럼 뭉뚱그린 분류라, 실제 소재명과 치수는 여기에만 있다.
    # 이게 빠지면 "크기 얼마예요?"에 DB를 두고도 직원에게 물어보라고 답한다.
    lines += [f"- {key}: {value}" for key, value in product.attributes.items() if value]
    lines += [
        f"- {PresetKey(key).label}: {answer}"
        for key, answer in product.preset_answers.items()
        if answer and key in PresetKey.values
    ]
    return "\n".join(lines)


def _describe_visitor(visit: Visit) -> str:
    """연령대·성별은 말투를 고르는 참고값이다. 단정적인 추측 근거로 쓰지 않는다."""
    if not visit.age_band and not visit.gender:
        return "손님 정보: 밝히지 않았습니다. 중립적인 말투를 씁니다."
    parts = [visit.get_age_band_display() or "연령대 미상", visit.get_gender_display() or "성별 미상"]
    return f"손님 정보: {' · '.join(parts)}. 말투를 맞추는 참고만 하고 취향을 단정하지 않습니다."


def _recent_turns(visit: Visit) -> list[dict]:
    recent = timeline(visit)[-TIMELINE_WINDOW:]
    turns = [{"role": ROLE_TO_OPENAI[log.role], "content": log.content} for log in recent]
    if not turns:
        return []
    return [{"role": "system", "content": TIMELINE_HEADER}, *turns]
