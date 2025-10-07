from typing import Optional, Tuple, Dict
from pricing_v2.types_v2 import PaymentTerm, OrgType

def resolve_currency_and_fee_scope(
    scope: str,
    payment_term: PaymentTerm,
    payer: Optional[Dict],  # Expects {"org_type": "...", "country_iso2": "..."}
) -> Tuple[str, str, str]:
    """
    The 'Rule Expert'. Determines the correct currency and fee scope based on facts.
    Returns: (invoice_currency, fee_scope, reason)
    """
    fee_scope = "ORIGIN_ONLY" if "A2A" in scope else "DESTINATION_ONLY"

    # For Imports (A2D), the rule is simple and based on payment term
    if "A2D" in scope:
        ccy = "AUD" if payment_term == PaymentTerm.PREPAID else "PGK"
        return (ccy, "DESTINATION_ONLY", f"import A2D: {payment_term} -> {ccy}")

    # For Exports, we need the payer's details to determine the currency
    if not payer:
        return ("", fee_scope, "export: payer details are required to resolve currency")

    org_type = payer.get("org_type")
    country = (payer.get("country_iso2") or "").upper()

    if org_type == OrgType.OVERSEAS_AGENT:
        ccy = "AUD" if country == "AU" else "USD"
        reason = f"export: payer is an overseas agent in {country or 'N/A'} -> {ccy}"
    elif org_type in (OrgType.PNG_SHIPPER, OrgType.PNG_CUSTOMER):
        ccy = "PGK"
        reason = "export: payer is a PNG shipper/customer -> PGK"
    else:
        ccy = "USD"  # A safe fallback for any other foreign payer
        reason = f"export: defaulted unknown payer type -> {ccy}"

    return (ccy, fee_scope, reason)