import mimetypes
import os
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
ALLOWED_IMAGE_FORMATS = {"GIF", "JPEG", "PNG", "WEBP"}
ALLOWED_PDF_CONTENT_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "binary/octet-stream",
}
ALLOWED_CSV_CONTENT_TYPES = {
    "application/csv",
    "application/octet-stream",
    "application/vnd.ms-excel",
    "text/csv",
    "text/plain",
}


def get_request_ip(request) -> str:
    forwarded_for = str(request.META.get("HTTP_X_FORWARDED_FOR", "") or "").strip()
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", "") or "").strip() or "unknown"


def get_upload_limit_bytes(setting_name: str, default_mb: int) -> int:
    raw_value = getattr(settings, setting_name, default_mb * 1024 * 1024)
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{setting_name} must be an integer number of bytes.") from exc
    if value < 1:
        raise ValidationError(f"{setting_name} must be greater than zero.")
    return value


def guess_content_type(file_name: str, fallback: str = "application/octet-stream") -> str:
    guessed, _ = mimetypes.guess_type(file_name)
    return guessed or fallback


def validate_csv_upload(uploaded_file, *, setting_name: str = "CSV_UPLOAD_MAX_BYTES", default_mb: int = 5) -> None:
    _validate_named_upload(
        uploaded_file,
        allowed_extensions={".csv"},
        allowed_content_types=ALLOWED_CSV_CONTENT_TYPES,
        max_size_bytes=get_upload_limit_bytes(setting_name, default_mb),
        file_label="CSV file",
    )


def validate_pdf_upload(uploaded_file, *, setting_name: str = "PDF_UPLOAD_MAX_BYTES", default_mb: int = 10) -> None:
    _validate_named_upload(
        uploaded_file,
        allowed_extensions={".pdf"},
        allowed_content_types=ALLOWED_PDF_CONTENT_TYPES,
        max_size_bytes=get_upload_limit_bytes(setting_name, default_mb),
        file_label="PDF file",
    )
    _verify_pdf_signature(uploaded_file)


def validate_image_upload(uploaded_file, *, setting_name: str = "IMAGE_UPLOAD_MAX_BYTES", default_mb: int = 2) -> None:
    _validate_named_upload(
        uploaded_file,
        allowed_extensions={".gif", ".jpeg", ".jpg", ".png", ".webp"},
        allowed_content_types=ALLOWED_IMAGE_CONTENT_TYPES,
        max_size_bytes=get_upload_limit_bytes(setting_name, default_mb),
        file_label="Image file",
    )
    _verify_image(uploaded_file)


def _validate_named_upload(uploaded_file, *, allowed_extensions: set[str], allowed_content_types: set[str], max_size_bytes: int, file_label: str) -> None:
    if uploaded_file is None:
        raise ValidationError(f"{file_label} is required.")

    file_name = os.path.basename(str(getattr(uploaded_file, "name", "") or "").strip())
    if not file_name:
        raise ValidationError(f"{file_label} must include a file name.")
    uploaded_file.name = file_name

    suffix = Path(file_name).suffix.lower()
    if suffix not in allowed_extensions:
        allowed = ", ".join(sorted(allowed_extensions))
        raise ValidationError(f"{file_label} must use one of these extensions: {allowed}.")

    size_bytes = int(getattr(uploaded_file, "size", 0) or 0)
    if size_bytes <= 0:
        raise ValidationError(f"{file_label} is empty.")
    if size_bytes > max_size_bytes:
        raise ValidationError(
            f"{file_label} exceeds the maximum allowed size of {max_size_bytes // (1024 * 1024)} MB."
        )

    content_type = str(getattr(uploaded_file, "content_type", "") or "").strip().lower()
    if content_type and content_type not in allowed_content_types:
        raise ValidationError(f"{file_label} content type '{content_type}' is not allowed.")


def _verify_pdf_signature(uploaded_file) -> None:
    position = uploaded_file.tell()
    try:
        signature = uploaded_file.read(5)
        if signature != b"%PDF-":
            raise ValidationError("Uploaded file is not a valid PDF.")
    finally:
        uploaded_file.seek(position)


def _verify_image(uploaded_file) -> None:
    position = uploaded_file.tell()
    try:
        with Image.open(uploaded_file) as image:
            image.verify()
            image_format = str(image.format or "").upper()
        if image_format not in ALLOWED_IMAGE_FORMATS:
            raise ValidationError("Uploaded image format is not allowed.")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValidationError("Uploaded image file is invalid or corrupted.") from exc
    finally:
        uploaded_file.seek(position)
