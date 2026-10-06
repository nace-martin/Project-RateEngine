"""Controlled loader for Rate Matrix master-data prerequisites (Pilot Gate B3F).

Plans, and only when explicitly asked applies, the creation or reuse of:

- PartyMaster rows with their roles and role identifiers;
- genuinely new legacy ProductCodes;
- CommercialProductCode mirrors of legacy ProductCodes.

Dry run is the default and never writes. Apply is atomic: every record must be
CREATE or REUSE, and any failure rolls everything back. Existing rows are never
updated. No tariff, rate, or pricing path is touched.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from parties.party_models import PartyMaster, PartyRole, PartyRoleIdentifier

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.services.rate_matrix_manifest import (
    ManifestParseError,
    parse_manifest_text,
    read_only_database,
)

MANIFEST_VERSION = 1

CREATE = "CREATE"
REUSE = "REUSE"
CONFLICT = "CONFLICT"
BLOCKED = "BLOCKED"

COUNTRY_PATTERN = re.compile(r"^[A-Z]{2}$")
RATE_PATTERN = re.compile(r"^\d\.\d{4}$")

TOP_KEYS = ("manifest_version", "parties", "legacy_product_codes", "commercial_product_codes")
PARTY_KEYS = ("legal_name", "trade_name", "entity_type", "country_code", "roles", "identifiers", "evidence")
IDENTIFIER_KEYS = ("role", "scheme", "value")
LEGACY_KEYS = (
    "id", "code", "description", "domain", "category", "default_unit", "is_gst_applicable", "gst_rate",
    "gst_treatment", "gl_revenue_code", "gl_cost_code", "percent_of_product_code", "evidence",
)
COMMERCIAL_KEYS = (
    "code", "name", "category", "sub_category", "gst_treatment", "charge_basis_default", "is_active",
    "legacy_product_code", "gst_approval", "evidence",
)
LEGACY_REF_KEYS = ("id", "code")
GST_APPROVAL_KEYS = ("approved", "reference")

# Fields compared when a legacy ProductCode already exists. Legacy rows are never altered.
LEGACY_COMPARE = (
    "id", "code", "description", "domain", "category", "default_unit", "is_gst_applicable",
    "gst_rate", "gst_treatment", "gl_revenue_code", "gl_cost_code",
)
COMMERCIAL_COMPARE = ("name", "category", "sub_category", "gst_treatment", "charge_basis_default", "is_active")


class MasterDataApplyError(RuntimeError):
    """Apply was refused or failed. Nothing was written."""


@dataclass
class Record:
    kind: str
    path: str
    identity: str
    action: str = CREATE
    evidence: str = ""
    reasons: list[str] = field(default_factory=list)
    details: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)

    def conflict(self, reason: str) -> None:
        self.action = CONFLICT
        self.reasons.append(reason)

    def block(self, reason: str) -> None:
        if self.action != CONFLICT:
            self.action = BLOCKED
        self.reasons.append(reason)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind, "path": self.path, "identity": self.identity, "action": self.action,
            "evidence": self.evidence, "reasons": self.reasons, "details": self.details,
        }


@dataclass
class MasterDataPlan:
    manifest_sha256: str = ""
    manifest_errors: list[dict[str, str]] = field(default_factory=list)
    records: list[Record] = field(default_factory=list)
    mode: str = "DRY_RUN"
    applied: dict[str, Any] | None = None

    @property
    def ready(self) -> bool:
        return not self.manifest_errors and all(r.action in (CREATE, REUSE) for r in self.records)

    def counts(self) -> dict[str, int]:
        return {action: sum(1 for r in self.records if r.action == action) for action in (CREATE, REUSE, CONFLICT, BLOCKED)}

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "manifest_sha256": self.manifest_sha256,
            "result": "READY" if self.ready else "NOT READY",
            "counts": self.counts(),
            "manifest_errors": self.manifest_errors,
            "records": [r.as_dict() for r in self.records],
            "applied": self.applied,
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def render_text(self) -> str:
        counts = self.counts()
        mode = "APPLY" if self.mode == "APPLY" else "DRY RUN (plan only; no rows are written)"
        out = [
            "Rate Matrix master-data plan",
            f"Mode: {mode}",
            f"Manifest sha256: {self.manifest_sha256}",
            "",
            f"CREATE {counts[CREATE]}   REUSE {counts[REUSE]}   CONFLICT {counts[CONFLICT]}   BLOCKED {counts[BLOCKED]}",
        ]
        if self.manifest_errors:
            out += ["", f"Manifest errors ({len(self.manifest_errors)})"]
            out += [f"  [{e['code']}] {e['path']}: {e['message']}" for e in self.manifest_errors]
        for kind in ("PartyMaster", "ProductCode", "CommercialProductCode"):
            records = [r for r in self.records if r.kind == kind]
            out += ["", f"{kind} ({len(records)})"]
            for record in records:
                out.append(f"  [{record.action}] {record.identity}  ({record.path})")
                out += [f"      - {detail}" for detail in record.details]
                out += [f"      ! {reason}" for reason in record.reasons]
                if record.evidence:
                    out.append(f"      evidence: {record.evidence}")
        out += ["", f"Result: {'READY' if self.ready else 'NOT READY'}"]
        if self.mode == "APPLY" and self.applied is not None:
            out.append(f"Applied by {self.applied['operator']}: {self.applied['rows_created']} row(s) created.")
        elif self.mode == "APPLY":
            out.append("Apply refused. Nothing was written.")
        else:
            out.append("Writes performed: 0")
        return "\n".join(out)


def plan_master_data_text(text: str, *, using: str = "default") -> MasterDataPlan:
    """Dry run: parse and plan inside a read-only, rolled-back transaction."""
    plan = MasterDataPlan(manifest_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        plan.manifest_errors.append({"code": "MANIFEST_NOT_STRICT_JSON", "path": "$", "message": str(exc)})
        return plan
    with read_only_database(using):
        _Planner(using, plan).run(data)
    return plan


def apply_master_data_text(text: str, *, operator, reviewed_sha256: str, using: str = "default") -> MasterDataPlan:
    """Apply the manifest atomically. Refuses unless every record is CREATE or REUSE.

    ``reviewed_sha256`` must equal the manifest hash printed by the dry run that was reviewed,
    so an apply can never cover input other than what was reviewed.
    """
    if operator is None or not getattr(operator, "is_active", False):
        raise MasterDataApplyError("Apply requires an active operator account.")
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    if reviewed_sha256 != digest:
        raise MasterDataApplyError(
            "The manifest does not match the reviewed dry run (sha256 differs). Nothing was written."
        )
    plan = MasterDataPlan(manifest_sha256=digest, mode="APPLY")
    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        plan.manifest_errors.append({"code": "MANIFEST_NOT_STRICT_JSON", "path": "$", "message": str(exc)})
        return plan

    with transaction.atomic(using=using):
        _Planner(using, plan).run(data)
        if not plan.ready:
            transaction.set_rollback(True, using=using)
            return plan
        created = _execute(plan, using)
        # Idempotency proof: planning the same manifest again must find nothing left to create.
        check = MasterDataPlan()
        _Planner(using, check).run(data)
        leftover = [r.identity for r in check.records if r.action != REUSE]
        if check.manifest_errors or leftover:
            raise MasterDataApplyError(
                "Post-apply verification failed; rolled back. Records not in REUSE state: " + ", ".join(leftover)
            )
    plan.applied = {"operator": operator.get_username(), "rows_created": created}
    return plan


def _execute(plan: MasterDataPlan, using: str) -> int:
    created = 0
    for record in plan.records:
        payload = record.payload
        if record.kind == "PartyMaster":
            party = payload["existing"]
            if party is None:
                party = PartyMaster(**payload["fields"])
                party.full_clean()
                party.save(using=using, force_insert=True)
                created += 1
            roles = {r.role_type: r for r in PartyRole.objects.using(using).filter(party=party)}
            for role_type in payload["roles_to_create"]:
                role = PartyRole(party=party, role_type=role_type)
                role.full_clean()
                role.save(using=using, force_insert=True)
                roles[role_type] = role
                created += 1
            for role_type, scheme, value in payload["identifiers_to_create"]:
                identifier = PartyRoleIdentifier(role=roles[role_type], scheme=scheme, value=value)
                identifier.full_clean()
                identifier.save(using=using, force_insert=True)
                created += 1
        elif record.kind == "ProductCode" and record.action == CREATE:
            fields = dict(payload["fields"])
            parent_code = fields.pop("percent_of_product_code")
            if parent_code is not None:
                fields["percent_of_product_code"] = ProductCode.objects.using(using).get(code=parent_code)
            product_code = ProductCode(**fields)
            product_code.full_clean()
            product_code.save(using=using, force_insert=True)
            created += 1
        elif record.kind == "CommercialProductCode" and record.action == CREATE:
            fields = dict(payload["fields"])
            fields["legacy_product_code"] = ProductCode.objects.using(using).get(pk=payload["legacy_id"])
            mirror = CommercialProductCode(**fields)
            mirror.full_clean()
            mirror.save(using=using, force_insert=True)
            created += 1
    return created


class _Planner:
    def __init__(self, using: str, plan: MasterDataPlan):
        self.using = using
        self.plan = plan
        self.proposed_legacy: dict[str, Record] = {}

    # ------------------------------------------------------------------ shape

    def _error(self, code: str, path: str, message: str) -> None:
        self.plan.manifest_errors.append({"code": code, "path": path, "message": message})

    def _object(self, value: Any, path: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self._error("MANIFEST_TYPE", path, "Expected a JSON object.")
            return None
        ok = True
        for key in keys:
            if key not in value:
                self._error("MANIFEST_MISSING_FIELD", f"{path}.{key}", "Required field is missing; every field must be explicit.")
                ok = False
        for key in sorted(set(value) - set(keys)):
            self._error("MANIFEST_UNKNOWN_FIELD", f"{path}.{key}", "Field is not part of the manifest contract.")
            ok = False
        return value if ok else None

    def _string(self, obj: dict, key: str, path: str, *, allow_blank: bool = False) -> str | None:
        value = obj[key]
        if not isinstance(value, str) or value != value.strip() or (not value and not allow_blank):
            self._error("VALUE_INVALID", f"{path}.{key}", "Expected a trimmed string" + ("." if allow_blank else ", not blank."))
            return None
        return value

    def _typed(self, obj: dict, key: str, path: str, kind: type) -> Any:
        value = obj[key]
        if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
            self._error("VALUE_INVALID", f"{path}.{key}", f"Expected {kind.__name__}.")
            return None
        return value

    # -------------------------------------------------------------------- run

    def run(self, data: Any) -> None:
        root = self._object(data, "$", TOP_KEYS)
        if root is None:
            return
        if root["manifest_version"] != MANIFEST_VERSION or isinstance(root["manifest_version"], bool):
            self._error("MANIFEST_VERSION", "$.manifest_version", f"Only manifest_version {MANIFEST_VERSION} is supported.")
            return
        sections = {}
        for key in TOP_KEYS[1:]:
            if not isinstance(root[key], list):
                self._error("MANIFEST_TYPE", f"$.{key}", "Expected a JSON array.")
                return
            sections[key] = root[key]
        for index, entry in enumerate(sections["parties"]):
            self._party(entry, f"$.parties[{index}]")
        for index, entry in enumerate(sections["legacy_product_codes"]):
            self._legacy(entry, f"$.legacy_product_codes[{index}]")
        for index, entry in enumerate(sections["commercial_product_codes"]):
            self._commercial(entry, f"$.commercial_product_codes[{index}]")

    def _add(self, record: Record) -> Record:
        self.plan.records.append(record)
        return record

    # ---------------------------------------------------------------- parties

    def _party(self, entry: Any, path: str) -> None:
        obj = self._object(entry, path, PARTY_KEYS)
        if obj is None:
            return
        legal_name = self._string(obj, "legal_name", path)
        trade_name = self._string(obj, "trade_name", path, allow_blank=True)
        entity_type = self._string(obj, "entity_type", path)
        country = self._string(obj, "country_code", path)
        evidence = self._string(obj, "evidence", path)
        roles = self._typed(obj, "roles", path, list)
        identifiers = self._typed(obj, "identifiers", path, list)
        if country is not None and not COUNTRY_PATTERN.match(country):
            self._error("VALUE_INVALID", f"{path}.country_code", "Expected a two-letter upper-case country code.")
            country = None
        if roles is not None and (not roles or any(r not in PartyRole.RoleType.values for r in roles) or len(set(roles)) != len(roles)):
            self._error("VALUE_INVALID", f"{path}.roles", "Expected a non-empty list of distinct valid role types.")
            roles = None
        parsed_identifiers = []
        for index, item in enumerate(identifiers or []):
            item_path = f"{path}.identifiers[{index}]"
            ident = self._object(item, item_path, IDENTIFIER_KEYS)
            if ident is None:
                identifiers = None
                continue
            role = self._string(ident, "role", item_path)
            scheme = self._string(ident, "scheme", item_path)
            value = self._string(ident, "value", item_path)
            if None in (role, scheme, value):
                identifiers = None
            elif scheme not in PartyRoleIdentifier.Scheme.values or (roles is not None and role not in roles):
                self._error("VALUE_INVALID", item_path, "Scheme must be valid and role must be one of this party's roles.")
                identifiers = None
            else:
                parsed_identifiers.append((role, scheme, value))
        if None in (legal_name, trade_name, entity_type, country, evidence, roles, identifiers):
            return

        record = self._add(Record("PartyMaster", path, f'"{legal_name}" ({country})', evidence=evidence))
        if any(r.kind == "PartyMaster" and r.identity == record.identity and r is not record for r in self.plan.records):
            record.conflict("Duplicate party identity in this manifest.")
            return
        matches = list(PartyMaster.objects.using(self.using).filter(legal_name=legal_name, country_code=country).order_by("id")[:2])
        existing = matches[0] if matches else None
        if len(matches) > 1:
            record.conflict("More than one existing PartyMaster has this legal name and country.")
            return
        roles_to_create, identifiers_to_create = [], []
        if existing is None:
            record.details.append("PartyMaster CREATE")
            roles_to_create = list(roles)
        else:
            record.details.append(f"PartyMaster REUSE {existing.id}")
            if not existing.is_active:
                record.conflict("Existing PartyMaster is inactive.")
            for name, value in (("trade_name", trade_name), ("entity_type", entity_type)):
                if getattr(existing, name) != value:
                    record.conflict(f"Existing PartyMaster differs in {name}; existing rows are never updated.")
            existing_roles = {r.role_type: r for r in PartyRole.objects.using(self.using).filter(party=existing)}
            for role in roles:
                if role not in existing_roles:
                    roles_to_create.append(role)
                elif not existing_roles[role].is_active:
                    record.conflict(f"Existing {role} role is inactive.")
        for role in roles:
            record.details.append(f"PartyRole {role} {'CREATE' if role in roles_to_create else 'REUSE'}")
        for role, scheme, value in parsed_identifiers:
            holder = (
                PartyRoleIdentifier.objects.using(self.using).filter(scheme=scheme, value=value)
                .select_related("role__party").first()
            )
            if holder is None:
                identifiers_to_create.append((role, scheme, value))
                record.details.append(f"PartyRoleIdentifier {scheme} {value} CREATE")
            elif existing is not None and holder.role.party_id == existing.id and holder.role.role_type == role:
                record.details.append(f"PartyRoleIdentifier {scheme} {value} REUSE")
            else:
                record.conflict(f"Identifier {scheme} {value} already belongs to another party or role.")
        if record.action != CONFLICT:
            record.action = CREATE if (existing is None or roles_to_create or identifiers_to_create) else REUSE
        record.payload = {
            "existing": existing, "roles_to_create": roles_to_create, "identifiers_to_create": identifiers_to_create,
            "fields": {"legal_name": legal_name, "trade_name": trade_name, "entity_type": entity_type, "country_code": country},
        }

    # ------------------------------------------------------- legacy ProductCode

    def _legacy(self, entry: Any, path: str) -> None:
        obj = self._object(entry, path, LEGACY_KEYS)
        if obj is None:
            return
        pc_id = self._typed(obj, "id", path, int)
        strings = {key: self._string(obj, key, path) for key in (
            "code", "description", "domain", "category", "default_unit", "gst_rate",
            "gst_treatment", "gl_revenue_code", "gl_cost_code", "evidence",
        )}
        taxable = self._typed(obj, "is_gst_applicable", path, bool)
        parent = obj["percent_of_product_code"]
        if parent is not None and (not isinstance(parent, str) or not parent or parent != parent.strip()):
            self._error("VALUE_INVALID", f"{path}.percent_of_product_code", "Expected null or a ProductCode code.")
            return
        if pc_id is None or taxable is None or None in strings.values():
            return
        if not RATE_PATTERN.match(strings["gst_rate"]):
            self._error("VALUE_INVALID", f"{path}.gst_rate", 'Expected a decimal string with four places, such as "0.1000".')
            return
        try:
            gst_rate = Decimal(strings["gst_rate"])
        except InvalidOperation:
            self._error("VALUE_INVALID", f"{path}.gst_rate", "Not a decimal.")
            return

        code = strings["code"]
        record = self._add(Record("ProductCode", path, f"{pc_id} {code}", evidence=strings["evidence"]))
        fields = {
            "id": pc_id, "code": code, "description": strings["description"], "domain": strings["domain"],
            "category": strings["category"], "default_unit": strings["default_unit"], "is_gst_applicable": taxable,
            "gst_rate": gst_rate, "gst_treatment": strings["gst_treatment"],
            "gl_revenue_code": strings["gl_revenue_code"], "gl_cost_code": strings["gl_cost_code"],
            "percent_of_product_code": parent,
        }
        record.payload = {"fields": fields}
        if code in self.proposed_legacy or any(
            r.kind == "ProductCode" and r is not record and r.payload.get("fields", {}).get("id") == pc_id
            for r in self.plan.records
        ):
            record.conflict("Duplicate ProductCode id or code in this manifest.")
            return
        self.proposed_legacy[code] = record

        manager = ProductCode.objects.using(self.using)
        by_code = manager.filter(code__iexact=code).first()
        by_id = manager.filter(pk=pc_id).first()
        if by_id is not None and (by_code is None or by_code.pk != by_id.pk):
            record.conflict(f"ProductCode id {pc_id} already belongs to '{by_id.code}'.")
            return
        if by_code is not None:
            differing = [name for name in LEGACY_COMPARE if getattr(by_code, name) != fields[name]]
            existing_parent = by_code.percent_of_product_code.code if by_code.percent_of_product_code_id else None
            if existing_parent != parent:
                differing.append("percent_of_product_code")
            if differing:
                record.conflict(
                    f"Existing ProductCode '{by_code.code}' differs in: {', '.join(differing)}. Legacy ProductCodes are never altered."
                )
            elif not by_code.is_active or by_code.retired_at is not None:
                record.conflict(f"Existing ProductCode '{by_code.code}' is inactive or retired.")
            else:
                record.action = REUSE
            return

        parent_obj = None
        if parent is not None:
            parent_obj = manager.filter(code=parent).first()
            if parent_obj is None and parent not in self.proposed_legacy:
                record.conflict(f"percent_of_product_code '{parent}' does not exist.")
                return
        if strings["gst_treatment"] == ProductCode.GST_TREATMENT_STANDARD and not taxable:
            record.conflict("gst_treatment STANDARD requires is_gst_applicable true.")
        if strings["gst_treatment"] != ProductCode.GST_TREATMENT_STANDARD and taxable:
            record.conflict("is_gst_applicable true requires gst_treatment STANDARD.")
        candidate = ProductCode(**{**fields, "percent_of_product_code": parent_obj})
        try:
            # Canonical creation rules: model validation (choices, id range by domain) on an explicit, manual id.
            candidate.full_clean(exclude=["percent_of_product_code"] if parent is not None and parent_obj is None else None)
        except ValidationError as exc:
            for name, messages in exc.message_dict.items():
                record.conflict(f"{name}: {' '.join(messages)}")

    # ---------------------------------------------------- CommercialProductCode

    def _commercial(self, entry: Any, path: str) -> None:
        obj = self._object(entry, path, COMMERCIAL_KEYS)
        if obj is None:
            return
        strings = {key: self._string(obj, key, path, allow_blank=(key == "sub_category")) for key in (
            "code", "name", "category", "sub_category", "gst_treatment", "charge_basis_default", "evidence",
        )}
        is_active = self._typed(obj, "is_active", path, bool)
        ref = self._object(obj["legacy_product_code"], f"{path}.legacy_product_code", LEGACY_REF_KEYS)
        approval = self._object(obj["gst_approval"], f"{path}.gst_approval", GST_APPROVAL_KEYS)
        ref_id = ref_code = approved = reference = None
        if ref is not None:
            ref_id = self._typed(ref, "id", f"{path}.legacy_product_code", int)
            ref_code = self._string(ref, "code", f"{path}.legacy_product_code")
        if approval is not None:
            approved = self._typed(approval, "approved", f"{path}.gst_approval", bool)
            reference = self._string(approval, "reference", f"{path}.gst_approval", allow_blank=True)
        if None in strings.values() or None in (is_active, ref_id, ref_code, approved, reference):
            return
        for key, choices in (
            ("category", CommercialProductCode.Category.values),
            ("gst_treatment", CommercialProductCode.GstTreatment.values),
            ("charge_basis_default", CommercialProductCode.ChargeBasis.values),
        ):
            if strings[key] not in choices:
                self._error("VALUE_INVALID", f"{path}.{key}", f"'{strings[key]}' is not one of {', '.join(sorted(choices))}.")
                return
        if approved and not reference:
            self._error("VALUE_INVALID", f"{path}.gst_approval.reference", "An approved GST treatment must cite its approval reference.")
            return

        code = strings["code"]
        record = self._add(Record("CommercialProductCode", path, f"{code} -> legacy {ref_id}", evidence=strings["evidence"]))
        fields = {key: strings[key] for key in ("code", "name", "category", "sub_category", "gst_treatment", "charge_basis_default")}
        fields["is_active"] = is_active
        record.payload = {"fields": fields, "legacy_id": ref_id}
        record.details.append(f"category {strings['category']}, basis {strings['charge_basis_default']}, GST {strings['gst_treatment']}")
        for other in self.plan.records:
            if other.kind == "CommercialProductCode" and other is not record and (
                other.payload.get("fields", {}).get("code") == code or other.payload.get("legacy_id") == ref_id
            ):
                record.conflict("Duplicate commercial code or legacy mapping in this manifest.")
                return

        proposed = self.proposed_legacy.get(ref_code)
        legacy = ProductCode.objects.using(self.using).filter(pk=ref_id).first()
        if legacy is None and proposed is not None and proposed.payload["fields"]["id"] == ref_id:
            legacy_view = {**proposed.payload["fields"], "is_active": True, "retired_at": None}
            if proposed.action in (CONFLICT, BLOCKED):
                record.block(f"Depends on legacy ProductCode {ref_id} {ref_code}, which is {proposed.action} in this manifest.")
        elif legacy is None:
            record.conflict(f"No legacy ProductCode has id {ref_id}.")
            return
        else:
            legacy_view = {"code": legacy.code, "gst_treatment": legacy.gst_treatment, "is_active": legacy.is_active, "retired_at": legacy.retired_at}
        if legacy_view["code"] != ref_code:
            record.conflict(f"Legacy ProductCode {ref_id} has code '{legacy_view['code']}', not '{ref_code}'.")
        if legacy_view["code"] != code:
            record.conflict(f"Commercial code '{code}' does not exactly mirror legacy code '{legacy_view['code']}'.")
        if not legacy_view["is_active"] or legacy_view["retired_at"] is not None:
            record.conflict(f"Legacy ProductCode {ref_id} is inactive or retired.")
        if legacy_view["gst_treatment"] != strings["gst_treatment"]:
            record.conflict(
                f"gst_treatment '{strings['gst_treatment']}' does not match legacy ProductCode {ref_id} ('{legacy_view['gst_treatment']}')."
            )

        manager = CommercialProductCode.objects.using(self.using)
        by_legacy = manager.filter(legacy_product_code_id=ref_id).first()
        if by_legacy is not None and by_legacy.code != code:
            record.conflict(f"Legacy ProductCode {ref_id} is already mapped to CommercialProductCode '{by_legacy.code}'.")
        existing = manager.filter(code=code).first()
        if existing is not None:
            if existing.legacy_product_code_id != ref_id:
                record.conflict(f"Existing CommercialProductCode '{code}' is mapped to {existing.legacy_product_code_id}, not {ref_id}.")
            differing = [name for name in COMMERCIAL_COMPARE if getattr(existing, name) != fields[name]]
            if differing:
                record.conflict(f"Existing CommercialProductCode '{code}' differs in: {', '.join(differing)}. Existing rows are never updated.")
            if record.action != CONFLICT:
                record.action = REUSE
            return
        if not approved:
            record.block(
                f"GST treatment {strings['gst_treatment']} is not commercially approved for loading (gst_approval.approved is false)."
            )
        else:
            record.details.append(f"GST approval: {reference}")
