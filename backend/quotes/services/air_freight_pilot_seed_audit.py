from __future__ import annotations

from typing import Any

from django.apps import apps
from django.db.models import Q


CANONICAL_ORGANIZATION = "Express Freight Management"
OPERATING_ENTITIES = [
    {"code": "PNG", "name": "EFM PNG"},
    {"code": "AUS", "name": "EFM Australia"},
    {"code": "FJI", "name": "EFM Fiji"},
    {"code": "SLB", "name": "EFM Solomon Islands"},
]
BRANCHES = [
    {"code": "POM", "name": "Port Moresby"},
    {"code": "LAE", "name": "Lae"},
    {"code": "BNE", "name": "Brisbane"},
    {"code": "SUV", "name": "Suva"},
    {"code": "HIR", "name": "Honiara"},
]
DEPARTMENTS = [
    {"code": "AIR", "name": "Air Freight"},
    {"code": "SEA", "name": "Sea Freight"},
    {"code": "CUS", "name": "Customs"},
    {"code": "TRN", "name": "Transport"},
]
ROLES = ["admin", "manager", "sales", "finance"]
PRODUCT_COVERAGE = [
    {"key": "air_freight", "label": "Air Freight", "terms": ["air freight", "freight"]},
    {"key": "fuel_surcharge", "label": "Fuel surcharge", "terms": ["fuel", "fsc"]},
    {"key": "security_surcharge", "label": "Security surcharge", "terms": ["security"]},
    {"key": "screening", "label": "Screening", "terms": ["screening"]},
    {"key": "awb_docs", "label": "AWB / documentation", "terms": ["awb", "documentation", "docs"]},
    {"key": "import_handling", "label": "Import handling", "terms": ["import handling", "import destination handling"]},
    {"key": "export_handling", "label": "Export handling", "terms": ["export handling"]},
    {"key": "origin_handling", "label": "Origin handling", "terms": ["origin handling"]},
    {"key": "destination_handling", "label": "Destination handling", "terms": ["destination handling"]},
    {"key": "storage_warehouse", "label": "Storage / warehouse", "terms": ["storage", "warehouse"]},
    {"key": "customs_pass_through", "label": "Customs pass-through", "terms": ["customs", "clearance"]},
    {"key": "misc_recoveries", "label": "Miscellaneous recoveries", "terms": ["misc", "recovery", "recoveries"]},
]
ALIASES = [
    "air freight",
    "freight",
    "fsc",
    "fuel surcharge",
    "security surcharge",
    "screening",
    "awb",
    "documentation fee",
    "terminal fee",
    "handling",
    "import handling",
    "export handling",
    "storage",
]
LOCATION_CODES = ["POM", "LAE", "BNE", "SYD", "SIN", "HKG", "NRT", "LAX", "AKL"]
CURRENCY_CODES = ["PGK", "USD", "AUD", "SGD", "EUR"]


def build_air_freight_pilot_seed_audit() -> dict[str, Any]:
    audit = _empty_audit()
    _audit_hierarchy(audit)
    _audit_roles_memberships(audit)
    _audit_product_codes(audit)
    _audit_charge_aliases(audit)
    _audit_locations(audit)
    _audit_currencies(audit)
    _audit_pilot_data(audit)
    _finish(audit)
    return audit


def render_air_freight_pilot_seed_audit_text(audit: dict[str, Any]) -> str:
    lines = [
        f"Air Freight pilot seed audit: {audit['status']}",
        f"Missing: {len(audit['missing'])}",
        f"Conflicts: {len(audit['conflicts'])}",
        f"Warnings: {len(audit['warnings'])}",
        "",
        "Recommended next actions:",
    ]
    lines.extend(f"- {item}" for item in audit["recommended_next_actions"])
    return "\n".join(lines) + "\n"


def _empty_audit() -> dict[str, Any]:
    return {
        "status": "not_ready",
        "summary": {},
        "hierarchy": {},
        "roles_memberships": {},
        "product_codes": {},
        "charge_aliases": {},
        "locations": {},
        "currencies": {},
        "pilot_data": {},
        "conflicts": [],
        "missing": [],
        "warnings": [],
        "recommended_next_actions": [],
    }


def _model(app_label: str, model_name: str, audit: dict[str, Any]):
    try:
        return apps.get_model(app_label, model_name)
    except LookupError:
        audit["warnings"].append(f"Model {app_label}.{model_name} is not available; skipped that audit section.")
        return None


