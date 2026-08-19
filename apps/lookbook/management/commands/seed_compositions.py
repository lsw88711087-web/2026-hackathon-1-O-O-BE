"""구도 4종 시드. 전 무드가 공용으로 쓰는 고정 마스터다.

프롬프트와 레퍼런스를 코드가 아니라 DB에 두는 이유는 **톤 조정에 배포가 필요 없게**
하려는 것이다. 이 명령은 빈 칸만 채우고, 사람이 admin에서 고친 값은 덮어쓰지 않는다.
`--force`를 줘야 시안 기준으로 되돌린다.

레퍼런스 이미지는 기획 시안에서 왔다. 시안마다 구도가 다르고(클로즈업·전신·반신·상반신),
그 차이가 곧 이 4행이다. 배경 색 변형은 구도가 아니라 무드라서 prompts.MOODS가 맡는다.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.lookbook.models import Composition

# 명세 "구도 선택" 표. 사진에 맞는 구도만 후보에 넣어야 왜곡이 안 생긴다.
# reference_url은 media/references/ 아래 파일명. 파일이 없으면 참조 없이 생성된다.
COMPOSITIONS = [
    {
        "code": "close_up",
        "name": "클로즈업",
        "min_face": 0.15,
        "max_face": 1.00,
        "reference": "close_up.png",
        "prompt": (
            "Composition: a tight close-up portrait, the face filling most of the frame, "
            "shot at eye level with shallow depth of field."
        ),
    },
    {
        "code": "half_body",
        "name": "상반신",
        "min_face": 0.05,
        "max_face": 0.35,
        "reference": "half_body.png",
        "prompt": (
            "Composition: a half-body shot from the waist up, three-quarter turn toward "
            "the camera, high-contrast editorial lighting."
        ),
    },
    {
        "code": "wide",
        "name": "와이드",
        "min_face": 0.00,
        "max_face": 0.15,
        "reference": "wide.png",
        "prompt": (
            "Composition: a full-body standing shot with generous headroom, wide framing, "
            "the whole outfit visible against a plain backdrop."
        ),
    },
    {
        "code": "product_focus",
        "name": "상품 중심",
        "min_face": 0.00,
        "max_face": 1.00,
        "reference": "product_focus.png",
        "prompt": (
            "Composition: a waist-up shot with the product held toward the camera so it "
            "is the largest and sharpest element in the frame."
        ),
    },
]

REFERENCE_DIR = "/media/references/"


class Command(BaseCommand):
    help = "화보 구도 4종을 채운다 (사람이 고친 값은 덮어쓰지 않는다)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="admin에서 고친 프롬프트·레퍼런스까지 시안 기준으로 되돌린다",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        created = updated = 0
        for item in COMPOSITIONS:
            composition, is_new = Composition.objects.get_or_create(
                code=item["code"],
                defaults={
                    "name": item["name"],
                    "min_face": item["min_face"],
                    "max_face": item["max_face"],
                },
            )
            created += is_new

            fields = []
            if is_new or options["force"] or not composition.prompt:
                composition.prompt = item["prompt"]
                fields.append("prompt")
            if is_new or options["force"] or not composition.reference_url:
                composition.reference_url = REFERENCE_DIR + item["reference"]
                fields.append("reference_url")
            if fields:
                composition.save(update_fields=[*fields, "updated_at"])
                updated += not is_new

        self.stdout.write(
            self.style.SUCCESS(f"구도 {len(COMPOSITIONS)}종 확인 (신규 {created}건 · 갱신 {updated}건)")
        )
        self.stdout.write("레퍼런스 파일을 MEDIA_ROOT/references/ 아래에 두어야 참조가 걸립니다.")
