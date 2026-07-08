from __future__ import annotations

from typing import Any

from pricing_v4.models import ChargeAlias, ProductCode


PRODUCT_CODE_CANDIDATES = [
    {
        "id": 2042,
        "code": "IMP-HANDLE-DEST",
        "description": "Import Destination Handling",
        "domain": ProductCode.DOMAIN_IMPORT,
        "category": ProductCode.CATEGORY_HANDLING,
        "default_unit": ProductCode.UNIT_SHIPMENT,
        "is_gst_applicable": True,
        "gst_rate": "0.1000",
        "gst_treatment": ProductCode.GST_TREATMENT_STANDARD,
        "gl_revenue_code": "TBD-REV",
        "gl_cost_code": "TBD-COS",
    },
    {
        "id": 2043,
        "code": "IMP-STORAGE-DEST",
        "description": "Import Destination Storage / Warehouse",
        "domain": ProductCode.DOMAIN_IMPORT,
        "category": ProductCode.CATEGORY_HANDLING,
        "default_unit": ProductCode.UNIT_SHIPMENT,
        "is_gst_applicable": True,
        "gst_rate": "0.1000",
        "gst_treatment": ProductCode.GST_TREATMENT_STANDARD,
        "gl_revenue_code": "TBD-REV",
        "gl_cost_code": "TBD-COS",
    },
]

ALIAS_CANDIDATES = [
    ("freight", "EXPORT", "MAIN", "EXP-FRT-AIR"),
    ("freight", "IMPORT", "MAIN", "IMP-FRT-AIR"),
    ("freight", "DOMESTIC", "MAIN", "DOM-FRT-AIR"),
    ("fuel surcharge", "EXPORT", "MAIN", "EXP-FSC-AIR"),
    ("fuel surcharge", "IMPORT", "ORIGIN", "IMP-FSC-PICKUP"),
    ("fuel surcharge", "IMPORT", "DESTINATION", "IMP-FSC-CARTAGE-DEST"),
    ("security surcharge", "EXPORT", "ORIGIN", "EXP-SCREEN"),
    ("security surcharge", "IMPORT", "ORIGIN", "IMP-SEC-ORIGIN"),
    ("screening", "EXPORT", "ORIGIN", "EXP-SCREEN"),
    ("screening", "IMPORT", "ORIGIN", "IMP-SEC-ORIGIN"),
    ("awb", "EXPORT", "ORIGIN", "EXP-AWB"),
    ("awb", "IMPORT", "ORIGIN", "IMP-AWB-ORIGIN"),
    ("awb", "DOMESTIC", "ORIGIN", "DOM-AWB"),
    ("export handling", "EXPORT", "ORIGIN", "EXP-HANDLE"),
    ("import handling", "IMPORT", "DESTINATION", "IMP-HANDLE-DEST"),
    ("storage", "IMPORT", "DESTINATION", "IMP-STORAGE-DEST"),
]

BLOCKED_DECISIONS = [
    {
        "item": "misc_recoveries",
        "reason": "Phase 13.1D deferred broad miscellaneous recoveries to manual review.",
    },
    {
        "item": "fsc ANY/ANY",
        "reason": "Broad FSC alias is ambiguous across airline, pickup, cartage, and domestic fuel.",
    },
    {
        "item": "handling generic",
        "reason": "Generic handling is ambiguous across origin and destination handling.",
    },
]


def build_air_freight_pilot_seed_plan() -> dict[str, Any]:
    product_actions = [_product_code_action(row) for row in PRODUCT_CODE_CANDIDATES]
    planned_product_codes = {
        action["candidate"]["code"]
        for action in product_actions
        if action["action"] == "create"
    }
    alias_actions = [_alias_action(*row, planned_product_codes) for row in ALIAS_CANDIDATES]
    conflicts = [item for item in product_actions + alias_actions if item["action"] == "conflict"]
    warnings = _placeholder_warnings(product_actions)
    plan = {
        "status": "blocked" if conflicts or BLOCKED_DECISIONS else "ready_for_dry_run_review",
        "summary": {
            "product_code_create": _count(product_actions, "create"),
            "product_code_reuse": _count(product_actions, "reuse"),
            "product_code_conflict": _count(product_actions, "conflict"),
            "charge_alias_create": _count(alias_actions, "create"),
            "charge_alias_create_after_product_code": _count(alias_actions, "create_after_product_code"),
            "charge_alias_skip": _count(alias_actions, "skip_existing"),
            "charge_alias_blocked": _count(alias_actions, "blocked"),
            "charge_alias_conflict": _count(alias_actions, "conflict"),
            "blocked_count": len(BLOCKED_DECISIONS) + _count(alias_actions, "blocked"),
            "warning_count": len(warnings),
        },
        "product_code_actions": product_actions,
        "charge_alias_actions": alias_actions,
        "conflicts": conflicts,
        "blocked": BLOCKED_DECISIONS,
        "warnings": warnings,
        "recommended_next_actions": [
            "Review GL placeholders and GST treatment before any apply-mode phase.",
            "Resolve blocked broad aliases before adding any write command.",
            "Keep Phase 13.1E dry-run only; no seed writes are available.",
        ],
    }
    return plan