def _audit_hierarchy(audit: dict[str, Any]) -> None:
    Organization = _model("parties", "Organization", audit)
    OperatingEntity = _model("parties", "OperatingEntity", audit)
    Branch = _model("parties", "Branch", audit)
    Department = _model("parties", "Department", audit)
    if not all([Organization, OperatingEntity, Branch, Department]):
        return

    orgs = list(Organization.objects.filter(name=CANONICAL_ORGANIZATION).values("id", "name", "is_active"))
    org = orgs[0] if len(orgs) == 1 else None
    if not org:
        _missing(audit, "hierarchy.organization", CANONICAL_ORGANIZATION)
    if len(orgs) > 1:
        _conflict(audit, "hierarchy.organization", f"Multiple organizations named {CANONICAL_ORGANIZATION}.")

    org_id = org["id"] if org else None
    org_active = bool(org and org["is_active"])
    if org and not org_active:
        _missing(audit, "hierarchy.organization", f"{CANONICAL_ORGANIZATION} active row")

    audit["hierarchy"] = {
        "organization": {"name": CANONICAL_ORGANIZATION, "exists": org_active, "is_active": org_active},
        "operating_entities": _check_scoped_rows(OperatingEntity, org_id, OPERATING_ENTITIES, audit, "hierarchy.operating_entities"),
        "branches": _check_scoped_rows(Branch, org_id, BRANCHES, audit, "hierarchy.branches"),
        "departments": _check_scoped_rows(Department, org_id, DEPARTMENTS, audit, "hierarchy.departments"),
    }


def _check_scoped_rows(model, org_id, expected: list[dict[str, str]], audit: dict[str, Any], path: str) -> dict[str, Any]:
    rows = []
    if not org_id:
        for item in expected:
            _missing(audit, path, item["code"])
            rows.append({**item, "exists": False})
        return {"items": rows, "missing_count": len(expected)}

    for item in expected:
        matches = list(model.objects.filter(organization_id=org_id, code=item["code"]).values("id", "code", "name", "is_active"))
        is_active = bool(matches and matches[0]["is_active"])
        exists = len(matches) == 1 and is_active
        if not exists:
            _missing(audit, path, item["code"])
        if len(matches) > 1:
            _conflict(audit, path, f"Multiple {model.__name__} rows for code {item['code']}.")
        rows.append({**item, "exists": exists, "is_active": is_active, "actual_name": matches[0]["name"] if matches else None})
    return {"items": rows, "missing_count": sum(1 for row in rows if not row["exists"])}


def _audit_roles_memberships(audit: dict[str, Any]) -> None:
    Role = _model("accounts", "Role", audit)
    UserMembership = _model("accounts", "UserMembership", audit)
    if not all([Role, UserMembership]):
        return

    role_rows = []
    for code in ROLES:
        matches = list(Role.objects.filter(code__iexact=code, is_active=True).values("id", "code", "name", "is_system", "organization_id"))
        if not matches:
            _missing(audit, "roles_memberships.roles", code)
        if len(matches) > 1:
            _conflict(audit, "roles_memberships.roles", f"Multiple active roles match {code}.")
        role_rows.append({"code": code, "exists": bool(matches), "matches": len(matches)})

    active = UserMembership.objects.filter(is_active=True)
    missing_primary = active.exclude(user_id__in=active.filter(is_primary=True).values("user_id")).values("user_id").distinct().count()
    incomplete = {
        "missing_organization": active.filter(organization__isnull=True).count(),
        "missing_operating_entity": active.filter(operating_entity__isnull=True).count(),
        "missing_branch": active.filter(branch__isnull=True).count(),
        "missing_department": active.filter(department__isnull=True).count(),
        "missing_role": active.filter(role__isnull=True).count(),
        "missing_primary": missing_primary,
    }
    for key, count in incomplete.items():
        if count:
            audit["warnings"].append(f"{count} active membership(s) have {key.replace('_', ' ')}.")

    audit["roles_memberships"] = {
        "roles": role_rows,
        "active_memberships": active.count(),
        "primary_memberships": active.filter(is_primary=True).count(),
        "incomplete_counts": incomplete,
    }


