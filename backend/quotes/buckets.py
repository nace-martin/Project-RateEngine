from __future__ import annotations

from decimal import Decimal
import re


BUCKET_TO_LEG = {
    "origin_charges": "ORIGIN",
    "airfreight": "MAIN",
    "destination_charges": "DESTINATION",
}

PUBLIC_CHARGE_SUBCATEGORY_ORDER = [
    "Customs / Regulatory",
    "Documentation",
    "Pickup / Delivery / Cartage",
    "Handling / Terminal",
    "Freight / Carrier Charges",
    "Carrier Surcharges",
    "Service / Agency Fees",
    "Other Charges",
]

_CATEGORY_TO_PUBLIC_SUBCATEGORY = {
    "CUSTOMS": "Customs / Regulatory",
    "STATUTORY": "Customs / Regulatory",
    "DOCUMENTATION": "Documentation",
    "LOCAL": "Pickup / Delivery / Cartage",
    "HANDLING": "Handling / Terminal",
    "TRANSPORT": "Freight / Carrier Charges",
}

_CUSTOMS_TERMS = (
    "customs",
    "clearance",
    "brokerage",
    "naqia",
    "quarantine",
    "permit",
    "licence",
    "license",
    "inspection",
    "duty",
    "tax",
    "compliance",
)

_DOCUMENTATION_TERMS = (
    "documentation",
    "document",
    "docs",
    "awb",
    "bill of lading",
    "manifest",
)

_PICKUP_DELIVERY_TERMS = (
    "pickup",
    "pick-up",
    "pick up",
    "delivery",
    "cartage",
    "transport",
    "trucking",
    "haulage",
)

_HANDLING_TERMS = (
    "handling",
    "terminal",
    "thc",
    "loading",
    "unloading",
    "forklift",
    "depot",
    "warehouse",
)

_FREIGHT_TERMS = (
    "air freight",
    "ocean freight",
    "sea freight",
    "base freight",
    "carrier freight",
)

_SURCHARGE_TERMS = (
    "fuel surcharge",
    "security surcharge",
    "baf",
    "caf",
    "pss",
    "gri",
    "emergency surcharge",
    "container surcharge",
)

_SERVICE_AGENCY_TERMS = (
    "service fee",
    "admin fee",
    "processing fee",
    "coordination fee",
    "agency fee",
)


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


def resolve_quote_line_sell_value(line, quote_currency: str) -> Decimal:
    """Return the customer-facing sell amount for the quote output currency."""
    currency = str(quote_currency or "PGK").upper()
    if currency != "PGK":
        line_currency = str(getattr(line, "sell_fcy_currency", "") or "").upper()
        if line_currency == currency and getattr(line, "sell_fcy", None) is not None:
            return line.sell_fcy
    return getattr(line, "sell_pgk", None) or Decimal("0")


def should_display_quote_line(line, quote_currency: str) -> bool:
    """Return whether a line should appear in the customer/public breakdown."""
    if getattr(line, "is_informational", False):
        return False
    if getattr(line, "conditional", False):
        return False
    if getattr(line, "is_rate_missing", False):
        return False
    return resolve_quote_line_sell_value(line, quote_currency) > Decimal("0")


def should_include_quote_line_in_subtotal(line, quote_currency: str) -> bool:
    """Return whether a line contributes to customer-facing subtotals/totals."""
    if getattr(line, "is_informational", False):
        return False
    if getattr(line, "conditional", False):
        return False
    if getattr(line, "is_rate_missing", False):
        return False
    return resolve_quote_line_sell_value(line, quote_currency) > Decimal("0")


def _contains_term(value: str, terms: tuple[str, ...]) -> bool:
    return any(re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", value) for term in terms)


def _line_text_value(line) -> str:
    component = getattr(line, "service_component", None)
    values = [
        getattr(line, "cost_source_description", None),
        getattr(line, "description", None),
        getattr(component, "description", None),
    ]
    return " ".join(str(value or "") for value in values).strip().lower()


def _line_metadata_value(line) -> str:
    component = getattr(line, "service_component", None)
    values = [
        getattr(line, "product_code", None),
        getattr(line, "component", None),
        getattr(line, "basis", None),
        getattr(line, "rule_family", None),
        getattr(line, "service_family", None),
        getattr(component, "code", None),
        getattr(component, "category", None),
    ]
    return " ".join(str(value or "") for value in values).replace("_", " ").replace("-", " ").strip().lower()


def classify_quote_line_public_subcategory(line) -> str:
    """Return the customer-facing sub-category for a public quote line."""
    text = _line_text_value(line)
    metadata = _line_metadata_value(line)
    searchable = f"{metadata} {text}".strip()
    leg = resolve_quote_line_leg(line)

    # EFM local cartage fuel must stay with cartage, not carrier surcharges.
    if "cartage" in searchable and "fuel surcharge" in searchable and leg in {"ORIGIN", "DESTINATION"}:
        return "Pickup / Delivery / Cartage"

    # EFM destination agency fee is part of destination customs handling.
    if "agency fee" in searchable and ("dest" in searchable or leg == "DESTINATION"):
        return "Customs / Regulatory"

    component = getattr(line, "service_component", None)
    category = str(getattr(component, "category", "") or "").upper()
    if category in _CATEGORY_TO_PUBLIC_SUBCATEGORY:
        if category == "TRANSPORT" and leg in {"ORIGIN", "DESTINATION"}:
            return "Pickup / Delivery / Cartage"
        return _CATEGORY_TO_PUBLIC_SUBCATEGORY[category]

    if _contains_term(searchable, _CUSTOMS_TERMS):
        return "Customs / Regulatory"
    if _contains_term(searchable, _DOCUMENTATION_TERMS):
        return "Documentation"
    if _contains_term(searchable, _PICKUP_DELIVERY_TERMS):
        return "Pickup / Delivery / Cartage"
    if _contains_term(searchable, _HANDLING_TERMS):
        return "Handling / Terminal"
    if _contains_term(searchable, _FREIGHT_TERMS):
        return "Freight / Carrier Charges"
    if _contains_term(searchable, _SURCHARGE_TERMS):
        return "Carrier Surcharges"
    if _contains_term(searchable, _SERVICE_AGENCY_TERMS):
        return "Service / Agency Fees"

    return "Other Charges"