def render_air_freight_pilot_seed_plan_text(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        f"Air Freight pilot seed plan: {plan['status']}",
        f"ProductCodes create/reuse/conflict: {summary['product_code_create']}/{summary['product_code_reuse']}/{summary['product_code_conflict']}",
        f"ChargeAliases create/dependent/skip/blocked/conflict: {summary['charge_alias_create']}/{summary['charge_alias_create_after_product_code']}/{summary['charge_alias_skip']}/{summary['charge_alias_blocked']}/{summary['charge_alias_conflict']}",
        f"Blocked: {summary['blocked_count']}",
        f"Warnings: {summary['warning_count']}",
        "",
        "Recommended next actions:",
    ]
    lines.extend(f"- {item}" for item in plan["recommended_next_actions"])
    return "\n".join(lines) + "\n"


def _product_code_action(candidate: dict[str, Any]) -> dict[str, Any]:
    existing_code = ProductCode.objects.filter(code=candidate["code"]).first()
    existing_id = ProductCode.objects.filter(id=candidate["id"]).first()
    validation = _validate_product_code_candidate(candidate)
    if existing_code:
        return {"action": "reuse", "candidate": candidate, "existing_id": existing_code.id, "validation": validation}
    if existing_id:
        return {
            "action": "conflict",
            "candidate": candidate,
            "reason": f"id {candidate['id']} already belongs to {existing_id.code}",
            "validation": validation,
        }
    return {"action": "create", "candidate": candidate, "validation": validation}


def _alias_action(
    alias_text: str,
    mode_scope: str,
    direction_scope: str,
    product_code_code: str,
    planned_product_codes: set[str],
) -> dict[str, Any]:
    normalized = ChargeAlias.normalize_alias_text_value(alias_text)
    target = ProductCode.objects.filter(code=product_code_code).first()
    action = {
        "alias_text": alias_text,
        "normalized_alias_text": normalized,
        "match_type": ChargeAlias.MatchType.EXACT,
        "mode_scope": mode_scope,
        "direction_scope": direction_scope,
        "product_code": product_code_code,
    }
    if not target:
        if product_code_code in planned_product_codes:
            return {
                **action,
                "action": "create_after_product_code",
                "depends_on_product_code": product_code_code,
            }
        return {**action, "action": "blocked", "reason": f"target ProductCode {product_code_code} does not exist yet"}

    exact = ChargeAlias.objects.filter(
        normalized_alias_text=normalized,
        match_type=ChargeAlias.MatchType.EXACT,
        mode_scope=mode_scope,
        direction_scope=direction_scope,
        product_code=target,
    ).first()
    if exact:
        return {**action, "action": "skip_existing", "existing_id": exact.id}

    conflict = ChargeAlias.objects.filter(
        normalized_alias_text=normalized,
        match_type=ChargeAlias.MatchType.EXACT,
        mode_scope=mode_scope,
        direction_scope=direction_scope,
        is_active=True,
    ).exclude(product_code=target).first()
    if conflict:
        return {
            **action,
            "action": "conflict",
            "existing_id": conflict.id,
            "reason": f"active scoped alias already targets ProductCode id {conflict.product_code_id}",
        }
    return {**action, "action": "create"}


def _validate_product_code_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
    valid = []
    errors = []
    warnings = []
    if 2000 <= candidate["id"] < 3000 and candidate["domain"] == ProductCode.DOMAIN_IMPORT:
        valid.append("id_range")
    else:
        errors.append("id_range")
    for field, allowed in [
        ("domain", dict(ProductCode.DOMAIN_CHOICES)),
        ("category", dict(ProductCode.CATEGORY_CHOICES)),
        ("default_unit", dict(ProductCode.UNIT_CHOICES)),
        ("gst_treatment", dict(ProductCode.GST_TREATMENT_CHOICES)),
    ]:
        (valid if candidate[field] in allowed else errors).append(field)
    for field in ["gl_revenue_code", "gl_cost_code"]:
        if candidate[field]:
            valid.append(field)
        else:
            errors.append(field)
        if str(candidate[field]).startswith("TBD"):
            warnings.append(f"{field} is placeholder")
    return {"valid": valid, "errors": errors, "warnings": warnings}


def _placeholder_warnings(actions: list[dict[str, Any]]) -> list[str]:
    warnings = []
    for action in actions:
        for warning in action["validation"]["warnings"]:
            warnings.append(f"{action['candidate']['code']}: {warning}")
    return warnings


def _count(actions: list[dict[str, Any]], action: str) -> int:
    return sum(1 for item in actions if item["action"] == action)