def _audit_product_codes(audit: dict[str, Any]) -> None:
    ProductCode = _model("pricing_v4", "ProductCode", audit)
    if not ProductCode:
        return

    rows = {}
    for coverage in PRODUCT_COVERAGE:
        query = Q()
        for term in coverage["terms"]:
            query |= Q(code__icontains=term) | Q(description__icontains=term)
        matches = list(ProductCode.objects.filter(query).values("id", "code", "description", "domain", "category", "default_unit").order_by("id"))
        if not matches:
            _missing(audit, "product_codes", coverage["key"])
        if len(matches) > 1:
            _conflict(audit, "product_codes", f"{coverage['label']} has {len(matches)} possible ProductCodes; review mapping.")
        rows[coverage["key"]] = {"label": coverage["label"], "exists": bool(matches), "matches": matches}

    audit["product_codes"] = {"coverage": rows, "missing_count": sum(1 for row in rows.values() if not row["exists"])}


def _audit_charge_aliases(audit: dict[str, Any]) -> None:
    ChargeAlias = _model("pricing_v4", "ChargeAlias", audit)
    if not ChargeAlias:
        return

    rows = {}
    for alias in ALIASES:
        normalized = ChargeAlias.normalize_alias_text_value(alias)
        matches = list(
            ChargeAlias.objects.filter(normalized_alias_text=normalized, is_active=True)
            .values("id", "alias_text", "normalized_alias_text", "product_code_id", "match_type", "mode_scope", "direction_scope")
            .order_by("id")
        )
        if not matches:
            _missing(audit, "charge_aliases", alias)
        if len({row["product_code_id"] for row in matches}) > 1:
            _conflict(audit, "charge_aliases", f"Alias {alias!r} maps to multiple ProductCodes.")
        rows[alias] = {"exists": bool(matches), "matches": matches}
    audit["charge_aliases"] = {"aliases": rows, "missing_count": sum(1 for row in rows.values() if not row["exists"])}


def _audit_locations(audit: dict[str, Any]) -> None:
    Airport = _model("core", "Airport", audit)
    Location = _model("core", "Location", audit)
    if not all([Airport, Location]):
        return

    rows = {}
    for code in LOCATION_CODES:
        airport_exists = Airport.objects.filter(iata_code=code).exists()
        locations = list(Location.objects.filter(code=code).values("id", "code", "name", "kind", "airport_id"))
        exists = airport_exists or bool(locations)
        if not exists:
            _missing(audit, "locations", code)
        if len(locations) > 1:
            _conflict(audit, "locations", f"Multiple Location rows found for {code}.")
        rows[code] = {"exists": exists, "airport_exists": airport_exists, "location_count": len(locations), "locations": locations}
    audit["locations"] = {"items": rows, "missing_count": sum(1 for row in rows.values() if not row["exists"])}


def _audit_currencies(audit: dict[str, Any]) -> None:
    Currency = _model("core", "Currency", audit)
    if not Currency:
        return

    rows = {}
    for code in CURRENCY_CODES:
        exists = Currency.objects.filter(code=code).exists()
        if not exists:
            _missing(audit, "currencies", code)
        rows[code] = {"exists": exists}
    audit["currencies"] = {"items": rows, "missing_count": sum(1 for row in rows.values() if not row["exists"])}


def _audit_pilot_data(audit: dict[str, Any]) -> None:
    Company = _model("parties", "Company", audit)
    if not Company:
        return

    obvious = Company.objects.filter(Q(name__icontains="pilot") | Q(name__icontains="demo") | Q(name__icontains="sample"))
    audit["pilot_data"] = {
        "obvious_pilot_demo_company_count": obvious.count(),
        "contains_sensitive_details": False,
        "note": "Only counts are reported; customer/supplier names are intentionally omitted.",
    }


def _finish(audit: dict[str, Any]) -> None:
    audit["summary"] = {
        "missing_count": len(audit["missing"]),
        "conflict_count": len(audit["conflicts"]),
        "warning_count": len(audit["warnings"]),
    }
    if audit["conflicts"] or audit["missing"]:
        audit["status"] = "not_ready"
    elif audit["warnings"]:
        audit["status"] = "ready_with_warnings"
    else:
        audit["status"] = "ready"

    if audit["missing"]:
        audit["recommended_next_actions"].append("Review missing reference data before Air Freight UAT.")
    if audit["conflicts"]:
        audit["recommended_next_actions"].append("Resolve conflicts before adding any seed/apply command.")
    if not audit["missing"] and not audit["conflicts"]:
        audit["recommended_next_actions"].append("Run this audit in staging and attach JSON output to the UAT gate.")


def _missing(audit: dict[str, Any], section: str, item: str) -> None:
    audit["missing"].append({"section": section, "item": item})


def _conflict(audit: dict[str, Any], section: str, detail: str) -> None:
    audit["conflicts"].append({"section": section, "detail": detail})
