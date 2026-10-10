"""Controlled loader for Rate Matrix tariffs (Pilot Gate B3H).

The apply counterpart of ``validate_rate_matrix_manifest``. It reuses the B3C
parser and validator contract unchanged and writes only:

    RateSheet -> RateLine -> RateApplicability
                          -> RateTier

Dry run is the default and never writes. Apply is insert-only and atomic: every
sheet in every supplied manifest must be CREATE or REUSE, or nothing is written.
An existing sheet with the same name and version is REUSE when it is identical in
every field and every line, and CONFLICT otherwise; stored rows are never updated.
A correction is a new RateSheet version.

Nothing here creates a CommercialProductCode, party, location, or legacy
ProductCode (that is the B3F master-data loader), and no pricing path calls this
module. The Rate Matrix is not wired into live pricing.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from django.db import transaction

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_manifest import (
    RATE_CONFLICT_MESSAGES,
    ManifestParseError,
    classify_rate_conflict,
    parse_manifest_text,
    read_only_database,
    validate_manifest_for_load,
)

CREATE = "CREATE"
REUSE = "REUSE"
CONFLICT = "CONFLICT"

_QUANTUM = Decimal("0.0001")

SHEET_FIELDS = (
    "rate_type", "transport_mode", "currency_code", "valid_from", "valid_until", "is_active",
    "source_reference", "carrier_id", "party_id",
)


class TariffApplyError(RuntimeError):
    """Apply was refused or failed verification. Nothing was written."""


@dataclass
class SheetPlan:
    manifest: str
    path: str
    name: str
    version: int
    action: str = CREATE
    reasons: list[str] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)

    @property
    def line_count(self) -> int:
        return len(self.payload["lines"])

    @property
    def tier_count(self) -> int:
        return sum(len(line["tiers"]) for line in self.payload["lines"])

    def as_dict(self) -> dict[str, Any]:
        return {
            "manifest": self.manifest, "path": self.path, "name": self.name, "version": self.version,
            "action": self.action, "reasons": self.reasons, "lines": self.line_count,
            "tiers": self.tier_count, **self.summary,
        }


@dataclass
class TariffPlan:
    manifests: list[dict[str, str]] = field(default_factory=list)
    reviewed_sha256: str = ""
    mode: str = "DRY_RUN"
    issues: list[dict[str, str]] = field(default_factory=list)
    warnings: list[dict[str, str]] = field(default_factory=list)
    sheets: list[SheetPlan] = field(default_factory=list)
    applied: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return (
            bool(self.manifests) and not self.issues
            and all(sheet.action in (CREATE, REUSE) for sheet in self.sheets)
        )

    def issue(self, manifest: str, code: str, path: str, message: str) -> None:
        entry = {"manifest": manifest, "code": code, "path": path, "message": message}
        if entry not in self.issues:
            self.issues.append(entry)

    def counts(self) -> dict[str, int]:
        creates = [sheet for sheet in self.sheets if sheet.action == CREATE]
        return {
            "sheets_create": len(creates),
            "sheets_reuse": sum(1 for s in self.sheets if s.action == REUSE),
            "sheets_conflict": sum(1 for s in self.sheets if s.action == CONFLICT),
            "rate_lines_create": sum(s.line_count for s in creates),
            "rate_applicabilities_create": sum(s.line_count for s in creates),
            "rate_tiers_create": sum(s.tier_count for s in creates),
            "errors": len(self.issues),
            "warnings": len(self.warnings),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "result": "READY" if self.ready else "NOT READY",
            "reviewed_sha256": self.reviewed_sha256,
            "manifests": self.manifests,
            "counts": self.counts(),
            "writes_performed": self.applied["rows_created"] if self.applied else 0,
            "rate_sheets": [sheet.as_dict() for sheet in self.sheets],
            "errors": self.issues,
            "warnings": self.warnings,
            "applied": self.applied,
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def render_text(self) -> str:
        counts = self.counts()
        mode = "APPLY" if self.mode == "APPLY" else "DRY RUN (plan only; no rows are written)"
        out = [
            "Rate Matrix tariff load",
            f"Mode: {mode}",
            f"Reviewed sha256: {self.reviewed_sha256}",
            "",
            f"Manifests ({len(self.manifests)})",
        ]
        out += [f"  {m['label']}  sha256 {m['sha256']}" for m in self.manifests]
        out += [
            "",
            (
                f"Sheets: CREATE {counts['sheets_create']}   REUSE {counts['sheets_reuse']}   "
                f"CONFLICT {counts['sheets_conflict']}"
            ),
            (
                f"Proposed creates: RateLine {counts['rate_lines_create']}, "
                f"RateApplicability {counts['rate_applicabilities_create']}, RateTier {counts['rate_tiers_create']}"
            ),
            "",
            f"Rate sheets ({len(self.sheets)})",
        ]
        for sheet in self.sheets:
            out.append(
                f"  [{sheet.action}] \"{sheet.name}\" v{sheet.version} {sheet.summary['rate_type']} "
                f"{sheet.summary['transport_mode']} {sheet.summary['currency_code']} "
                f"{sheet.summary['valid_from']}..{sheet.summary['valid_until'] or 'open'} "
                f"active={sheet.summary['is_active']} lines={sheet.line_count} tiers={sheet.tier_count}"
            )
            out.append(f"      {sheet.manifest} {sheet.path}  source=\"{sheet.summary['source_reference']}\"")
            out += [f"      ! {reason}" for reason in sheet.reasons]
        for title, items in (("Errors", self.issues), ("Warnings", self.warnings)):
            out += ["", f"{title} ({len(items)})"]
            out += [f"  [{i['code']}] {i['manifest']} {i['path']}: {i['message']}" for i in items]
        out += ["", f"Result: {'READY' if self.ready else 'NOT READY'}"]
        if self.mode == "APPLY" and self.applied is not None:
            applied = self.applied
            out.append(
                f"Applied by {applied['operator']}: {applied['rows_created']} row(s) created "
                f"({applied['sheets']} sheets, {applied['lines']} lines, "
                f"{applied['applicabilities']} applicabilities, {applied['tiers']} tiers)."
            )
        elif self.mode == "APPLY":
            out.append("Apply refused. Nothing was written.")
        else:
            out.append("Writes performed: 0")
        return "\n".join(out)


def manifest_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def reviewed_digest(texts: list[str]) -> str:
    """The hash an operator reviews and binds an apply to.

    One manifest: its own sha256. Several: the sha256 of the sorted per-manifest hashes, so the
    binding covers exactly this set of inputs regardless of the order they are named in.
    """
    hashes = [manifest_sha256(text) for text in texts]
    if len(hashes) == 1:
        return hashes[0]
    return hashlib.sha256("\n".join(sorted(hashes)).encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- planning


def plan_tariffs(entries: list[tuple[str, str]], *, using: str = "default") -> TariffPlan:
    """Dry run: plan every manifest inside a read-only, rolled-back transaction."""
    with read_only_database(using):
        return _build_plan(entries, using=using, mode="DRY_RUN")


def apply_tariffs(
    entries: list[tuple[str, str]], *, operator, reviewed_sha256: str, using: str = "default"
) -> TariffPlan:
    """Apply every manifest atomically, or write nothing.

    ``reviewed_sha256`` must equal the digest printed by the dry run that was reviewed, so an
    apply can never cover input other than what was reviewed.
    """
    if operator is None or not getattr(operator, "is_active", False):
        raise TariffApplyError("Apply requires an active operator account.")
    digest = reviewed_digest([text for _label, text in entries])
    if reviewed_sha256 != digest:
        raise TariffApplyError(
            "The manifests do not match the reviewed dry run (sha256 differs). Nothing was written."
        )

    with transaction.atomic(using=using):
        plan = _build_plan(entries, using=using, mode="APPLY")
        if not plan.ready:
            transaction.set_rollback(True, using=using)
            return plan

        before = _table_counts(using)
        _execute(plan, operator, using)
        after = _table_counts(using)
        expected = {
            "sheets": sum(1 for s in plan.sheets if s.action == CREATE),
            "lines": plan.counts()["rate_lines_create"],
            "applicabilities": plan.counts()["rate_applicabilities_create"],
            "tiers": plan.counts()["rate_tiers_create"],
        }
        created = {key: after[key] - before[key] for key in expected}
        if created != expected:
            raise TariffApplyError(
                f"Post-apply verification failed; rolled back. Expected rows {expected}, created {created}."
            )

        # Stored-truth proof: planning the same manifests again must find every sheet identical and
        # no ambiguity among active tariffs. Anything else rolls the whole apply back.
        check = _build_plan(entries, using=using, mode="DRY_RUN")
        problems = [f"{i['code']} {i['path']}" for i in check.issues]
        problems += [f"{s.name} v{s.version} is {s.action}" for s in check.sheets if s.action != REUSE]
        if problems or len(check.sheets) != len(plan.sheets):
            raise TariffApplyError(
                "Post-apply verification failed; rolled back. " + "; ".join(problems or ["sheet count differs"])
            )

    plan.applied = {
        "operator": operator.get_username(),
        "rows_created": sum(created.values()),
        **created,
    }
    return plan


def _table_counts(using: str) -> dict[str, int]:
    return {
        "sheets": RateSheet.objects.using(using).count(),
        "lines": RateLine.objects.using(using).count(),
        "applicabilities": RateApplicability.objects.using(using).count(),
        "tiers": RateTier.objects.using(using).count(),
    }


def _build_plan(entries: list[tuple[str, str]], *, using: str, mode: str) -> TariffPlan:
    plan = TariffPlan(mode=mode)
    if not entries:
        plan.issue("-", "NO_MANIFEST", "$", "At least one manifest is required.")
        return plan
    plan.reviewed_sha256 = reviewed_digest([text for _label, text in entries])

    validated: list[tuple[str, Any, Any]] = []
    for label, text in entries:
        plan.manifests.append({"label": label, "sha256": manifest_sha256(text)})
        try:
            data = parse_manifest_text(text)
        except ManifestParseError as exc:
            plan.issue(label, "MANIFEST_NOT_STRICT_JSON", "$", str(exc))
            continue
        result = validate_manifest_for_load(data, using=using)
        clean = True
        for issue in result.report.errors:
            plan.issue(label, issue.code, issue.path, issue.message)
            clean = False
        for warning in result.report.warnings:
            plan.warnings.append(
                {"manifest": label, "code": warning.code, "path": warning.path, "message": warning.message}
            )
        for code in result.report.product_codes:
            if code["action"] == CREATE:
                plan.issue(
                    label, "PRODUCT_CODE_CREATE_NOT_SUPPORTED", "$.product_codes",
                    f"'{code['code']}' would be created. The tariff loader only references existing "
                    "CommercialProductCodes; load them with load_rate_matrix_master_data first.",
                )
                clean = False
        if clean:
            validated.append((label, data, result))

    _check_across_manifests(plan, validated)
    if plan.issues:
        # Sheets are only planned once the inputs are valid and mutually unambiguous.
        return plan
    for label, data, result in validated:
        _plan_sheets(plan, label, data, result, using)
    return plan


def _check_across_manifests(plan: TariffPlan, validated: list[tuple[str, Any, Any]]) -> None:
    """Rival tariffs and duplicate sheet identities between different manifests."""
    seen_sheets: dict[tuple[str, int], str] = {}
    for label, data, _result in validated:
        for index, sheet in enumerate(data["rate_sheets"]):
            key = (sheet["name"], sheet["version"])
            path = f"$.rate_sheets[{index}]"
            if key in seen_sheets:
                plan.issue(
                    label, "SHEET_DUPLICATE_ACROSS_MANIFESTS", path,
                    f"Sheet '{key[0]}' v{key[1]} is also supplied by {seen_sheets[key]}.",
                )
            else:
                seen_sheets[key] = f"{label} {path}"

    for position, (label, _data, result) in enumerate(validated):
        for other_label, _other_data, other_result in validated[:position]:
            for record in result.rate_records:
                for other in other_result.rate_records:
                    if record["sheet_key"] == other["sheet_key"]:
                        continue
                    code = classify_rate_conflict(record, other)
                    if code:
                        plan.issue(
                            label, code, record["label"],
                            RATE_CONFLICT_MESSAGES[code].format(other=f"{other_label} {other['label']}"),
                        )


def _plan_sheets(plan: TariffPlan, label: str, data: dict, result: Any, using: str) -> None:
    geography = {geo["iata"]: uuid.UUID(geo["id"]) for geo in result.report.geography}
    suppliers = {
        (party["legal_name"], party["country_code"], party["role"]): uuid.UUID(party["id"])
        for party in result.report.parties
    }
    codes = {
        code.code: code
        for code in CommercialProductCode.objects.using(using).filter(
            code__in={
                value
                for sheet in data["rate_sheets"]
                for line in sheet["lines"]
                for value in (line["product_code"], line["percentage_basis_product_code"])
                if value is not None
            }
        )
    }

    for index, raw in enumerate(data["rate_sheets"]):
        path = f"$.rate_sheets[{index}]"
        supplier = raw["supplier"]
        payload = {
            "sheet": {
                "name": raw["name"], "version": raw["version"], "rate_type": raw["rate_type"],
                "transport_mode": raw["transport_mode"], "currency_code": raw["currency_code"],
                "valid_from": date.fromisoformat(raw["valid_from"]),
                "valid_until": date.fromisoformat(raw["valid_until"]) if raw["valid_until"] else None,
                "is_active": raw["is_active"], "source_reference": raw["source_reference"],
                "carrier_id": suppliers[(supplier["legal_name"], supplier["country_code"], supplier["role"])]
                if supplier else None,
                "party_id": None,  # Pilot v1: customer-specific tariffs are rejected by validation.
            },
            "lines": [_line_payload(line, geography, codes) for line in raw["lines"]],
        }
        sheet_plan = SheetPlan(
            manifest=label, path=path, name=raw["name"], version=raw["version"], payload=payload,
            summary={
                "rate_type": raw["rate_type"], "transport_mode": raw["transport_mode"],
                "currency_code": raw["currency_code"], "valid_from": raw["valid_from"],
                "valid_until": raw["valid_until"], "is_active": raw["is_active"],
                "source_reference": raw["source_reference"],
                "supplier": supplier["legal_name"] if supplier else None,
            },
        )
        existing = (
            RateSheet.objects.using(using)
            .filter(name=raw["name"], version=raw["version"])
            .prefetch_related("lines__product_code", "lines__percentage_basis_product_code", "lines__applicability", "lines__tiers")
            .first()
        )
        if existing is not None:
            reasons = _differences(existing, payload)
            if reasons:
                sheet_plan.action = CONFLICT
                sheet_plan.reasons = reasons
            else:
                sheet_plan.action = REUSE
        plan.sheets.append(sheet_plan)


def _line_payload(raw: dict, geography: dict[str, uuid.UUID], codes: dict[str, CommercialProductCode]) -> dict:
    applicability = raw["applicability"]
    return {
        "product_code": raw["product_code"], "rate_basis": raw["rate_basis"],
        "unit_rate": _decimal(raw["unit_rate"]), "additive_flat_amount": _decimal(raw["additive_flat_amount"]),
        "min_charge": _decimal(raw["min_charge"]), "max_charge": _decimal(raw["max_charge"]),
        "percentage_rate": _decimal(raw["percentage_rate"]),
        "percentage_basis_product_code": raw["percentage_basis_product_code"],
        "direction": applicability["direction"], "payment_term": applicability["payment_term"],
        "service_level": applicability["service_level"],
        "commodity_category": applicability["commodity_category"],
        "equipment_type": applicability["equipment_type"],
        "origin_id": geography[applicability["origin_iata"]] if applicability["origin_iata"] else None,
        "destination_id": geography[applicability["destination_iata"]] if applicability["destination_iata"] else None,
        "tiers": [
            (_decimal(tier["min_quantity"]), _decimal(tier["max_quantity"]), _decimal(tier["unit_rate"]))
            for tier in raw["tiers"]
        ],
        "product_code_ref": codes[raw["product_code"]],
        "percentage_basis_ref": codes[raw["percentage_basis_product_code"]]
        if raw["percentage_basis_product_code"] else None,
    }


def _decimal(value: str | None) -> Decimal | None:
    return None if value is None else Decimal(value)


# ----------------------------------------------------------------------------- comparison


def _q(value: Decimal | None) -> str | None:
    return None if value is None else format(value.quantize(_QUANTUM), "f")


def _line_key(line: dict[str, Any]) -> tuple:
    """Canonical identity of a stored or proposed line, including its applicability and tiers."""
    return (
        line["product_code"], line["rate_basis"], _q(line["unit_rate"]), _q(line["additive_flat_amount"]),
        _q(line["min_charge"]), _q(line["max_charge"]), _q(line["percentage_rate"]),
        line["percentage_basis_product_code"],
        line["direction"], str(line["origin_id"]) if line["origin_id"] else None,
        str(line["destination_id"]) if line["destination_id"] else None,
        line["payment_term"], line["service_level"], line["commodity_category"], line["equipment_type"],
        tuple(sorted((_q(lo), _q(hi), _q(rate)) for lo, hi, rate in line["tiers"])),
    )


def _stored_line(line: RateLine) -> dict[str, Any]:
    applicability = line.applicability
    return {
        "product_code": line.product_code.code, "rate_basis": line.rate_basis,
        "unit_rate": line.unit_rate, "additive_flat_amount": line.additive_flat_amount,
        "min_charge": line.min_charge, "max_charge": line.max_charge, "percentage_rate": line.percentage_rate,
        "percentage_basis_product_code": (
            line.percentage_basis_product_code.code if line.percentage_basis_product_code else None
        ),
        "direction": applicability.direction, "payment_term": applicability.payment_term,
        "service_level": applicability.service_level,
        "commodity_category": applicability.commodity_category,
        "equipment_type": applicability.equipment_type,
        "origin_id": applicability.origin_id, "destination_id": applicability.destination_id,
        "tiers": [(t.min_quantity, t.max_quantity, t.unit_rate) for t in line.tiers.all()],
    }


def _differences(existing: RateSheet, payload: dict[str, Any]) -> list[str]:
    reasons = []
    proposed = payload["sheet"]
    differing = [name for name in SHEET_FIELDS if getattr(existing, name) != proposed[name]]
    if differing:
        reasons.append(
            f"Stored RateSheet '{existing.name}' v{existing.version} differs in: {', '.join(differing)}. "
            "Stored sheets are never updated; a correction is a new version."
        )

    stored = []
    for line in existing.lines.all():
        try:
            stored.append(_stored_line(line))
        except RateApplicability.DoesNotExist:
            reasons.append(f"Stored line {line.product_code.code} has no applicability row.")
    stored_keys = Counter(_line_key(line) for line in stored)
    proposed_keys = Counter(_line_key(line) for line in payload["lines"])
    missing = proposed_keys - stored_keys
    extra = stored_keys - proposed_keys
    if missing or extra:
        reasons.append(
            f"Stored lines differ from the manifest: {sum(missing.values())} proposed line(s) not stored "
            f"({_codes(missing)}), {sum(extra.values())} stored line(s) not proposed ({_codes(extra)})."
        )
    return reasons


def _codes(keys: Counter) -> str:
    return ", ".join(sorted({key[0] for key in keys})) or "none"


# ----------------------------------------------------------------------------- apply


def _execute(plan: TariffPlan, operator, using: str) -> None:
    for sheet_plan in plan.sheets:
        if sheet_plan.action != CREATE:
            continue
        values = sheet_plan.payload["sheet"]
        sheet = RateSheet(
            name=values["name"], version=values["version"], rate_type=values["rate_type"],
            transport_mode=values["transport_mode"], currency_code=values["currency_code"],
            valid_from=values["valid_from"], valid_until=values["valid_until"],
            is_active=values["is_active"], source_reference=values["source_reference"],
            carrier_id=values["carrier_id"], party_id=values["party_id"], created_by=operator,
        )
        sheet.full_clean()
        sheet.save(using=using, force_insert=True)

        for raw in sheet_plan.payload["lines"]:
            line = RateLine(
                sheet=sheet, product_code=raw["product_code_ref"], rate_basis=raw["rate_basis"],
                unit_rate=raw["unit_rate"], additive_flat_amount=raw["additive_flat_amount"],
                min_charge=raw["min_charge"], max_charge=raw["max_charge"],
                percentage_rate=raw["percentage_rate"], percentage_basis_product_code=raw["percentage_basis_ref"],
            )
            # RateLine.clean() requires a TIERED_WEIGHT line's tiers to exist already, so field and
            # constraint checks run first and the full model check runs once the tiers are stored.
            line.clean_fields()
            line.validate_constraints()
            line.save(using=using, force_insert=True)

            applicability = RateApplicability(
                rate_line=line, origin_id=raw["origin_id"], destination_id=raw["destination_id"],
                direction=raw["direction"], payment_term=raw["payment_term"],
                service_level=raw["service_level"], commodity_category=raw["commodity_category"],
                equipment_type=raw["equipment_type"],
            )
            applicability.full_clean()
            applicability.save(using=using, force_insert=True)

            for lower, upper, rate in raw["tiers"]:
                tier = RateTier(rate_line=line, min_quantity=lower, max_quantity=upper, unit_rate=rate)
                tier.save(using=using, force_insert=True)  # RateTier.save() runs full_clean()
            line.full_clean()
