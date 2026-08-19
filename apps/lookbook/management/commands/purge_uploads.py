"""오래된 얼굴 사진 정리.

명세의 `photos/ Lifecycle 24시간`을 local 백엔드에서 대신한다. **파일 나이만 본다.**
presign만 받고 안 올렸거나 사진만 올리고 이탈한 경우는 DB에 행이 없어서, 화보 테이블을
훑는 방식으로는 영원히 못 찾는다. 얼굴 사진이라 누락되면 안 된다.

하루 한 번 cron으로 돌린다:
    0 4 * * * /srv/oando/venv/bin/python /srv/oando/manage.py purge_uploads
"""

import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "UPLOAD_RETENTION_HOURS를 넘긴 업로드 사진을 지운다 (local 백엔드 전용)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="지우지 않고 대상만 센다. 처음 돌릴 때 이걸로 확인한다",
        )

    def handle(self, *args, **options):
        root = Path(settings.UPLOAD_LOCAL_ROOT)
        if not root.exists():
            self.stdout.write("업로드 디렉터리가 없습니다. 지울 것도 없습니다.")
            return

        cutoff = time.time() - settings.UPLOAD_RETENTION_HOURS * 3600
        removed = 0
        for path in root.rglob("*"):
            if not path.is_file() or path.stat().st_mtime >= cutoff:
                continue
            if not options["dry_run"]:
                path.unlink(missing_ok=True)
            removed += 1

        if not options["dry_run"]:
            self._prune_empty_dirs(root)

        verb = "지울 대상" if options["dry_run"] else "삭제"
        self.stdout.write(self.style.SUCCESS(f"{verb} {removed}개"))

    def _prune_empty_dirs(self, root: Path) -> None:
        """날짜 디렉터리가 매일 쌓인다. 파일을 지워도 껍데기가 남으면 계속 늘어난다."""
        for path in sorted(root.rglob("*"), key=lambda item: len(item.parts), reverse=True):
            if path.is_dir() and not any(path.iterdir()):
                path.rmdir()
