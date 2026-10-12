"""Controlled introduction of a new CommercialTermsPolicy version (Pilot Gate B3L-B).

Plans, and only when explicitly asked applies, one new policy version that takes over from the policy in
force on a stated date. Dry run is the default and never writes.

An existing policy row is never edited in place. The single permitted change to an existing row is
ending an open-ended policy (``valid_until`` from null to the day before the new version starts), and
it happens only through this explicit, reviewed, atomic supersession so that:

- the old version ends the day before the new one begins (no overlap, no gap);
- exactly one policy resolves for every date;
- the whole change is all-or-nothing, bound to the reviewed hash, and idempotent.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.services.commercial_policy import (
    PolicyResolutionError,
    require_unique_commercial_terms_policy,
)
from pricing_v4.services.rate_matrix_manifest import (
    ManifestParseError,
    parse_manifest_text,
    read_only_database,
)

MANIFEST_VERSION = 1
TOP_KEYS = ("manifest_version", "policy", "supersedes", "evidence")
POLICY_KEYS = (
    "policy_code", "valid_from", "margin_percent", "margin_method", "import_caf_percent", "export_caf_percent",
    "gst_standard_percent", "caf_method", "fx_side_convention", "fx_max_age_days", "fx_primary_source",
    "fx_fallback_source",
)
SUPERSEDES_KEYS = ("policy_code", "expected_valid_until", "set_valid_until")
DECIMAL_FIELDS = ("margin_percent", "import_caf_percent", "export_caf_percent", "gst_standard_percent")

CREATE = "CREATE"
REUSE = "REUSE"
CONFLICT = "CONFLICT"
SUPERSEDE = "SUPERSEDE"
ALREADY_ENDED = "ALREADY_ENDED"


class PolicyApplyError(RuntimeError):
    """Apply was refused or failed verification. Nothing was written."""


@dataclass
class PolicyPlan:
    manifest_sha256: str = ""
    manifest_errors: list[dict[str, str]] = field(default_factory=list)
    action: str | None = None
    supersede_action: str | None = None
    policy: dict[str, Any] = field(default_factory=dict)
    supersedes: dict[str, Any] = field(default_factory=dict)
    evidence: str = ""
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    mode: str = "DRY_RUN"
    applied: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return (
            not self.manifest_errors
            and self.action in (CREATE, REUSE)
            and self.supersede_action in (SUPERSEDE, ALREADY_ENDED)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "manifest_sha256": self.manifest_sha256,
            "result": "READY" if self.ready else "NOT READY", "policy_action": self.action,
            "supersede_action": self.supersede_action, "manifest_errors": self.manifest_errors,
            "policy": self.policy, "supersedes": self.supersedes, "evidence": self.evidence,
            "reasons": self.reasons, "details": self.details,
            "writes_performed": self.applied["rows_written"] if self.applied else 0, "applied": self.applied,
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True, default=str)

    def render_text(self) -> str:
        mode = "APPLY" if self.mode == "APPLY" else "DRY RUN (plan only; no rows are written)"
        out = [
            "Commercial terms policy version plan",
            f"Mode: {mode}",
            f"Manifest sha256: {self.manifest_sha256}",
            "",
            f"New policy:  [{self.action}] {self.policy.get('policy_code')} from {self.policy.get('valid_from')}",
            (
                f"Old policy:  [{self.supersede_action}] {self.supersedes.get('policy_code')} "
                f"ends {self.supersedes.get('set_valid_until')}"
            ),
        ]
        if self.policy:
            out.append("Values: " + json.dumps(self.policy, sort_keys=True, default=str))
        out += [f"  - {detail}" for detail in self.details]
        out += [f"  ! {reason}" for reason in self.reasons]
        if self.manifest_errors:
            out += ["", "Manifest errors"] + [f"  [{e['code']}] {e['path']}: {e['message']}" for e in self.manifest_errors]
        out.append(f"Evidence: {self.evidence}")
        out += ["", f"Result: {'READY' if self.ready else 'NOT READY'}"]
        if self.mode == "APPLY" and self.applied is not None:
            out.append(f"Applied by {self.applied['operator']}: {self.applied['rows_written']} row(s) written.")
        elif self.mode == "APPLY":
            out.append("Apply refused. Nothing was written.")
        else:
            out.append("Writes performed: 0")
        return "\n".join(out)


def plan_policy_text(text: str, *, using: str = "default") -> PolicyPlan:
    plan = PolicyPlan(manifest_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    with read_only_database(using):
        _plan(text, plan)
    return plan


def apply_policy_text(text: str, *, operator, reviewed_sha256: str, using: str = "default") -> PolicyPlan:
    if operator is None or not getattr(operator, "is_active", False):
        raise PolicyApplyError("Apply requires an active operator account.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if reviewed_sha256 != digest:
        raise PolicyApplyError("The manifest does not match the reviewed dry run (sha256 differs). Nothing was written.")
    plan = PolicyPlan(manifest_sha256=digest, mode="APPLY")
    written = 0
    with transaction.atomic(using=using):
        _plan(text, plan)
        if not plan.ready:
            transaction.set_rollback(True, using=using)
            return plan
        if plan.supersede_action == SUPERSEDE:
            old = CommercialTermsPolicy.objects.using(using).select_for_update().get(
                policy_code=plan.supersedes["policy_code"]
            )
            old.valid_until = date.fromisoformat(plan.supersedes["set_valid_until"])
            old.full_clean()
            old.save(using=using, update_fields=["valid_until"])
            written += 1
        if plan.action == CREATE:
            row = CommercialTermsPolicy(**_row_values(plan.policy))
            row.full_clean()
            row.save(using=using, force_insert=True)
            written += 1

        # Stored-truth proof: planning again finds nothing left to do, and exactly one policy resolves on
        # either side of the changeover and well after it.
        check = PolicyPlan()
        _plan(text, check)
        if check.manifest_errors or check.action != REUSE or check.supersede_action != ALREADY_ENDED:
            raise PolicyApplyError(
                "Post-apply verification failed; rolled back. "
                f"Plan after apply was {check.action}/{check.supersede_action}: {'; '.join(check.reasons)}"
            )
        new_start = date.fromisoformat(plan.policy["valid_from"])
        for probe, expected in (
            (new_start - timedelta(days=1), plan.supersedes["policy_code"]),
            (new_start, plan.policy["policy_code"]),
            (new_start + timedelta(days=365), plan.policy["policy_code"]),
        ):
            try:
                resolved = require_unique_commercial_terms_policy(probe)
            except PolicyResolutionError as exc:
                raise PolicyApplyError(f"Post-apply verification failed; rolled back. {probe}: {exc}") from exc
            if resolved.policy_code != expected:
                raise PolicyApplyError(
                    f"Post-apply verification failed; rolled back. {probe} resolves to "
                    f"{resolved.policy_code}, expected {expected}."
                )
    plan.applied = {"operator": operator.get_username(), "rows_written": written}
    return plan


# ----------------------------------------------------------------------------- planning


def _row_values(policy: dict[str, Any]) -> dict[str, Any]:
    values = dict(policy)
    values["valid_from"] = date.fromisoformat(values["valid_from"])
    for name in DECIMAL_FIELDS:
        values[name] = None if values[name] is None else Decimal(values[name])
    values["valid_until"] = None
    values["is_active"] = True
    return values


def _plan(text: str, plan: PolicyPlan) -> None:
    def error(code: str, path: str, message: str) -> None:
        plan.manifest_errors.append({"code": code, "path": path, "message": message})

    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        error("MANIFEST_NOT_STRICT_JSON", "$", str(exc))
        return
    if not isinstance(data, dict) or set(data) != set(TOP_KEYS):
        error("MANIFEST_SHAPE", "$", f"Expected an object with exactly: {', '.join(TOP_KEYS)}.")
        return
    if data["manifest_version"] != MANIFEST_VERSION or isinstance(data["manifest_version"], bool):
        error("MANIFEST_VERSION", "$.manifest_version", f"Only manifest_version {MANIFEST_VERSION} is supported.")
        return
    evidence, policy, supersedes = data["evidence"], data["policy"], data["supersedes"]
    if not isinstance(evidence, str) or not evidence.strip() or evidence != evidence.strip():
        error("VALUE_INVALID", "$.evidence", "Evidence must be a trimmed, non-blank string.")
        return
    if not isinstance(policy, dict) or set(policy) != set(POLICY_KEYS):
        error("MANIFEST_SHAPE", "$.policy", f"Expected exactly: {', '.join(POLICY_KEYS)}.")
        return
    if not isinstance(supersedes, dict) or set(supersedes) != set(SUPERSEDES_KEYS):
        error("MANIFEST_SHAPE", "$.supersedes", f"Expected exactly: {', '.join(SUPERSEDES_KEYS)}.")
        return
    plan.evidence = evidence

    try:
        valid_from = date.fromisoformat(policy["valid_from"])
        set_until = date.fromisoformat(supersedes["set_valid_until"])
        expected_until = (
            None if supersedes["expected_valid_until"] is None else date.fromisoformat(supersedes["expected_valid_until"])
        )
    except (TypeError, ValueError) as exc:
        error("DATE_INVALID", "$", f"Dates must be YYYY-MM-DD strings: {exc}")
        return
    normalised = dict(policy)
    for name in DECIMAL_FIELDS:
        value = policy[name]
        if value is None:
            normalised[name] = None
            continue
        try:
            number = Decimal(value) if isinstance(value, str) else None
        except InvalidOperation:
            number = None
        if number is None:
            error("DECIMAL_INVALID", f"$.policy.{name}", "Percentages must be decimal strings such as \"5.00\".")
            return
        normalised[name] = str(number.quantize(Decimal("0.01")))
    for name in ("policy_code", "margin_method", "caf_method", "fx_side_convention", "fx_primary_source",
                 "fx_fallback_source"):
        if not isinstance(policy[name], str) or policy[name] != policy[name].strip():
            error("VALUE_INVALID", f"$.policy.{name}", "Expected a trimmed string.")
            return
    age = policy["fx_max_age_days"]
    if age is not None and (not isinstance(age, int) or isinstance(age, bool) or age < 0):
        error("VALUE_INVALID", "$.policy.fx_max_age_days", "Expected null or a non-negative integer.")
        return
    plan.policy = {**normalised, "valid_from": valid_from.isoformat(), "valid_until": None}
    plan.supersedes = {
        "policy_code": supersedes["policy_code"],
        "expected_valid_until": expected_until.isoformat() if expected_until else None,
        "set_valid_until": set_until.isoformat(),
    }

    reasons: list[str] = []
    candidate = CommercialTermsPolicy(**_row_values(plan.policy))
    try:
        candidate.full_clean(validate_unique=False, validate_constraints=False)
    except ValidationError as exc:
        reasons.append(f"Policy values are invalid: {exc.message_dict if hasattr(exc, 'message_dict') else exc}")

    if valid_from != set_until + timedelta(days=1):
        reasons.append(
            f"The old policy must end the day before the new one starts: valid_from {valid_from} requires "
            f"set_valid_until {valid_from - timedelta(days=1)}, not {set_until}."
        )

    existing = CommercialTermsPolicy.objects.filter(policy_code=policy["policy_code"]).first()
    old = CommercialTermsPolicy.objects.filter(policy_code=supersedes["policy_code"]).first()
    if old is None:
        reasons.append(f"Superseded policy '{supersedes['policy_code']}' does not exist.")
    elif old.policy_code == policy["policy_code"]:
        reasons.append("A policy cannot supersede itself.")
    else:
        if not old.is_active:
            reasons.append(f"Superseded policy '{old.policy_code}' is inactive.")
        if old.valid_until == set_until:
            plan.supersede_action = ALREADY_ENDED
            plan.details.append(f"{old.policy_code} already ends {set_until}.")
        elif old.valid_until == expected_until:
            if set_until <= old.valid_from:
                reasons.append("set_valid_until must be after the old policy's valid_from.")
            else:
                plan.supersede_action = SUPERSEDE
                plan.details.append(
                    f"{old.policy_code}: valid_until {old.valid_until or 'open-ended'} -> {set_until} "
                    "(the only change to the existing row)."
                )
        else:
            reasons.append(
                f"{old.policy_code} valid_until is {old.valid_until}, expected {expected_until} or {set_until}."
            )

    if existing is None:
        plan.action = CREATE
        plan.details.append(f"Insert {policy['policy_code']} from {valid_from}, open-ended.")
    else:
        stored = {
            "valid_from": existing.valid_from.isoformat(), "valid_until": existing.valid_until,
            **{name: (None if getattr(existing, name) is None else str(getattr(existing, name)))
               for name in DECIMAL_FIELDS},
            **{name: getattr(existing, name) for name in (
                "policy_code", "margin_method", "caf_method", "fx_side_convention", "fx_max_age_days",
                "fx_primary_source", "fx_fallback_source",
            )},
        }
        differing = sorted(key for key in stored if stored[key] != plan.policy.get(key))
        if differing or not existing.is_active:
            plan.action = CONFLICT
            reasons.append(
                f"Stored policy '{existing.policy_code}' differs in: {', '.join(differing) or 'is_active'}. "
                "Stored policies are never edited; use a new policy code."
            )
        else:
            plan.action = REUSE
            plan.details.append(f"{existing.policy_code} is already stored and identical.")

    rivals = (
        CommercialTermsPolicy.objects.filter(is_active=True)
        .exclude(policy_code__in=[policy["policy_code"], supersedes["policy_code"]])
        .filter(Q(valid_until__isnull=True) | Q(valid_until__gte=valid_from))
    )
    for rival in rivals:
        reasons.append(f"Active policy '{rival.policy_code}' would overlap the new version from {valid_from}.")

    plan.reasons = reasons
    if reasons:
        plan.action = CONFLICT
