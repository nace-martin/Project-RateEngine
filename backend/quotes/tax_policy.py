# quotes/tax_policy.py
from typing import Dict

def apply_gst_policy(version, charge) -> None:
    """
    Mutates `charge.is_taxable` and `charge.gst_percentage` in place.

    Rules (MVP):
      - AIR (international linehaul): 0% GST
      - PNG (PG)
        * IMPORT/DOMESTIC: ORIGIN/DESTINATION services in PG -> 10%
        * EXPORT: ORIGIN services in PG -> 0% if export_evidence=True else 10%
      - Outside PG (e.g., AU): 0% (out-of-scope for MVP unless you add that jurisdiction)
      - Disbursements (duty/import GST/etc.): 0%
    """
    # 0) Defaults
    charge.is_taxable = False
    charge.gst_percentage = 0

    # 1) Disbursements / pass-through codes: always non-taxable on recharge
    # Adjust this set as you standardize your codes
    non_tax_codes = {"DUTY", "IMPORT_GST", "AQIS", "DAU", "ICS", "DISB"}
    code = (charge.code or "").upper()
    if code in non_tax_codes:
        return  # leave at 0%

    # 2) AIR (international linehaul): 0%
    if charge.stage == "AIR":
        return

    # 3) Work out jurisdiction from stage
    #    ORIGIN -> origin.country_code; DESTINATION -> destination.country_code
    if charge.stage == "ORIGIN":
        country = version.origin.country_code
    elif charge.stage == "DESTINATION":
        country = version.destination.country_code
    else:
        country = None  # Unknown -> stay 0%

    # 4) PNG logic
    if country == "PG":
        svc = version.quotation.service_type  # IMPORT / EXPORT / DOMESTIC
        if svc in ("IMPORT", "DOMESTIC"):
            # Services supplied in PNG -> 10%
            charge.is_taxable = True
            charge.gst_percentage = 10
            return

        if svc == "EXPORT":
            # Origin services in PNG directly connected to export can be zero-rated
            # flag lives in policy_snapshot: {"export_evidence": true/false}
            export_evidence = bool(version.policy_snapshot.get("export_evidence", False))
            if charge.stage == "ORIGIN":
                if export_evidence:
                    # zero-rated with evidence
                    return
                else:
                    charge.is_taxable = True
                    charge.gst_percentage = 10
                    return
            # destination stage for an export is typically outside PG; if it is PG keep default 0 unless you choose otherwise.
        return

    # 5) Non-PNG (e.g., AU) — for MVP treat as out-of-scope (0%)
    # If/when you register in AU, extend rules here.
    return
