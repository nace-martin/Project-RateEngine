"""Controlled creation of ONE same-code ServiceComponent (Pilot Gate B3H).

The V4 adapter turns an engine charge into a quote line only when a
``ServiceComponent`` with the same code as the ProductCode exists; otherwise it
logs a warning and drops the line. ``sync_v4_components`` is the only existing
creator, and it upserts every ProductCode (and the SPOT defaults) in one pass,
which is far too broad to run for a single reviewed charge.

This loader plans, and only when explicitly asked applies, exactly one
ServiceComponent from a strict JSON manifest:

- dry run is the default and never writes;
- every outcome is CREATE, REUSE or CONFLICT, and only CREATE writes;
- apply is atomic, idempotent and insert-only: a stored row is never updated;
- the proposed fields must equal what ``sync_v4_components`` would derive for
  the ProductCode, so a later broad sync is a no-op for this row;
- no other ServiceComponent, ProductCode, rate, or pricing row is touched.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from django.db import transaction

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.management.commands.sync_v4_components import infer_component_leg
from pricing_v4.models import ProductCode
from pricing_v4.services.rate_matrix_manifest import (
    ManifestParseError,
    parse_manifest_text,
    read_only_database,
)
from services.models import (
    AUDIENCE_CHOICES,
    CATEGORY_CHOICES,
    COST_SOURCE_CHOICES,
    COST_TYPE_CHOICES,
    LEG_CHOICES,
    MODE_CHOICES,
    UNIT_CHOICES,
    ServiceComponent,
)

MANIFEST_VERSION = 1

CREATE = "CREATE"
REUSE = "REUSE"
CONFLICT = "CONFLICT"

TOP_KEYS = ("manifest_version", "service_components")
ENTRY_KEYS = (
    "code", "description", "mode", "leg", "category", "cost_type", "cost_source", "unit", "audience",
    "is_active", "evidence",
)
CHOICES = {
    "mode": MODE_CHOICES, "leg": LEG_CHOICES, "category": CATEGORY_CHOICES, "cost_type": COST_TYPE_CHOICES,
    "cost_source": COST_SOURCE_CHOICES, "unit": UNIT_CHOICES, "audience": AUDIENCE_CHOICES,
}

# Mirrors the category map inside sync_v4_components.Command.handle (it is a local there). A test
# runs the real command and compares, so this cannot drift silently.
SYNC_CATEGORY_MAP = {
    "FREIGHT": "TRANSPORT",
    "DOCUMENTATION": "DOCUMENTATION",
    "REGULATORY": "DOCUMENTATION",
    "CUSTOMS": "CUSTOMS",
    "CARTAGE": "LOCAL",
    "SURCHARGE": "ACCESSORIAL",
}

# Columns the manifest does not state take the model defaults. They are compared on REUSE, so an
# existing row carrying anything else is a CONFLICT rather than being silently accepted.
UNSTATED_DEFAULTS = {
    "base_pgk_cost": Decimal("0.00"),
    "cost_currency_type": "PGK",
    "min_charge_pgk": None,
    "tiering_json": None,
    "tax_code": None,
    "tax_rate": Decimal("0.0000"),
    "percent_of_component_id": None,
    "percent_value": None,
    "service_code_id": None,
}


class ComponentApplyError(RuntimeError):
    """Apply was refused or failed verification. Nothing was written."""


@dataclass
class ComponentPlan:
    manifest_sha256: str = ""
    manifest_errors: list[dict[str, str]] = field(default_factory=list)
    action: str | None = None
    code: str = ""
    evidence: str = ""
    fields: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    mode: str = "DRY_RUN"
    applied: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return not self.manifest_errors and self.action in (CREATE, REUSE)

    def counts(self) -> dict[str, int]:
        return {a: 1 if self.action == a else 0 for a in (CREATE, REUSE, CONFLICT)}

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "manifest_sha256": self.manifest_sha256,
            "result": "READY" if self.ready else "NOT READY",
            "counts": self.counts(),
            "manifest_errors": self.manifest_errors,
            "record": {
                "kind": "ServiceComponent", "identity": self.code, "action": self.action,
                "evidence": self.evidence, "fields": self.fields, "reasons": self.reasons,
                "details": self.details,
            },
            "writes_performed": self.applied["rows_created"] if self.applied else 0,
            "applied": self.applied,
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def render_text(self) -> str:
        counts = self.counts()
        mode = "APPLY" if self.mode == "APPLY" else "DRY RUN (plan only; no rows are written)"
        out = [
            "ServiceComponent mirror plan",
            f"Mode: {mode}",
            f"Manifest sha256: {self.manifest_sha256}",
            "",
            f"CREATE {counts[CREATE]}   REUSE {counts[REUSE]}   CONFLICT {counts[CONFLICT]}",
        ]
        if self.manifest_errors:
            out += ["", f"Manifest errors ({len(self.manifest_errors)})"]
            out += [f"  [{e['code']}] {e['path']}: {e['message']}" for e in self.manifest_errors]
        if self.action:
            out += ["", f"ServiceComponent [{self.action}] {self.code}"]
            out += [f"      - {detail}" for detail in self.details]
            out += [f"      ! {reason}" for reason in self.reasons]
            out.append(f"      evidence: {self.evidence}")
        out += ["", f"Result: {'READY' if self.ready else 'NOT READY'}"]
        if self.mode == "APPLY" and self.applied is not None:
            out.append(f"Applied by {self.applied['operator']}: {self.applied['rows_created']} row(s) created.")
        elif self.mode == "APPLY":
            out.append("Apply refused. Nothing was written.")
        else:
            out.append("Writes performed: 0")
        return "\n".join(out)


def plan_component_text(text: str, *, using: str = "default") -> ComponentPlan:
    """Dry run: parse and plan inside a read-only, rolled-back transaction."""
    plan = ComponentPlan(manifest_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    with read_only_database(using):
        _plan(text, plan, using)
    return plan


def apply_component_text(text: str, *, operator, reviewed_sha256: str, using: str = "default") -> ComponentPlan:
    """Create the component atomically. Refuses unless the plan is CREATE or REUSE."""
    if operator is None or not getattr(operator, "is_active", False):
        raise ComponentApplyError("Apply requires an active operator account.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if reviewed_sha256 != digest:
        raise ComponentApplyError(
            "The manifest does not match the reviewed dry run (sha256 differs). Nothing was written."
        )
    plan = ComponentPlan(manifest_sha256=digest, mode="APPLY")
    created = 0
    with transaction.atomic(using=using):
        _plan(text, plan, using)
        if not plan.ready:
            transaction.set_rollback(True, using=using)
            return plan
        if plan.action == CREATE:
            component = ServiceComponent(**plan.fields, **UNSTATED_DEFAULTS)
            component.full_clean()
            component.save(using=using, force_insert=True)
            created = 1
        # Idempotency proof: planning again must find the stored row identical.
        check = ComponentPlan()
        _plan(text, check, using)
        if check.manifest_errors or check.action != REUSE:
            raise ComponentApplyError(
                "Post-apply verification failed; rolled back. "
                f"Plan after apply was {check.action}: {'; '.join(check.reasons) or 'no detail'}"
            )
    plan.applied = {"operator": operator.get_username(), "rows_created": created}
    return plan


def _plan(text: str, plan: ComponentPlan, using: str) -> None:
    def error(code: str, path: str, message: str) -> None:
        plan.manifest_errors.append({"code": code, "path": path, "message": message})

    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        error("MANIFEST_NOT_STRICT_JSON", "$", str(exc))
        return
    entry = _entry(data, error)
    if entry is None:
        return

    plan.code = entry["code"]
    plan.evidence = entry["evidence"]
    plan.fields = {key: entry[key] for key in ENTRY_KEYS if key != "evidence"}
    reasons = _prerequisite_problems(entry, using)
    existing = ServiceComponent.objects.using(using).filter(code=entry["code"]).first()

    if existing is not None:
        differing = sorted(
            [key for key in plan.fields if getattr(existing, key) != plan.fields[key]]
            + [key for key, default in UNSTATED_DEFAULTS.items() if getattr(existing, key) != default]
        )
        if differing:
            reasons.append(
                f"Stored ServiceComponent '{existing.code}' differs in: {', '.join(differing)}. "
                "Stored rows are never updated."
            )
        if reasons:
            plan.action, plan.reasons = CONFLICT, reasons
        else:
            plan.action = REUSE
            plan.details.append("Stored ServiceComponent is identical; nothing to create.")
        return

    taken = ServiceComponent.objects.using(using).filter(description=entry["description"]).first()
    if taken is not None:
        reasons.append(f"Description is already used by ServiceComponent '{taken.code}' (descriptions are unique).")
    if reasons:
        plan.action, plan.reasons = CONFLICT, reasons
        return
    plan.action = CREATE
    plan.details.append("Same code as ProductCode and CommercialProductCode; no other row is created or changed.")


def _entry(data: Any, error) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        error("MANIFEST_TYPE", "$", "Expected a JSON object.")
        return None
    ok = True
    for key in TOP_KEYS:
        if key not in data:
            error("MANIFEST_MISSING_FIELD", f"$.{key}", "Required field is missing; every field must be explicit.")
            ok = False
    for key in sorted(set(data) - set(TOP_KEYS)):
        error("MANIFEST_UNKNOWN_FIELD", f"$.{key}", "Field is not part of the manifest contract.")
        ok = False
    if not ok:
        return None
    if data["manifest_version"] != MANIFEST_VERSION or isinstance(data["manifest_version"], bool):
        error("MANIFEST_VERSION", "$.manifest_version", f"Only manifest_version {MANIFEST_VERSION} is supported.")
        return None
    entries = data["service_components"]
    if not isinstance(entries, list):
        error("MANIFEST_TYPE", "$.service_components", "Expected a JSON array.")
        return None
    if len(entries) != 1:
        error(
            "SERVICE_COMPONENT_COUNT", "$.service_components",
            f"Exactly one ServiceComponent is permitted per manifest; found {len(entries)}.",
        )
        return None

    path = "$.service_components[0]"
    entry = entries[0]
    if not isinstance(entry, dict):
        error("MANIFEST_TYPE", path, "Expected a JSON object.")
        return None
    for key in ENTRY_KEYS:
        if key not in entry:
            error("MANIFEST_MISSING_FIELD", f"{path}.{key}", "Required field is missing; every field must be explicit.")
            ok = False
    for key in sorted(set(entry) - set(ENTRY_KEYS)):
        error("MANIFEST_UNKNOWN_FIELD", f"{path}.{key}", "Field is not part of the manifest contract.")
        ok = False
    if not ok:
        return None

    for key in ("code", "description", "evidence", *CHOICES):
        value = entry[key]
        if not isinstance(value, str) or not value or value != value.strip():
            error("VALUE_INVALID", f"{path}.{key}", "Expected a trimmed, non-blank string.")
            ok = False
    if not isinstance(entry["is_active"], bool):
        error("VALUE_INVALID", f"{path}.is_active", "Expected true or false.")
        ok = False
    if not ok:
        return None
    if len(entry["code"]) > 20 or entry["code"] != entry["code"].upper():
        error("VALUE_INVALID", f"{path}.code", "Expected an upper-case code of at most 20 characters.")
        ok = False
    if len(entry["description"]) > 255:
        error("VALUE_INVALID", f"{path}.description", "Description exceeds 255 characters.")
        ok = False
    for key, choices in CHOICES.items():
        if entry[key] not in {value for value, _label in choices}:
            error("VALUE_NOT_ALLOWED", f"{path}.{key}", f"'{entry[key]}' is not a valid {key}.")
            ok = False
    return entry if ok else None


def _prerequisite_problems(entry: dict[str, Any], using: str) -> list[str]:
    """Reasons the component cannot be created or reused. Empty means it is compatible."""
    code = entry["code"]
    legacy = ProductCode.objects.using(using).filter(code=code).first()
    if legacy is None:
        return [f"No legacy ProductCode has code '{code}'. A component is only created for an existing ProductCode."]
    reasons = []
    if not legacy.is_active or legacy.retired_at is not None:
        reasons.append(f"Legacy ProductCode {legacy.id} ({code}) is inactive or retired.")
    mirror = CommercialProductCode.objects.using(using).filter(code=code).first()
    if mirror is None:
        reasons.append(f"No CommercialProductCode '{code}' exists; load the master data first.")
    elif mirror.legacy_product_code_id != legacy.id or not mirror.is_active:
        reasons.append(
            f"CommercialProductCode '{code}' is not an active mirror of legacy ProductCode {legacy.id}."
        )

    # The row must be exactly what sync_v4_components would write, so a later broad sync is a no-op.
    description = legacy.description
    if ServiceComponent.objects.using(using).filter(description=description).exclude(code=code).exists():
        description = f"{description} (V4)"
    derived = {
        "description": description, "mode": "AIR", "leg": infer_component_leg(legacy),
        "category": SYNC_CATEGORY_MAP.get(legacy.category, "ACCESSORIAL"), "cost_type": "COGS",
        "cost_source": "BASE_COST", "unit": legacy.default_unit if legacy.default_unit in ("KG", "SHIPMENT") else "SHIPMENT",
        "is_active": True,
    }
    for key, value in derived.items():
        if entry[key] != value:
            reasons.append(
                f"{key} '{entry[key]}' differs from what sync_v4_components derives ('{value}'); "
                "a later sync would overwrite it."
            )
    return reasons
