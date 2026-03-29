from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Iterator


def file_field_storage_exists(file_field) -> bool:
    if not file_field:
        return False

    file_name = str(getattr(file_field, "name", "") or "").strip()
    if not file_name:
        return False

    storage = getattr(file_field, "storage", None)
    if storage is not None:
        try:
            return bool(storage.exists(file_name))
        except Exception:
            pass

    try:
        file_path = getattr(file_field, "path", None)
    except Exception:
        file_path = None
    return bool(file_path and os.path.exists(file_path))


def file_field_basename(file_field) -> str:
    file_name = str(getattr(file_field, "name", "") or "").strip()
    return os.path.basename(file_name)


@contextmanager
def materialize_file_field(file_field) -> Iterator[str | None]:
    if not file_field_storage_exists(file_field):
        yield None
        return

    try:
        file_path = getattr(file_field, "path", None)
    except Exception:
        file_path = None

    if file_path and os.path.exists(file_path):
        yield file_path
        return

    file_name = str(getattr(file_field, "name", "") or "").strip()
    suffix = Path(file_name).suffix
    temp_path = None
    with file_field.storage.open(file_name, "rb") as source:
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = temp_file.name
            for chunk in source.chunks() if hasattr(source, "chunks") else iter(lambda: source.read(64 * 1024), b""):
                if not chunk:
                    break
                temp_file.write(chunk)

    try:
        yield temp_path
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)
