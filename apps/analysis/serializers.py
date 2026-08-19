from rest_framework import serializers

from apps.events.serializers import EventItemSerializer, validate_batch_size


class FinishRequestSerializer(serializers.Serializer):
    """바디는 비어 있어도 된다. events는 프론트에 남은 버퍼를 동봉하는 용도다.

    종료되면 토큰이 쓰기 권한을 잃으므로, 버퍼를 `/events`로 따로 보내면 401을 맞고
    관람 직전 구간이 통째로 사라진다. 동봉하면 요청이 하나라 레이스도 없다.
    """

    events = EventItemSerializer(many=True, required=False, default=list)

    def validate_events(self, value: list[dict]) -> list[dict]:
        return validate_batch_size(value)


class FinishResponseSerializer(serializers.Serializer):
    slug = serializers.CharField(help_text="리포트 주소. 추측하기 어려운 값이다")
    status = serializers.CharField(help_text="pending / ready / failed")
    events = serializers.DictField(
        help_text="동봉한 이벤트의 accepted · duplicated · ignored · rejected. "
        "rejected가 0이 아니면 버퍼가 한 번에 저장하는 수를 넘긴 것이므로, "
        "다음부터는 /finish 전에 /events로 미리 비워야 한다"
    )


class ReportDetailSerializer(serializers.Serializer):
    """박제된 리포트. status가 ready일 때만 나머지 필드가 들어 있다.

    payload를 재계산하지 않고 그대로 흘려보내므로, 몇 번을 열어도 같은 화면이 나온다.
    """

    status = serializers.CharField(help_text="pending / ready / failed")
    character = serializers.DictField(required=False, help_text="type_code · name · one_liner")
    top_keywords = serializers.ListField(required=False)
    summary = serializers.CharField(required=False)
    hero = serializers.DictField(required=False, allow_null=True, help_text="가장 잘 맞는 상품 1개")
    recommendations = serializers.ListField(required=False)
    interested = serializers.ListField(required=False)
    confidence = serializers.FloatField(required=False, help_text="0~1")
    is_exploring = serializers.BooleanField(
        required=False, help_text="true면 신호가 적어 '탐색 중'으로 표시한다. 프론트는 이 값으로 분기한다"
    )
    visit_summary = serializers.DictField(required=False)
