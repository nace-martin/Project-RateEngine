from urllib.parse import quote as urlquote

from django.conf import settings
from django.core import signing

DEFAULT_PUBLIC_QUOTE_TTL_SECONDS = 60 * 60 * 24 * 7
PUBLIC_QUOTE_TOKEN_SALT = "quote-public-link-v1"


def _get_public_quote_ttl_seconds() -> int:
    value = getattr(settings, "PUBLIC_QUOTE_LINK_TTL_SECONDS", DEFAULT_PUBLIC_QUOTE_TTL_SECONDS)
    try:
        return int(value)
    except (TypeError, ValueError):
        return DEFAULT_PUBLIC_QUOTE_TTL_SECONDS


def build_public_quote_token(quote_id: str) -> str:
    signer = signing.TimestampSigner(salt=PUBLIC_QUOTE_TOKEN_SALT)
    return signer.sign(str(quote_id))


def get_public_quote_id_from_token(token: str) -> str | None:
    signer = signing.TimestampSigner(salt=PUBLIC_QUOTE_TOKEN_SALT)
    try:
        return signer.unsign(token, max_age=_get_public_quote_ttl_seconds())
    except (signing.SignatureExpired, signing.BadSignature):
        return None


def build_public_quote_url(
    quote_id: str,
    version_number: int | None = None,
    summary_only: bool = False,
) -> str:
    base_url = getattr(settings, "FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    token = build_public_quote_token(quote_id)
    query_parts = [f"token={urlquote(token)}"]
    if version_number is not None:
        query_parts.append(f"version={version_number}")
    if summary_only:
        query_parts.append("summary=1")
    return f"{base_url}/public/quote?{'&'.join(query_parts)}"
