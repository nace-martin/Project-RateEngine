from __future__ import annotations

import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Inspect the active media storage backend and optionally perform a write/delete "
        "round-trip to verify uploads will persist."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--write-test",
            action="store_true",
            help="Write and delete a small test file using Django's default storage backend.",
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Media storage configuration"))
        self.stdout.write(f"- Storage backend: {default_storage.__class__.__module__}.{default_storage.__class__.__name__}")
        self.stdout.write(f"- MEDIA_ROOT: {settings.MEDIA_ROOT}")
        self.stdout.write(f"- MEDIA_URL: {settings.MEDIA_URL}")

        media_root = Path(settings.MEDIA_ROOT)
        self.stdout.write(f"- MEDIA_ROOT exists: {media_root.exists()}")
        self.stdout.write(f"- MEDIA_ROOT is directory: {media_root.is_dir()}")

        if options["write_test"]:
            self._write_test()

    def _write_test(self):
        test_name = f"storage-check/{uuid.uuid4()}.txt"
        payload = b"rateengine media storage check"
        saved_name = None
        try:
            saved_name = default_storage.save(test_name, ContentFile(payload))
            exists_after_write = default_storage.exists(saved_name)
            self.stdout.write(f"- Write test saved: {saved_name}")
            self.stdout.write(f"- Exists after write: {exists_after_write}")
            if not exists_after_write:
                raise CommandError("Write test failed: saved file is not visible in storage.")
        finally:
            if saved_name and default_storage.exists(saved_name):
                default_storage.delete(saved_name)
                self.stdout.write(f"- Deleted test file: {saved_name}")
