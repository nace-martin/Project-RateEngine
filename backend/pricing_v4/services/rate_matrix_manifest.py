"""Dry-run validation of a Rate Matrix ingestion manifest (Pilot Gate B3C).

Validates a strict JSON manifest against the Pilot Gate B3A contract
(docs/architecture/clean-database-architecture-v2.1.md section 3.5.1) and the
current database. It only reads. There is no apply mode: nothing here creates,
updates, or deletes a row, and no pricing path calls this module.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from itertools import pairwise
from typing import Any

from django.db import connections, transaction

from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import RateApplicability, RateLine, RateSheet

MANIFEST_VERSION = 1

ERROR = "ERROR"
WARNING = "WARNING"

DECIMAL_PATTERN = re.compile(r"^\d+(\.\d+)?$")
NEGATIVE_PATTERN = re.compile(r"^-\d+(\.\d+)?$")
IATA_PATTERN = re.compile(r"^[A-Z]{3}$")
CURRENCY_PATTERN = re.compile(r"^[A-Z]{3}$")

SCALAR_BASES = ("FLAT", "PER_KG", "PER_CBM", "PER_UNIT")
SUPPLIER_ROLES = ("CARRIER", "AGENT")
CUSTOMER_ROLES = ("CUSTOMER",)

TOP_KEYS = ("manifest_version", "product_codes", "rate_sheets")
PRODUCT_CODE_KEYS = (
    "code", "name", "category", "sub_category", "gst_treatment",
    "charge_basis_default", "is_active", "legacy_product_code",
)
LEGACY_REF_KEYS = ("id", "code")
SHEET_KEYS = (
    "name", "version", "rate_type", "transport_mode", "currency_code", "valid_from",
    "valid_until", "is_active", "source_reference", "supplier", "customer", "lines",
)
PARTY_KEYS = ("legal_name", "country_code", "role")
LINE_KEYS = (
    "product_code", "rate_basis", "unit_rate", "additive_flat_amount", "min_charge",
    "max_charge", "percentage_rate", "percentage_basis_product_code", "applicability", "tiers",
)
APPLICABILITY_KEYS = (
    "direction", "origin_iata", "destination_iata", "payment_term",
    "service_level", "commodity_category", "equipment_type",
)
TIER_KEYS = ("min_quantity", "max_quantity", "unit_rate")

# Applicability and scope dimensions where a blank value means "any".
WILDCARD_DIMENSIONS = (
    "supplier", "customer", "direction", "origin", "destination",
    "service_level", "commodity_category", "equipment_type", "payment_term",
)
EXACT_DIMENSIONS = ("rate_type", "product_code", "transport_mode", "currency_code")


class ManifestParseError(ValueError):
    """The manifest text is not strict JSON."""


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"severity": self.severity, "code": self.code, "path": self.path, "message": self.message}


@dataclass
class ManifestReport:
    """Deterministic result of one dry-run. Holds no timestamps and no generated ids."""

    issues: list[Issue] = field(default_factory=list)
    product_codes: list[dict[str, Any]] = field(default_factory=list)
    geography: list[dict[str, Any]] = field(default_factory=list)
    parties: list[dict[str, Any]] = field(default_factory=list)
    sheets: list[dict[str, Any]] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == ERROR]

    @property
    def warnings(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.severity == WARNING]

    @property
    def passed(self) -> bool:
        return not self.errors

    def error(self, code: str, path: str, message: str) -> None:
        self.issues.append(Issue(ERROR, code, path, message))

    def warn(self, code: str, path: str, message: str) -> None:
        self.issues.append(Issue(WARNING, code, path, message))

    def counts(self) -> dict[str, int]:
        return {
            "product_codes_create": sum(1 for pc in self.product_codes if pc["action"] == "CREATE"),
            "product_codes_reuse": sum(1 for pc in self.product_codes if pc["action"] == "REUSE"),
            "geography_reuse": len(self.geography),
            "parties_reuse": len(self.parties),
            "rate_sheets_create": len(self.sheets),
            "rate_lines_create": sum(sheet["lines"] for sheet in self.sheets),
            "rate_applicabilities_create": sum(sheet["lines"] for sheet in self.sheets),
            "rate_tiers_create": sum(sheet["tiers"] for sheet in self.sheets),
            "errors": len(self.errors),
            "warnings": len(self.warnings),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": "DRY_RUN",
            "writes_performed": 0,
            "result": "PASS" if self.passed else "FAIL",
            "counts": self.counts(),
            "product_codes": self.product_codes,
            "geography": self.geography,
            "parties": self.parties,
            "rate_sheets": self.sheets,
            "errors": [issue.as_dict() for issue in self.errors],
            "warnings": [issue.as_dict() for issue in self.warnings],
        }

    def render_json(self) -> str:
        return json.dumps(self.as_dict(), indent=2, sort_keys=True)

    def render_text(self) -> str:
        counts = self.counts()
        out = [
            "Rate Matrix manifest dry-run",
            "Mode: DRY RUN (validation only; no rows are written and no apply mode exists)",
            "",
            "Proposed creates",
            f"  CommercialProductCode: {counts['product_codes_create']}",
            f"  RateSheet:             {counts['rate_sheets_create']}",
            f"  RateLine:              {counts['rate_lines_create']}",
            f"  RateApplicability:     {counts['rate_applicabilities_create']}",
            f"  RateTier:              {counts['rate_tiers_create']}",
            "",
            "Proposed reuses",
            f"  CommercialProductCode: {counts['product_codes_reuse']}",
            f"  GeoLocation:           {counts['geography_reuse']}",
            f"  PartyMaster:           {counts['parties_reuse']}",
            "",
            f"Resolved ProductCodes ({len(self.product_codes)})",
        ]
        for pc in self.product_codes:
            out.append(
                f"  {pc['action']:6s} {pc['code']} -> legacy ProductCode {pc['legacy_id']} "
                f"[{pc['category']}, {pc['charge_basis_default']}, {pc['gst_treatment']}] ({pc['origin']})"
            )
        out += ["", f"Resolved geography ({len(self.geography)})"]
        for geo in self.geography:
            out.append(f"  {geo['iata']} -> {geo['canonical_name']} ({geo['country_code']}) {geo['id']}")
        out += ["", f"Resolved parties ({len(self.parties)})"]
        for party in self.parties:
            out.append(
                f"  {party['role']} {party['legal_name']} ({party['country_code']}) {party['id']}"
            )
        out += ["", f"Rate sheets validated ({len(self.sheets)})"]
        for sheet in self.sheets:
            shown = {key: "(invalid)" if value is None else value for key, value in sheet.items()}
            out.append(
                f"  {sheet['path']} \"{shown['name']}\" v{shown['version']} {shown['rate_type']} "
                f"{shown['transport_mode']} {shown['currency_code']} "
                f"{shown['valid_from']}..{sheet['valid_until'] or 'open'} "
                f"active={sheet['is_active']} lines={sheet['lines']} tiers={sheet['tiers']} "
                f"source=\"{sheet['source_reference']}\""
            )
        for title, issues in (("Errors", self.errors), ("Warnings", self.warnings)):
            out += ["", f"{title} ({len(issues)})"]
            for issue in issues:
                out.append(f"  [{issue.code}] {issue.path}: {issue.message}")
        out += ["", f"Result: {'PASS' if self.passed else 'FAIL'}"]
        if not self.passed:
            out.append("The proposals above are not valid while errors remain.")
        out.append("Writes performed: 0")
        return "\n".join(out)


@contextmanager
def read_only_database(using: str = "default"):
    """Run the block with the connection refusing writes, then roll everything back.

    The validator issues no write statements. This makes that a property of the
    connection as well: an accidental write raises instead of persisting.
    """
    connection = connections[using]
    try:
        with transaction.atomic(using=using):
            if connection.vendor == "postgresql":
                # Scoped to this (sub)transaction; undone by the rollback below.
                with connection.cursor() as cursor:
                    cursor.execute("SET LOCAL transaction_read_only = on")
            elif connection.vendor == "sqlite":
                with connection.cursor() as cursor:
                    cursor.execute("PRAGMA query_only = ON")
            try:
                yield
            finally:
                transaction.set_rollback(True, using=using)
    finally:
        if connection.vendor == "sqlite" and connection.connection is not None:
            # A pragma is not transactional, and after a rejected write Django refuses
            # further queries until the block ends, so reset it on the raw connection.
            connection.connection.execute("PRAGMA query_only = OFF")


def parse_manifest_text(text: str) -> Any:
    """Parse strict JSON: no duplicate keys, no NaN or Infinity."""

    def reject_duplicates(pairs):
        seen: dict[str, Any] = {}
        for key, value in pairs:
            if key in seen:
                raise ManifestParseError(f"Duplicate key '{key}' in manifest object.")
            seen[key] = value
        return seen

    def reject_constant(name):
        raise ManifestParseError(f"Non-finite number '{name}' is not permitted.")

    try:
        return json.loads(text, object_pairs_hook=reject_duplicates, parse_constant=reject_constant)
    except json.JSONDecodeError as exc:
        raise ManifestParseError(f"Invalid JSON at line {exc.lineno} column {exc.colno}: {exc.msg}") from exc


def validate_manifest_text(text: str, *, using: str = "default") -> ManifestReport:
    try:
        data = parse_manifest_text(text)
    except ManifestParseError as exc:
        report = ManifestReport()
        report.error("MANIFEST_NOT_STRICT_JSON", "$", str(exc))
        return report
    return validate_manifest(data, using=using)


def validate_manifest(data: Any, *, using: str = "default") -> ManifestReport:
    """Validate an already-parsed manifest. Reads the database; writes nothing."""
    with read_only_database(using):
        return _Validator(using).run(data)


def _is_blank(value: Any) -> bool:
    return value is None or value == ""


class _Validator:
    def __init__(self, using: str):
        self.using = using
        self.report = ManifestReport()
        self.proposed_codes: dict[str, str] = {}
        self.resolved_codes: dict[str, dict[str, Any]] = {}
        self.geo_cache: dict[str, GeoLocation | None] = {}
        self.party_cache: dict[tuple[str, str, str], PartyMaster | None] = {}
        self.rate_records: list[dict[str, Any]] = []

    # ------------------------------------------------------------------ shape

    def _object(self, value: Any, path: str, keys: tuple[str, ...]) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            self.report.error("MANIFEST_TYPE", path, "Expected a JSON object.")
            return None
        ok = True
        for key in keys:
            if key not in value:
                self.report.error(
                    "MANIFEST_MISSING_FIELD", f"{path}.{key}",
                    "Required field is missing; every field must be stated explicitly.",
                )
                ok = False
        for key in sorted(set(value) - set(keys)):
            self.report.error("MANIFEST_UNKNOWN_FIELD", f"{path}.{key}", "Field is not part of the manifest contract.")
            ok = False
        return value if ok else None

    def _list(self, value: Any, path: str) -> list[Any] | None:
        if not isinstance(value, list):
            self.report.error("MANIFEST_TYPE", path, "Expected a JSON array.")
            return None
        return value

    def _string(self, obj: dict, key: str, path: str, *, allow_blank: bool = False, max_length: int | None = None) -> str | None:
        value = obj[key]
        field_path = f"{path}.{key}"
        if not isinstance(value, str):
            self.report.error("MANIFEST_TYPE", field_path, "Expected a string.")
            return None
        if value != value.strip():
            self.report.error("VALUE_NOT_TRIMMED", field_path, "Value has leading or trailing whitespace.")
            return None
        if not value and not allow_blank:
            self.report.error("VALUE_REQUIRED", field_path, "Value must not be blank.")
            return None
        if max_length is not None and len(value) > max_length:
            self.report.error("VALUE_TOO_LONG", field_path, f"Value exceeds {max_length} characters.")
            return None
        return value

    def _choice(self, obj: dict, key: str, path: str, choices, *, allow_blank: bool = False) -> str | None:
        value = self._string(obj, key, path, allow_blank=allow_blank)
        if value is None:
            return None
        if value == "" and allow_blank:
            return value
        if value not in choices:
            self.report.error(
                "VALUE_NOT_ALLOWED", f"{path}.{key}",
                f"'{value}' is not one of {', '.join(sorted(choices))}.",
            )
            return None
        return value

    def _bool(self, obj: dict, key: str, path: str) -> bool | None:
        value = obj[key]
        if not isinstance(value, bool):
            self.report.error("MANIFEST_TYPE", f"{path}.{key}", "Expected true or false.")
            return None
        return value

    def _decimal(self, obj: dict, key: str, path: str, *, nullable: bool, max_digits: int, decimal_places: int) -> Decimal | None:
        value = obj[key]
        field_path = f"{path}.{key}"
        if value is None:
            if not nullable:
                self.report.error("VALUE_REQUIRED", field_path, "Value must not be null.")
            return None
        if not isinstance(value, str):
            self.report.error(
                "DECIMAL_NOT_STRING", field_path,
                "Amounts must be decimal strings such as \"12.50\", not JSON numbers.",
            )
            return None
        if NEGATIVE_PATTERN.match(value):
            self.report.error("NEGATIVE_AMOUNT", field_path, "Negative amounts are not permitted.")
            return None
        if not DECIMAL_PATTERN.match(value):
            self.report.error("DECIMAL_INVALID", field_path, f"'{value}' is not a plain decimal number.")
            return None
        try:
            number = Decimal(value)
        except InvalidOperation:
            self.report.error("DECIMAL_INVALID", field_path, f"'{value}' is not a plain decimal number.")
            return None
        whole, _, fraction = value.partition(".")
        if len(fraction) > decimal_places:
            self.report.error("DECIMAL_PRECISION", field_path, f"At most {decimal_places} decimal places are stored.")
            return None
        if len(whole.lstrip("0")) > max_digits - decimal_places:
            self.report.error("DECIMAL_PRECISION", field_path, "Value is too large for the stored precision.")
            return None
        return number

    def _date(self, obj: dict, key: str, path: str, *, nullable: bool) -> date | None:
        value = obj[key]
        field_path = f"{path}.{key}"
        if value is None:
            if not nullable:
                self.report.error("VALUE_REQUIRED", field_path, "Value must not be null.")
            return None
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            self.report.error("DATE_INVALID", field_path, "Expected a date string in YYYY-MM-DD form.")
            return None
        try:
            return date.fromisoformat(value)
        except ValueError:
            self.report.error("DATE_INVALID", field_path, f"'{value}' is not a real calendar date.")
            return None

    # -------------------------------------------------------------------- run

    def run(self, data: Any) -> ManifestReport:
        root = self._object(data, "$", TOP_KEYS)
        if root is None:
            return self.report
        if root["manifest_version"] != MANIFEST_VERSION or isinstance(root["manifest_version"], bool):
            self.report.error(
                "MANIFEST_VERSION", "$.manifest_version",
                f"Only manifest_version {MANIFEST_VERSION} is supported.",
            )
            return self.report

        product_codes = self._list(root["product_codes"], "$.product_codes")
        sheets = self._list(root["rate_sheets"], "$.rate_sheets")
        if product_codes is not None:
            self._collect_proposed_codes(product_codes)
            for index, entry in enumerate(product_codes):
                self._product_code(entry, f"$.product_codes[{index}]")
        if sheets is not None:
            seen_sheets: dict[tuple[str, int], str] = {}
            for index, entry in enumerate(sheets):
                self._sheet(entry, f"$.rate_sheets[{index}]", seen_sheets)
        self._detect_rate_conflicts()

        self.report.product_codes = sorted(self.resolved_codes.values(), key=lambda pc: pc["code"])
        self.report.geography = sorted(
            (
                {"iata": code, "id": str(geo.id), "canonical_name": geo.canonical_name, "country_code": geo.country_code}
                for code, geo in self.geo_cache.items() if geo is not None
            ),
            key=lambda geo: geo["iata"],
        )
        self.report.parties = sorted(
            (
                {"role": role, "legal_name": name, "country_code": country, "id": str(party.id)}
                for (name, country, role), party in self.party_cache.items() if party is not None
            ),
            key=lambda party: (party["role"], party["legal_name"], party["country_code"]),
        )
        return self.report

    # ---------------------------------------------------------- product codes

    def _collect_proposed_codes(self, entries: list[Any]) -> None:
        for index, entry in enumerate(entries):
            if isinstance(entry, dict) and isinstance(entry.get("code"), str):
                self.proposed_codes.setdefault(entry["code"], f"$.product_codes[{index}]")

    def _product_code(self, entry: Any, path: str) -> None:
        obj = self._object(entry, path, PRODUCT_CODE_KEYS)
        if obj is None:
            return
        code = self._string(obj, "code", path, max_length=64)
        name = self._string(obj, "name", path, max_length=255)
        category = self._choice(obj, "category", path, CommercialProductCode.Category.values)
        sub_category = self._string(obj, "sub_category", path, allow_blank=True, max_length=64)
        gst_treatment = self._choice(obj, "gst_treatment", path, CommercialProductCode.GstTreatment.values)
        basis = self._choice(obj, "charge_basis_default", path, CommercialProductCode.ChargeBasis.values)
        is_active = self._bool(obj, "is_active", path)
        legacy_ref = self._object(obj["legacy_product_code"], f"{path}.legacy_product_code", LEGACY_REF_KEYS)

        if code is not None and code != code.upper():
            self.report.error("PRODUCT_CODE_NOT_NORMALIZED", f"{path}.code", "Code must be upper case.")
            code = None
        if code is not None and self.proposed_codes.get(code) != path:
            self.report.error(
                "PRODUCT_CODE_DUPLICATE_IN_MANIFEST", f"{path}.code",
                f"Code '{code}' is already proposed at {self.proposed_codes[code]}.",
            )
            return

        legacy = None
        if legacy_ref is not None:
            legacy = self._legacy_product_code(legacy_ref, f"{path}.legacy_product_code", code, gst_treatment)
        if None in (code, name, category, sub_category, gst_treatment, basis, is_active) or legacy is None:
            return

        for other in self.resolved_codes.values():
            if other["legacy_id"] == legacy.id and other["origin"] == "manifest":
                self.report.error(
                    "LEGACY_PRODUCT_CODE_MAPPED_TWICE", f"{path}.legacy_product_code.id",
                    f"Legacy ProductCode {legacy.id} is already mapped by '{other['code']}' in this manifest.",
                )
                return

        proposal = {
            "code": code, "name": name, "category": category, "sub_category": sub_category,
            "gst_treatment": gst_treatment, "charge_basis_default": basis, "is_active": is_active,
        }
        action = self._compare_with_existing(proposal, legacy, path)
        if action is None:
            return
        self.resolved_codes[code] = {
            **proposal, "action": action, "legacy_id": legacy.id, "legacy_code": legacy.code, "origin": "manifest",
        }

    def _legacy_product_code(self, ref: dict, path: str, code: str | None, gst_treatment: str | None) -> ProductCode | None:
        legacy_id = ref["id"]
        if not isinstance(legacy_id, int) or isinstance(legacy_id, bool):
            self.report.error("MANIFEST_TYPE", f"{path}.id", "Expected an integer legacy ProductCode id.")
            return None
        legacy_code = self._string(ref, "code", path)
        legacy = ProductCode.objects.using(self.using).filter(pk=legacy_id).first()
        if legacy is None:
            self.report.error("LEGACY_PRODUCT_CODE_NOT_FOUND", f"{path}.id", f"No legacy ProductCode has id {legacy_id}.")
            return None
        ok = True
        if legacy_code is not None and legacy.code != legacy_code:
            self.report.error(
                "LEGACY_PRODUCT_CODE_MISMATCH", f"{path}.code",
                f"Legacy ProductCode {legacy_id} has code '{legacy.code}', not '{legacy_code}'.",
            )
            ok = False
        if code is not None and legacy.code != code:
            self.report.error(
                "PRODUCT_CODE_NOT_EXACT_MIRROR", path,
                f"Proposed code '{code}' does not exactly match legacy code '{legacy.code}'.",
            )
            ok = False
        if not legacy.is_active or legacy.retired_at is not None:
            self.report.error(
                "LEGACY_PRODUCT_CODE_INACTIVE", f"{path}.id",
                f"Legacy ProductCode {legacy_id} ({legacy.code}) is inactive or retired.",
            )
            ok = False
        if gst_treatment is not None and legacy.gst_treatment != gst_treatment:
            self.report.error(
                "GST_TREATMENT_MISMATCH", path,
                f"Proposed gst_treatment '{gst_treatment}' differs from legacy ProductCode "
                f"{legacy_id} ('{legacy.gst_treatment}').",
            )
            ok = False
        return legacy if ok and legacy_code is not None else None

    def _compare_with_existing(self, proposal: dict[str, Any], legacy: ProductCode, path: str) -> str | None:
        manager = CommercialProductCode.objects.using(self.using)
        by_legacy = manager.filter(legacy_product_code_id=legacy.id).first()
        if by_legacy is not None and by_legacy.code != proposal["code"]:
            self.report.error(
                "PRODUCT_CODE_MAPPING_CONFLICT", f"{path}.legacy_product_code.id",
                f"Legacy ProductCode {legacy.id} is already mapped to existing CommercialProductCode '{by_legacy.code}'.",
            )
            return None
        existing = manager.filter(code=proposal["code"]).first()
        if existing is None:
            return "CREATE"
        if existing.legacy_product_code_id != legacy.id:
            mapped = existing.legacy_product_code_id if existing.legacy_product_code_id is not None else "no legacy ProductCode"
            self.report.error(
                "PRODUCT_CODE_MAPPING_CONFLICT", path,
                f"Existing CommercialProductCode '{existing.code}' is mapped to {mapped}, not {legacy.id}.",
            )
            return None
        differing = sorted(key for key, value in proposal.items() if getattr(existing, key) != value)
        if differing:
            self.report.error(
                "PRODUCT_CODE_EXISTING_DIFFERS", path,
                f"Existing CommercialProductCode '{existing.code}' differs in: {', '.join(differing)}. "
                "Existing rows are never updated.",
            )
            return None
        return "REUSE"

    def _resolve_line_code(self, code: str, path: str) -> bool:
        if code in self.resolved_codes:
            return True
        if code in self.proposed_codes:
            self.report.error(
                "PRODUCT_CODE_PROPOSAL_INVALID", path,
                f"'{code}' is proposed at {self.proposed_codes[code]} but that proposal has errors.",
            )
            return False
        existing = CommercialProductCode.objects.using(self.using).filter(code=code).first()
        if existing is None:
            self.report.error(
                "PRODUCT_CODE_UNRESOLVED", path,
                f"'{code}' is neither proposed in this manifest nor an existing CommercialProductCode.",
            )
            return False
        if existing.legacy_product_code_id is None:
            self.report.error(
                "PRODUCT_CODE_UNMAPPED", path,
                f"Existing CommercialProductCode '{code}' has no legacy ProductCode mapping.",
            )
            return False
        if not existing.is_active:
            self.report.error("PRODUCT_CODE_INACTIVE", path, f"Existing CommercialProductCode '{code}' is inactive.")
            return False
        self.resolved_codes[code] = {
            "code": existing.code, "name": existing.name, "category": existing.category,
            "sub_category": existing.sub_category, "gst_treatment": existing.gst_treatment,
            "charge_basis_default": existing.charge_basis_default, "is_active": existing.is_active,
            "action": "REUSE", "legacy_id": existing.legacy_product_code_id,
            "legacy_code": existing.legacy_product_code.code, "origin": "existing",
        }
        return True

    # ------------------------------------------------------ geography, parties

    def _geo(self, obj: dict, key: str, path: str, transport_mode: str | None) -> tuple[bool, GeoLocation | None]:
        """Return (resolved_ok, location). A null value is a valid wildcard."""
        value = obj[key]
        field_path = f"{path}.{key}"
        if value is None:
            return True, None
        if not isinstance(value, str) or not IATA_PATTERN.match(value):
            self.report.error("IATA_INVALID", field_path, "Expected null or a three-letter upper-case IATA code.")
            return False, None
        if value not in self.geo_cache:
            self.geo_cache[value] = None
            identifiers = list(
                GeoLocationIdentifier.objects.using(self.using)
                .filter(scheme=GeoLocationIdentifier.Scheme.IATA, code=value)
                .select_related("location").order_by("id")[:2]
            )
            if not identifiers:
                self.report.error("GEOGRAPHY_NOT_FOUND", field_path, f"No IATA identifier '{value}' exists.")
            elif len(identifiers) > 1:
                self.report.error("GEOGRAPHY_AMBIGUOUS", field_path, f"IATA identifier '{value}' is not unique.")
            elif not identifiers[0].location.is_active:
                self.report.error("GEOGRAPHY_INACTIVE", field_path, f"The location for IATA '{value}' is inactive.")
            elif transport_mode == "AIR" and identifiers[0].location.location_type != GeoLocation.LocationType.AIRPORT:
                self.report.error("GEOGRAPHY_NOT_AIRPORT", field_path, f"IATA '{value}' does not resolve to an airport.")
            else:
                self.geo_cache[value] = identifiers[0].location
            return self.geo_cache[value] is not None, self.geo_cache[value]
        location = self.geo_cache[value]
        if location is None:
            self.report.error("GEOGRAPHY_UNRESOLVED", field_path, f"IATA '{value}' did not resolve (see earlier error).")
        return location is not None, location

    def _party(self, value: Any, path: str, allowed_roles: tuple[str, ...]) -> tuple[bool, PartyMaster | None]:
        """Return (resolved_ok, party). A null value means no party scope."""
        if value is None:
            return True, None
        obj = self._object(value, path, PARTY_KEYS)
        if obj is None:
            return False, None
        legal_name = self._string(obj, "legal_name", path)
        country_code = self._string(obj, "country_code", path)
        role = self._choice(obj, "role", path, allowed_roles)
        if None in (legal_name, country_code, role):
            return False, None
        key = (legal_name, country_code, role)
        if key in self.party_cache:
            party = self.party_cache[key]
            if party is None:
                self.report.error("PARTY_UNRESOLVED", path, "Party did not resolve (see earlier error).")
            return party is not None, party
        self.party_cache[key] = None
        matches = list(
            PartyMaster.objects.using(self.using)
            .filter(legal_name=legal_name, country_code=country_code).order_by("id")[:2]
        )
        if not matches:
            self.report.error("PARTY_NOT_FOUND", path, f"No PartyMaster '{legal_name}' ({country_code}) exists.")
        elif len(matches) > 1:
            self.report.error("PARTY_AMBIGUOUS", path, f"PartyMaster '{legal_name}' ({country_code}) is not unique.")
        elif not matches[0].is_active:
            self.report.error("PARTY_INACTIVE", path, f"PartyMaster '{legal_name}' ({country_code}) is inactive.")
        elif not PartyRole.objects.using(self.using).filter(party=matches[0], role_type=role, is_active=True).exists():
            self.report.error(
                "PARTY_ROLE_MISSING", f"{path}.role",
                f"PartyMaster '{legal_name}' ({country_code}) has no active {role} role.",
            )
        else:
            self.party_cache[key] = matches[0]
        return self.party_cache[key] is not None, self.party_cache[key]

    # ----------------------------------------------------------------- sheets

    def _sheet(self, entry: Any, path: str, seen: dict[tuple[str, int], str]) -> None:
        obj = self._object(entry, path, SHEET_KEYS)
        if obj is None:
            return
        name = self._string(obj, "name", path, max_length=255)
        rate_type = self._choice(obj, "rate_type", path, RateSheet.RateType.values)
        transport_mode = self._choice(obj, "transport_mode", path, RateSheet.TransportMode.values)
        source_reference = self._string(obj, "source_reference", path, max_length=255)
        is_active = self._bool(obj, "is_active", path)
        valid_from = self._date(obj, "valid_from", path, nullable=False)
        valid_until = self._date(obj, "valid_until", path, nullable=True)
        valid_until_ok = obj["valid_until"] is None or valid_until is not None

        version = obj["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            self.report.error("VERSION_INVALID", f"{path}.version", "Version must be an integer of 1 or more.")
            version = None

        currency_code = self._string(obj, "currency_code", path)
        if currency_code is not None:
            if not CURRENCY_PATTERN.match(currency_code):
                self.report.error("CURRENCY_INVALID", f"{path}.currency_code", "Expected three upper-case letters.")
                currency_code = None
            elif not Currency.objects.using(self.using).filter(pk=currency_code).exists():
                self.report.error(
                    "CURRENCY_UNKNOWN", f"{path}.currency_code",
                    f"Currency '{currency_code}' is not a known currency.",
                )
                currency_code = None

        if valid_from is not None and valid_until is not None and valid_until <= valid_from:
            self.report.error(
                "VALIDITY_WINDOW_INVALID", f"{path}.valid_until",
                "valid_until must be later than valid_from, or null for open-ended.",
            )
            valid_until_ok = False

        supplier_ok, supplier = self._party(obj["supplier"], f"{path}.supplier", SUPPLIER_ROLES)
        customer_ok, customer = self._party(obj["customer"], f"{path}.customer", CUSTOMER_ROLES)
        if rate_type == "BUY" and obj["customer"] is not None:
            self.report.error("BUY_SHEET_HAS_CUSTOMER", f"{path}.customer", "A BUY sheet must not name a customer.")
        if rate_type == "SELL" and obj["supplier"] is not None:
            self.report.error("SELL_SHEET_HAS_SUPPLIER", f"{path}.supplier", "A SELL sheet must not name a supplier.")
        if rate_type == "BUY" and obj["supplier"] is None:
            self.report.warn(
                "BUY_SHEET_WITHOUT_SUPPLIER", f"{path}.supplier",
                "BUY sheet names no carrier or agent; it would apply regardless of supplier.",
            )

        if name is not None and version is not None:
            key = (name, version)
            if key in seen:
                self.report.error(
                    "SHEET_DUPLICATE_IN_MANIFEST", path,
                    f"Sheet name and version already used at {seen[key]}.",
                )
            else:
                seen[key] = path
                if RateSheet.objects.using(self.using).filter(name=name, version=version).exists():
                    self.report.error(
                        "SHEET_ALREADY_EXISTS", path,
                        f"A RateSheet named '{name}' version {version} already exists. "
                        "Existing sheets are never updated; use a new version.",
                    )

        lines = self._list(obj["lines"], f"{path}.lines")
        line_count = tier_count = 0
        if lines is not None:
            if not lines:
                self.report.error("SHEET_HAS_NO_LINES", f"{path}.lines", "A rate sheet must contain at least one line.")
            sheet_context = {
                "path": path, "rate_type": rate_type, "transport_mode": transport_mode,
                "currency_code": currency_code, "valid_from": valid_from, "valid_until": valid_until,
                "valid_until_ok": valid_until_ok, "is_active": is_active,
                "supplier": supplier.id if supplier else None, "supplier_ok": supplier_ok,
                "customer": customer.id if customer else None, "customer_ok": customer_ok,
            }
            for index, line in enumerate(lines):
                line_count += 1
                tier_count += self._line(line, f"{path}.lines[{index}]", sheet_context)

        self.report.sheets.append({
            "path": path, "name": name, "version": version, "rate_type": rate_type,
            "transport_mode": transport_mode, "currency_code": currency_code,
            "valid_from": valid_from.isoformat() if valid_from else None,
            "valid_until": valid_until.isoformat() if valid_until else None,
            "is_active": is_active, "source_reference": source_reference,
            "lines": line_count, "tiers": tier_count,
        })

    # ------------------------------------------------------------------ lines

    def _line(self, entry: Any, path: str, sheet: dict[str, Any]) -> int:
        obj = self._object(entry, path, LINE_KEYS)
        if obj is None:
            return 0
        amount = {"nullable": True, "max_digits": 18, "decimal_places": 4}
        code = self._string(obj, "product_code", path)
        basis = self._choice(obj, "rate_basis", path, RateLine.RateBasis.values)
        # Amounts are validated for form only; pricing is not calculated in this phase.
        self._decimal(obj, "unit_rate", path, **amount)
        self._decimal(obj, "additive_flat_amount", path, **amount)
        min_charge = self._decimal(obj, "min_charge", path, **amount)
        max_charge = self._decimal(obj, "max_charge", path, **amount)
        self._decimal(obj, "percentage_rate", path, nullable=True, max_digits=5, decimal_places=2)

        code_ok = code is not None and self._resolve_line_code(code, f"{path}.product_code")

        basis_code = obj["percentage_basis_product_code"]
        if basis_code is not None:
            basis_code = self._string(obj, "percentage_basis_product_code", path)
            if basis_code is not None:
                self._resolve_line_code(basis_code, f"{path}.percentage_basis_product_code")

        if basis is not None:
            self._basis_rules(obj, basis, path)
        if min_charge is not None and max_charge is not None and min_charge > max_charge:
            self.report.error("MIN_EXCEEDS_MAX", f"{path}.min_charge", "min_charge must not exceed max_charge.")
        if obj["additive_flat_amount"] is not None and basis is not None and basis != "PER_KG":
            self.report.error(
                "ADDITIVE_FLAT_NOT_PER_KG", f"{path}.additive_flat_amount",
                f"additive_flat_amount is only permitted for PER_KG, not {basis}.",
            )

        applicability = self._applicability(obj["applicability"], f"{path}.applicability", sheet)
        tier_count = self._tiers(obj["tiers"], f"{path}.tiers", basis)

        essentials = (sheet["rate_type"], sheet["transport_mode"], sheet["currency_code"], sheet["valid_from"], sheet["is_active"])
        if (
            code_ok and applicability is not None and None not in essentials
            and sheet["valid_until_ok"] and sheet["supplier_ok"] and sheet["customer_ok"]
        ):
            self.rate_records.append({
                "label": path, "source": "manifest", "is_active": sheet["is_active"],
                "rate_type": sheet["rate_type"], "product_code": code,
                "transport_mode": sheet["transport_mode"], "currency_code": sheet["currency_code"],
                "valid_from": sheet["valid_from"], "valid_until": sheet["valid_until"],
                "supplier": sheet["supplier"], "customer": sheet["customer"], **applicability,
            })
        return tier_count

    def _basis_rules(self, obj: dict, basis: str, path: str) -> None:
        has_unit = obj["unit_rate"] is not None
        has_percent = obj["percentage_rate"] is not None
        has_percent_basis = obj["percentage_basis_product_code"] is not None
        if basis in SCALAR_BASES:
            if not has_unit:
                self.report.error("BASIS_FIELDS", f"{path}.unit_rate", f"{basis} requires unit_rate.")
            if has_percent:
                self.report.error("BASIS_FIELDS", f"{path}.percentage_rate", f"{basis} must not carry percentage_rate.")
            if has_percent_basis:
                self.report.error(
                    "BASIS_FIELDS", f"{path}.percentage_basis_product_code",
                    f"{basis} must not carry percentage_basis_product_code.",
                )
        elif basis == "TIERED_WEIGHT":
            if has_unit:
                self.report.error("BASIS_FIELDS", f"{path}.unit_rate", "TIERED_WEIGHT rates belong on tiers, not unit_rate.")
            if has_percent:
                self.report.error("BASIS_FIELDS", f"{path}.percentage_rate", "TIERED_WEIGHT must not carry percentage_rate.")
            if has_percent_basis:
                self.report.error(
                    "BASIS_FIELDS", f"{path}.percentage_basis_product_code",
                    "TIERED_WEIGHT must not carry percentage_basis_product_code.",
                )
        elif basis == "PERCENTAGE":
            if not has_percent:
                self.report.error("BASIS_FIELDS", f"{path}.percentage_rate", "PERCENTAGE requires percentage_rate.")
            if not has_percent_basis:
                self.report.error(
                    "BASIS_FIELDS", f"{path}.percentage_basis_product_code",
                    "PERCENTAGE requires percentage_basis_product_code.",
                )
            if has_unit:
                self.report.error("BASIS_FIELDS", f"{path}.unit_rate", "PERCENTAGE must not carry unit_rate.")

    def _applicability(self, entry: Any, path: str, sheet: dict[str, Any]) -> dict[str, Any] | None:
        obj = self._object(entry, path, APPLICABILITY_KEYS)
        if obj is None:
            return None
        direction = self._choice(obj, "direction", path, RateApplicability.Direction.values)
        payment_term = self._choice(obj, "payment_term", path, RateApplicability.PaymentTerm.values, allow_blank=True)
        service_level = self._choice(obj, "service_level", path, RateApplicability.ServiceLevel.values, allow_blank=True)
        commodity = self._string(obj, "commodity_category", path, allow_blank=True, max_length=64)
        equipment = self._string(obj, "equipment_type", path, allow_blank=True, max_length=64)
        origin_ok, origin = self._geo(obj, "origin_iata", path, sheet["transport_mode"])
        destination_ok, destination = self._geo(obj, "destination_iata", path, sheet["transport_mode"])

        if payment_term and sheet["rate_type"] == "BUY":
            self.report.error(
                "BUY_PAYMENT_TERM_NOT_BLANK", f"{path}.payment_term",
                "BUY rates must use a blank payment_term.",
            )
            payment_term = None
        if origin is not None and destination is not None and origin.id == destination.id:
            self.report.error("ORIGIN_EQUALS_DESTINATION", path, "Origin and destination resolve to the same location.")
            origin_ok = False
        if origin_ok and destination_ok and origin is None and destination is None:
            self.report.warn(
                "APPLICABILITY_ANY_LOCATION", path,
                "No origin or destination is set; the rate would apply to every route.",
            )
        if None in (direction, payment_term, service_level, commodity, equipment) or not (origin_ok and destination_ok):
            return None
        return {
            "direction": direction, "payment_term": payment_term, "service_level": service_level,
            "commodity_category": commodity, "equipment_type": equipment,
            "origin": origin.id if origin else None, "destination": destination.id if destination else None,
        }

    # ------------------------------------------------------------------ tiers

    def _tiers(self, entry: Any, path: str, basis: str | None) -> int:
        tiers = self._list(entry, path)
        if tiers is None:
            return 0
        if basis != "TIERED_WEIGHT":
            if tiers and basis is not None:
                self.report.error("TIERS_NOT_ALLOWED", path, f"{basis} lines must have an empty tiers array.")
            return 0
        if not tiers:
            self.report.error("TIERS_REQUIRED", path, "TIERED_WEIGHT requires at least one tier.")
            return 0

        parsed = []
        for index, tier in enumerate(tiers):
            tier_path = f"{path}[{index}]"
            obj = self._object(tier, tier_path, TIER_KEYS)
            if obj is None:
                return len(tiers)
            lower = self._decimal(obj, "min_quantity", tier_path, nullable=False, max_digits=12, decimal_places=4)
            upper = self._decimal(obj, "max_quantity", tier_path, nullable=True, max_digits=12, decimal_places=4)
            rate = self._decimal(obj, "unit_rate", tier_path, nullable=False, max_digits=18, decimal_places=4)
            if lower is None or rate is None or (obj["max_quantity"] is not None and upper is None):
                return len(tiers)
            if upper is not None and upper <= lower:
                self.report.error("TIER_BOUNDS", tier_path, "max_quantity must be greater than min_quantity.")
                return len(tiers)
            parsed.append((lower, upper, tier_path))

        # Tiers are [min_quantity, max_quantity): lower inclusive, upper exclusive.
        if parsed[0][0] != 0:
            self.report.error("TIER_COVERAGE_START", parsed[0][2], "The first tier must start at 0.")
        for (_lower, upper, tier_path), (next_lower, _next_upper, next_path) in pairwise(parsed):
            if upper is None:
                self.report.error("TIER_OPEN_ENDED_NOT_LAST", tier_path, "Only the final tier may be open-ended.")
            elif next_lower > upper:
                self.report.error("TIER_GAP", next_path, f"Gap between {upper} and {next_lower}; tiers must be contiguous.")
            elif next_lower < upper:
                self.report.error("TIER_OVERLAP", next_path, f"Tier starts at {next_lower}, before the previous tier ends at {upper}.")
        if parsed[-1][1] is not None:
            self.report.error(
                "TIER_COVERAGE_END", parsed[-1][2],
                "The final tier must be open-ended (max_quantity null); coverage is incomplete.",
            )
        return len(tiers)

    # -------------------------------------------------------------- conflicts

    def _existing_rate_records(self) -> list[dict[str, Any]]:
        records = []
        lines = (
            RateLine.objects.using(self.using).filter(sheet__is_active=True)
            .select_related("sheet", "product_code", "applicability")
            .order_by("sheet__name", "sheet__version", "product_code__code", "id")
        )
        for line in lines:
            sheet = line.sheet
            applicability = getattr(line, "applicability", None)
            records.append({
                "label": f"existing RateSheet \"{sheet.name}\" v{sheet.version} line {line.product_code.code}",
                "source": "existing", "is_active": True,
                "rate_type": sheet.rate_type, "product_code": line.product_code.code,
                "transport_mode": sheet.transport_mode, "currency_code": sheet.currency_code,
                "valid_from": sheet.valid_from, "valid_until": sheet.valid_until,
                "supplier": sheet.carrier_id, "customer": sheet.party_id,
                "direction": applicability.direction if applicability else "",
                "payment_term": applicability.payment_term if applicability else "",
                "service_level": applicability.service_level if applicability else "",
                "commodity_category": applicability.commodity_category if applicability else "",
                "equipment_type": applicability.equipment_type if applicability else "",
                "origin": applicability.origin_id if applicability else None,
                "destination": applicability.destination_id if applicability else None,
            })
        return records

    @staticmethod
    def _windows_overlap(a: dict[str, Any], b: dict[str, Any]) -> bool:
        # End dates are treated as inclusive, the conservative reading: a sheet ending
        # on the day another starts is reported as overlapping.
        a_ends_before_b = a["valid_until"] is not None and a["valid_until"] < b["valid_from"]
        b_ends_before_a = b["valid_until"] is not None and b["valid_until"] < a["valid_from"]
        return not (a_ends_before_b or b_ends_before_a)

    def _classify(self, a: dict[str, Any], b: dict[str, Any]) -> str | None:
        if not (a["is_active"] and b["is_active"]):
            return None
        if any(a[dim] != b[dim] for dim in EXACT_DIMENSIONS):
            return None
        if not self._windows_overlap(a, b):
            return None
        differing = [dim for dim in WILDCARD_DIMENSIONS if a[dim] != b[dim]]
        if any(not (_is_blank(a[dim]) or _is_blank(b[dim])) for dim in differing):
            return None
        if not differing:
            return "RATE_DUPLICATE_IDENTITY"
        if differing == ["payment_term"]:
            return "RATE_PAYMENT_TERM_COEXISTENCE"
        return "RATE_AMBIGUOUS_MATCH"

    def _detect_rate_conflicts(self) -> None:
        messages = {
            "RATE_DUPLICATE_IDENTITY": "Same rate identity with overlapping validity as {other}.",
            "RATE_PAYMENT_TERM_COEXISTENCE": (
                "A blank (any) payment term and a specific payment term coexist for the same "
                "otherwise-identical active rate with overlapping validity: {other}."
            ),
            "RATE_AMBIGUOUS_MATCH": (
                "More than one rate could match the same quote context with overlapping validity "
                "(a blank dimension overlaps a specific one): {other}. No precedence is applied."
            ),
        }
        manifest_records = self.rate_records
        existing = self._existing_rate_records() if manifest_records else []
        for index, record in enumerate(manifest_records):
            for other in manifest_records[:index] + existing:
                code = self._classify(record, other)
                if code:
                    self.report.error(code, record["label"], messages[code].format(other=other["label"]))
