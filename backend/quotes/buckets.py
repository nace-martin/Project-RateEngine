from __future__ import annotations


BUCKET_TO_LEG = {
    "origin_charges": "ORIGIN",
    "airfreight": "MAIN",
    "destination_charges": "DESTINATION",
}


def normalize_bucket(raw_bucket) -> str | None:
    value = str(raw_bucket or "").strip().lower()
    return BUCKET_TO_LEG.get(value)


def normalize_leg(raw_leg) -> str | None:
    value = str(raw_leg or "").strip().upper()
    if value in {"ORIGIN", "DESTINATION"}:
        return value
    if value in {"MAIN", "FREIGHT"}:
        return "MAIN"
    return None


def resolve_quote_line_leg(line) -> str:
    """
    Resolve the persisted quote-line leg.

    QuoteLine.bucket/leg is authoritative. ServiceComponent metadata is not,
    because it can be resynced independently of saved quote results.
    """
    return normalize_bucket(getattr(line, "bucket", None)) or normalize_leg(getattr(line, "leg", None)) or "MAIN"
