from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from django.conf import settings
from django.contrib.staticfiles import finders


@dataclass(frozen=True)
class QuoteBrandingContext:
    display_name: str
    support_email: str
    support_phone: str
    website_url: str
    address_lines: list[str]
    quote_footer_text: str
    public_quote_tagline: str
    email_signature_text: str
    primary_color: str
    accent_color: str
    logo_path: Optional[str] = None
    logo_url: Optional[str] = None

    @property
    def primary_color_rgb(self) -> tuple[int, int, int]:
        return _hex_to_rgb(self.primary_color, (15, 42, 86))

    @property
    def accent_color_rgb(self) -> tuple[int, int, int]:
        return _hex_to_rgb(self.accent_color, (215, 25, 32))


def _hex_to_rgb(value: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = str(value or "").strip()
    if not raw:
        return default
    if raw.startswith("#"):
        raw = raw[1:]
    if len(raw) != 6:
        return default
    try:
        return tuple(int(raw[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return default


def _fallback_logo_path() -> Optional[str]:
    try:
        logo_path = finders.find("images/efm_logo_cropped.png")
        if logo_path and Path(logo_path).exists():
            return logo_path

        fallback = Path(settings.BASE_DIR) / "static" / "images" / "efm_logo_cropped.png"
        if fallback.exists():
            return str(fallback)

        new_logo = finders.find("images/efm_logo_new.png")
        if new_logo and Path(new_logo).exists():
            return new_logo

        old_logo = finders.find("images/eac_logo.png")
        if old_logo and Path(old_logo).exists():
            return old_logo
    except Exception:
        return None
    return None


def _resolve_uploaded_logo(logo_field) -> tuple[Optional[str], Optional[str]]:
    if not logo_field:
        return None, None
    file_path = getattr(logo_field, "path", None)
    file_url = getattr(logo_field, "url", None)
    if file_path and Path(file_path).exists():
        return file_path, file_url
    return None, file_url


def get_quote_branding(quote) -> QuoteBrandingContext:
    branding = getattr(getattr(quote, "organization", None), "branding", None)
    organization = getattr(quote, "organization", None)

    display_name = getattr(branding, "display_name", "") or getattr(organization, "name", "") or "EFM Express Air Cargo"
    support_email = getattr(branding, "support_email", "") or "quotes@efmexpress.com"
    support_phone = getattr(branding, "support_phone", "") or "+675 325 8500"
    website_url = getattr(branding, "website_url", "") or ""
    address_lines = [
        line.strip()
        for line in str(getattr(branding, "address_lines", "") or "PO Box 1791\nPort Moresby\nPapua New Guinea").splitlines()
        if line.strip()
    ]
    quote_footer_text = getattr(branding, "quote_footer_text", "") or ""
    public_quote_tagline = getattr(branding, "public_quote_tagline", "") or f"Quote from {display_name}"
    email_signature_text = getattr(branding, "email_signature_text", "") or ""
    primary_color = getattr(branding, "primary_color", "") or "#0F2A56"
    accent_color = getattr(branding, "accent_color", "") or "#D71920"

    uploaded_logo_path, uploaded_logo_url = _resolve_uploaded_logo(getattr(branding, "logo_primary", None))
    logo_path = uploaded_logo_path or _fallback_logo_path()

    return QuoteBrandingContext(
        display_name=display_name,
        support_email=support_email,
        support_phone=support_phone,
        website_url=website_url,
        address_lines=address_lines,
        quote_footer_text=quote_footer_text,
        public_quote_tagline=public_quote_tagline,
        email_signature_text=email_signature_text,
        primary_color=primary_color,
        accent_color=accent_color,
        logo_path=logo_path,
        logo_url=uploaded_logo_url,
    )

