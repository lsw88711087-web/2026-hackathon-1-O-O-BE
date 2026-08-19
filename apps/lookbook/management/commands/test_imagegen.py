"""화보 합성을 실제로 한 장 뽑아본다. 벤더 연동 점검용.

**DB도 워커도 거치지 않는다.** 리포트·방문·상품을 만들지 않고 벤더 호출만 떼어내
확인한다. 여기서 성공하면 남은 건 배선 문제고, 실패하면 키·크레딧·마스크 중 하나다.

    manage.py test_imagegen --photo 얼굴사진.jpg
    manage.py test_imagegen --photo 얼굴사진.jpg --mask 마스크.png --quality low

⚠️ 실제로 과금된다. 기본 quality는 settings 값을 따르고 --quality로 낮출 수 있다.
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.lookbook import compose, prompts
from apps.lookbook.models import Composition
from common import imagegen

# 벤더를 부르기 전에 끊는다. 키가 없는데 사진부터 읽으면 원인이 흐려진다.
QUALITY_CHOICES = ("low", "medium", "high", "auto")


class Command(BaseCommand):
    help = "사진 한 장으로 화보 합성을 시험한다 (실제 과금 발생)."

    def add_arguments(self, parser):
        parser.add_argument("--photo", required=True, help="얼굴이 나온 사진 (jpg/png/webp)")
        parser.add_argument("--mask", default="", help="인물 실루엣 PNG. 없으면 마스크 없이 생성")
        parser.add_argument(
            "--reference", default="", help="구도 레퍼런스 이미지 파일. --composition보다 우선"
        )
        parser.add_argument(
            "--composition",
            default="",
            help="DB의 구도 코드(close_up/half_body/wide/product_focus). 레퍼런스와 프롬프트를 그대로 쓴다",
        )
        parser.add_argument("--product-image", default="", help="배경 제거된 상품 PNG")
        parser.add_argument("--quality", default="", choices=["", *QUALITY_CHOICES], help="낮출수록 싸다")
        parser.add_argument("--out", default="lookbook_test.png", help="결과 저장 경로")
        parser.add_argument("--product", default="MCM 비세토스 토트백", help="화보에 넣을 상품 이름")
        parser.add_argument("--attempt", type=int, default=1, help="2 이상이면 자세·구도를 흔든다")
        parser.add_argument(
            "--cutout",
            action="store_true",
            help="벤더를 부르지 않고 마스크로 인물만 오려 배경판에 얹는다 (--mask 필요)",
        )
        parser.add_argument(
            "--raw",
            action="store_true",
            help="레이아웃 합성을 건너뛰고 AI 결과 그대로 저장한다 (인물 사진만 확인할 때)",
        )

    def handle(self, *args, **options):
        # 누끼 모드는 벤더를 안 부르므로 키가 없어도 된다.
        if not options["cutout"] and not settings.OPENAI_API_KEY:
            raise CommandError("OPENAI_API_KEY가 없습니다. .env에 넣고 다시 실행하세요.")

        photo = self._read(options["photo"], "사진")
        mask = self._read(options["mask"], "마스크") if options["mask"] else None
        composition = self._composition(options["composition"])

        reference_path = options["reference"] or self._reference_path(composition)
        reference = self._read(reference_path, "레퍼런스") if reference_path else None
        product_image = (
            self._read(options["product_image"], "상품 이미지") if options["product_image"] else None
        )

        # 순서가 계약이다. worker._generate와 같은 순서로 넣어야 프롬프트의 번호가 맞는다.
        references = [item for item in (reference, product_image) if item]

        prompt = prompts.build(
            # 리포트 payload에 mood가 아직 없어서 실제 워커도 빈 dict를 넘긴다.
            # 여기서 가짜로 채우면 실제보다 좋은 결과가 나와 판단이 흐려진다.
            mood={},
            composition_prompt=composition.prompt if composition else "",
            product_names=[options["product"]],
            venue=settings.LOOKBOOK_VENUE,
            season=settings.LOOKBOOK_SEASON,
            seed=7,
            attempt=options["attempt"],
            has_reference=bool(reference),
            has_product_image=bool(product_image),
        )

        if options["cutout"]:
            # 마스크가 없으면 오릴 수가 없다. 그래도 레이아웃은 확인할 수 있어야 해서
            # 사진을 그대로 얹는다 — 인물이 사각형으로 들어가는 게 정상이다.
            if mask is None:
                self.stdout.write(
                    self.style.WARNING("마스크가 없어 누끼를 못 땁니다. 사진을 사각형 그대로 얹습니다.")
                )
            person = compose.cutout(photo, mask) if mask else photo
            self._save(options, person, product_image, elapsed=0.0)
            return

        quality = options["quality"] or settings.LOOKBOOK_GEN_QUALITY
        self.stdout.write(
            f"모델   {settings.LOOKBOOK_IMAGE_MODEL} · {settings.LOOKBOOK_GEN_SIZE} · {quality}"
        )
        self.stdout.write(f"마스크 {'있음' if mask else '없음 (배경 전체가 새로 그려진다)'}")
        self.stdout.write(f"구도   {composition.code if composition else '없음'}")
        self.stdout.write(f"참조   {reference_path or '없음'}")
        self.stdout.write(f"상품   {options['product_image'] or '이름만'}")
        self.stdout.write(f"프롬프트\n  {prompt}\n")
        self.stdout.write("생성 중...")

        started = time.monotonic()
        try:
            png = imagegen.edit(
                photo=photo, mask=mask, references=references, prompt=prompt, quality=quality
            )
        except imagegen.ImageGenError as error:
            raise CommandError(f"[{error.error_code}] {error}") from error

        # 상품은 벤더 결과에 이미 들어 있다. 누끼 경로에서만 따로 얹는다.
        self._save(options, png, None, time.monotonic() - started)

    def _save(self, options: dict, person: bytes, product: bytes | None, elapsed: float) -> None:
        """레이아웃을 얹어 저장한다. --raw면 인물 이미지를 그대로 남긴다."""
        final = (
            person
            if options["raw"]
            else compose.build(
                person=person,
                product=product,
                caption={
                    "muse_label": "N.011",
                    "venue": settings.LOOKBOOK_VENUE,
                    "season": settings.LOOKBOOK_SEASON,
                },
                size=settings.LOOKBOOK_IMAGE_SIZE,
            )
        )

        out = Path(options["out"])
        out.write_bytes(final)
        width, height = imagegen.size_of(final)

        self.stdout.write(
            self.style.SUCCESS(f"성공: {out} · {width}x{height} · {len(final) / 1024:.0f}KB")
        )
        self.stdout.write(f"소요 {elapsed:.1f}초 (LOOKBOOK_EXPECTED_SEC={settings.LOOKBOOK_EXPECTED_SEC})")
        if elapsed > settings.LOOKBOOK_EXPECTED_SEC * 1.5:
            self.stdout.write(
                self.style.WARNING(
                    f"실측이 예상치보다 훨씬 깁니다. LOOKBOOK_EXPECTED_SEC를 {round(elapsed)}쯤으로 "
                    "올리지 않으면 로딩 화면이 90%에서 오래 멈춰 있습니다."
                )
            )

    def _composition(self, code: str) -> Composition | None:
        if not code:
            return None
        composition = Composition.objects.filter(code=code).first()
        if composition is None:
            raise CommandError(f"그런 구도가 없습니다: {code}")
        return composition

    def _reference_path(self, composition: Composition | None) -> str:
        """구도에 걸린 레퍼런스를 MEDIA_ROOT 아래 실제 경로로 바꾼다."""
        if composition is None or not composition.reference_url:
            return ""
        relative = composition.reference_url.removeprefix(settings.MEDIA_URL).removeprefix("/")
        return str(Path(settings.MEDIA_ROOT) / relative)

    def _read(self, path: str, label: str) -> bytes:
        file = Path(path)
        if not file.exists():
            raise CommandError(f"{label} 파일이 없습니다: {file}")
        return file.read_bytes()
