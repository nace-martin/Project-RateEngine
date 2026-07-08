from __future__ import annotations

from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.utils import IntegrityError

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
        "gl_revenue_code": "4400",
        "gl_cost_code": "5400",
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
        "gl_revenue_code": "4400",
        "gl_cost_code": "5400",
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
        "apply_scope": False,
    },
    {
        "item": "fsc ANY/ANY",
        "reason": "Broad FSC alias is ambiguous across airline, pickup, cartage, and domestic fuel.",
        "apply_scope": False,
    },
    {
        "item": "handling generic",
        "reason": "Generic handling is ambiguous across origin and destination handling.",
        "apply_scope": False,
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
    apply_blockers = _apply_blockers(product_actions, alias_actions, conflicts, warnings)
    plan = {
        "status": "blocked" if apply_blockers else "ready_for_apply",
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
            "apply_blocker_count": len(apply_blockers),
            "warning_count": len(warnings),
        },
        "product_code_actions": product_actions,
        "charge_alias_actions": alias_actions,
        "conflicts": conflicts,
        "apply_blockers": apply_blockers,
        "blocked": BLOCKED_DECISIONS,
        "warnings": warnings,
        "recommended_next_actions": [
            "Run dry-run first and review product_code_actions, charge_alias_actions, conflicts, and apply_blockers.",
            "Use --apply only in the approved environment after dry-run output is ready_for_apply.",
            "Keep miscellaneous recoveries, broad fsc, and generic handling out of apply scope.",
        ],
    }
    return plan


def apply_air_freight_pilot_seed_plan() -> dict[str, Any]:
    plan = build_air_freight_pilot_seed_plan()
    if plan["apply_blockers"]:
        return {**plan, "status": "apply_aborted", "applied": _empty_apply_summary("apply blockers present")}

    created_product_codes = []
    created_charge_aliases = []
    try:
        with transaction.atomic():
            for action in plan["product_code_actions"]:
                if action["action"] != "create":
                    continue
                candidate = action["candidate"]
                product_code = ProductCode(**{**candidate, "gst_rate": Decimal(candidate["gst_rate"])})
                product_code.full_clean()
                product_code.save(force_insert=True)
                created_product_codes.append(product_code.code)

            for action in plan["charge_alias_actions"]:
                if action["action"] not in {"create", "create_after_product_code"}:
                    continue
                product_code = ProductCode.objects.filter(code=action["product_code"]).first()
                if not product_code:
                    raise RuntimeError(f"target ProductCode {action['product_code']} is missing")
                alias = ChargeAlias(
                    alias_text=action["alias_text"],
                    normalized_alias_text=action["normalized_alias_text"],
                    match_type=action["match_type"],
                    mode_scope=action["mode_scope"],
                    direction_scope=action["direction_scope"],
                    product_code=product_code,
                    alias_source=ChargeAlias.AliasSource.SEED,
                    review_status=ChargeAlias.ReviewStatus.APPROVED,
                    is_active=True,
                    notes="Phase 13.1H Air Freight pilot seed apply",
                )
                alias.full_clean()
                alias.save(force_insert=True)
                created_charge_aliases.append(alias.alias_text)
    except (IntegrityError, RuntimeError, ValidationError) as exc:
        return {**build_air_freight_pilot_seed_plan(), "status": "apply_aborted", "applied": _empty_apply_summary(str(exc))}

    return {
        **build_air_freight_pilot_seed_plan(),
        "status": "applied",
        "applied": {
            "product_codes_created": len(created_product_codes),
            "charge_aliases_created": len(created_charge_aliases),
            "created_product_codes": created_product_codes,
            "created_charge_aliases": created_charge_aliases,
        },
    }


def render_air_freight_pilot_seed_plan_text(plan: dict[str, Any]) -> str:
    summary = plan["summary"]
    lines = [
        f"Air Freight pilot seed plan: {plan['status']}",
        f"ProductCodes create/reuse/conflict: {summary['product_code_create']}/{summary['product_code_reuse']}/{summary['product_code_conflict']}",
        f"ChargeAliases create/dependent/skip/blocked/conflict: {summary['charge_alias_create']}/{summary['charge_alias_create_after_product_code']}/{summary['charge_alias_skip']}/{summary['charge_alias_blocked']}/{summary['charge_alias_conflict']}",
        f"Blocked: {summary['blocked_count']}",
        f"Apply blockers: {summary['apply_blocker_count']}",
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
        mismatches = _product_code_mismatches(existing_code, candidate)
        if mismatches:
            return {
                "action": "conflict",
                "candidate": candidate,
                "existing_id": existing_code.id,
                "reason": f"existing ProductCode differs on {', '.join(mismatches)}",
                "validation": validation,
            }
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
        if not exact.is_active or exact.review_status != ChargeAlias.ReviewStatus.APPROVED:
            return {
                **action,
                "action": "conflict",
                "existing_id": exact.id,
                "reason": "existing scoped alias is not active and approved",
            }
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


def _product_code_mismatches(existing: ProductCode, candidate: dict[str, Any]) -> list[str]:
    fields = [
        "id",
        "description",
        "domain",
        "category",
        "default_unit",
        "is_gst_applicable",
        "gst_treatment",
        "gl_revenue_code",
        "gl_cost_code",
    ]
    mismatches = [field for field in fields if getattr(existing, field) != candidate[field]]
    if existing.gst_rate != Decimal(candidate["gst_rate"]):
        mismatches.append("gst_rate")
    return mismatches


def _apply_blockers(
    product_actions: list[dict[str, Any]],
    alias_actions: list[dict[str, Any]],
    conflicts: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    blockers = [{"type": "conflict", "item": item} for item in conflicts]
    for action in product_actions:
        for error in action["validation"]["errors"]:
            blockers.append({"type": "validation_error", "product_code": action["candidate"]["code"], "field": error})
    blockers.extend({"type": "placeholder_gl", "item": warning} for warning in warnings)
    blockers.extend({"type": "missing_target", "item": item} for item in alias_actions if item["action"] == "blocked")
    blockers.extend({"type": "blocked_decision", "item": item} for item in BLOCKED_DECISIONS if item.get("apply_scope", True))
    return blockers


def _empty_apply_summary(reason: str) -> dict[str, Any]:
    return {
        "product_codes_created": 0,
        "charge_aliases_created": 0,
        "created_product_codes": [],
        "created_charge_aliases": [],
        "reason": reason,
    }


def _count(actions: list[dict[str, Any]], action: str) -> int:
    return sum(1 for item in actions if item["action"] == action)
