"""Controlled creation of the Pilot export ServiceComponent twins (Pilot Gate B3M-E).

The V4 adapter turns an engine charge into a quote line only when a ``ServiceComponent`` with the same
code as the ProductCode exists. Rate Matrix export pricing treats a missing twin as a pricing failure,
so the twelve Pilot ``EXP-*`` twins must exist before the flag is turned on.

This is a thin, idempotent wrapper over the single-component loader
(``pricing_v4.services.service_component_mirror``). It derives one strict manifest per Pilot code from the
stored legacy ProductCode exactly as ``sync_v4_components`` would, plans each through the existing loader,
and applies them in one transaction:

- dry run is the default and never writes;
- every outcome is CREATE, REUSE or CONFLICT; only CREATE writes, and a CONFLICT writes nothing at all;
- stored rows are never updated;
- the set must be reviewed: apply requires the combined sha256 printed by the dry run.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from django.db import transaction

from pricing_v4.management.commands.sync_v4_components import infer_component_leg
from pricing_v4.models import ProductCode
from pricing_v4.services.service_component_mirror import (
    AUDIENCE_DEFAULT,
    CONFLICT,
    CREATE,
    MANIFEST_VERSION,
    REUSE,
    SYNC_CATEGORY_MAP,
    ComponentApplyError,
    ComponentPlan,
    apply_component_text,
    plan_component_text,
)
from services.models import ServiceComponent

PILOT_EXPORT_CODES = (
    "EXP-FRT-AIR", "EXP-FSC-AIR", "EXP-DOC", "EXP-AWB", "EXP-CLEAR", "EXP-AGENCY", "EXP-TERM",
    "EXP-BUILDUP", "EXP-HANDLE", "EXP-SCREEN", "EXP-PICKUP", "EXP-FSC-PICKUP",
)
EVIDENCE = (
    "Pilot Gate B3M-E: same-code ServiceComponent twin required by Rate Matrix export pricing; "
    "fields are exactly what sync_v4_components derives from the ProductCode."
)


class ExportComponentError(RuntimeError):
    """The twin set cannot be planned or applied. Nothing was written."""


@dataclass
class ComponentSetPlan:
    mode: str = "DRY_RUN"
    plans: list[tuple[str, ComponentPlan]] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    applied: dict[str, Any] | None = None

    @property
    def combined_sha256(self) -> str:
        digest = hashlib.sha256()
        for code, plan in sorted(self.plans):
            digest.update(f"{code}:{plan.manifest_sha256}\n".encode("utf-8"))
        return digest.hexdigest()

    def counts(self) -> dict[str, int]:
        return {a: sum(1 for _c, p in self.plans if p.action == a) for a in (CREATE, REUSE, CONFLICT)}

    @property
    def ready(self) -> bool:
        return (
            not self.problems and len(self.plans) == len(PILOT_EXPORT_CODES)
            and all(p.ready for _c, p in self.plans)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "combined_sha256": self.combined_sha256, "counts": self.counts(),
            "result": "READY" if self.ready else "NOT READY", "problems": self.problems,
            "records": [
                {"code": code, "action": plan.action, "manifest_sha256": plan.manifest_sha256,
                 "reasons": plan.reasons, "manifest_errors": plan.manifest_errors}
                for code, plan in self.plans
            ],
            "writes_performed": self.applied["rows_created"] if self.applied else 0,
            "applied": self.applied,
        }

    def render_text(self) -> str:
        counts = self.counts()
        out = [
            "Pilot export ServiceComponent twins",
            f"Mode: {'APPLY' if self.mode == 'APPLY' else 'DRY RUN (plan only; no rows are written)'}",
            f"Combined sha256: {self.combined_sha256}",
            f"CREATE {counts[CREATE]}   REUSE {counts[REUSE]}   CONFLICT {counts[CONFLICT]}",
        ]
        for code, plan in self.plans:
            out.append(f"  [{plan.action}] {code}")
            out += [f"      ! {reason}" for reason in plan.reasons]
            out += [f"      ! [{e['code']}] {e['message']}" for e in plan.manifest_errors]
        out += [f"Problem: {p}" for p in self.problems]
        out.append(f"Result: {'READY' if self.ready else 'NOT READY'}")
        if self.mode == "APPLY" and self.applied is not None:
            out.append(f"Applied by {self.applied['operator']}: {self.applied['rows_created']} row(s) created.")
        elif self.mode == "APPLY":
            out.append("Apply refused. Nothing was written.")
        else:
            out.append("Writes performed: 0")
        return "\n".join(out)


def derive_manifest_text(code: str, *, using: str = "default") -> str:
    """One strict single-component manifest, derived from the stored ProductCode as the broad sync would."""
    legacy = ProductCode.objects.using(using).filter(code=code).first()
    if legacy is None:
        raise ExportComponentError(f"No legacy ProductCode '{code}'; a twin is only created for an existing one.")
    description = legacy.description
    if ServiceComponent.objects.using(using).filter(description=description).exclude(code=code).exists():
        description = f"{description} (V4)"
    return json.dumps({
        "manifest_version": MANIFEST_VERSION,
        "service_components": [{
            "code": code, "description": description, "mode": "AIR", "leg": infer_component_leg(legacy),
            "category": SYNC_CATEGORY_MAP.get(legacy.category, "ACCESSORIAL"), "cost_type": "COGS",
            "cost_source": "BASE_COST",
            "unit": legacy.default_unit if legacy.default_unit in ("KG", "SHIPMENT") else "SHIPMENT",
            "audience": AUDIENCE_DEFAULT, "is_active": True, "evidence": EVIDENCE,
        }],
    }, indent=2, sort_keys=True) + "\n"


def _plan_set(plan: ComponentSetPlan, using: str) -> None:
    plan.plans, plan.problems = [], []
    for code in PILOT_EXPORT_CODES:
        try:
            text = derive_manifest_text(code, using=using)
        except ExportComponentError as exc:
            plan.problems.append(str(exc))
            continue
        plan.plans.append((code, plan_component_text(text, using=using)))


def plan_export_components(*, using: str = "default") -> ComponentSetPlan:
    plan = ComponentSetPlan()
    _plan_set(plan, using)
    return plan


def apply_export_components(*, operator, reviewed_sha256: str, using: str = "default") -> ComponentSetPlan:
    """Create every missing twin atomically. Refuses unless the reviewed set is CREATE/REUSE only."""
    if operator is None or not getattr(operator, "is_active", False):
        raise ExportComponentError("Apply requires an active operator account.")
    plan = ComponentSetPlan(mode="APPLY")
    created = 0
    with transaction.atomic(using=using):
        _plan_set(plan, using)
        if reviewed_sha256 != plan.combined_sha256:
            transaction.set_rollback(True, using=using)
            raise ExportComponentError(
                "The twin set does not match the reviewed dry run (sha256 differs). Nothing was written."
            )
        if not plan.ready:
            transaction.set_rollback(True, using=using)
            return plan
        for code, item in plan.plans:
            if item.action != CREATE:
                continue
            try:
                done = apply_component_text(
                    derive_manifest_text(code, using=using), operator=operator,
                    reviewed_sha256=item.manifest_sha256, using=using,
                )
            except ComponentApplyError as exc:
                raise ExportComponentError(f"{code}: {exc}") from exc
            created += done.applied["rows_created"] if done.applied else 0
        verify = ComponentSetPlan()
        _plan_set(verify, using)
        if verify.problems or verify.counts()[REUSE] != len(PILOT_EXPORT_CODES):
            raise ExportComponentError("Post-apply verification failed; rolled back.")
    plan.applied = {"operator": operator.get_username(), "rows_created": created}
    return plan
