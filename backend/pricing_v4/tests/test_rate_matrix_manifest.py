"""Pilot Gate B3C: dry-run Rate Matrix manifest validation.

Every value here is synthetic test data. No real tariff, party, or rate appears.
"""

import copy
import datetime
import json
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialChargeAlias, CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_manifest import (
    read_only_database,
    validate_manifest,
    validate_manifest_text,
)

GUARDED = (CommercialProductCode, CommercialChargeAlias, RateSheet, RateLine, RateApplicability, RateTier)

FREIGHT = "EXP-SYNTH-FRT"
SCREEN = "EXP-SYNTH-SCREEN"
FSC = "EXP-SYNTH-FSC"
RETIRED = "EXP-SYNTH-RETIRED"
INACTIVE = "EXP-SYNTH-INACTIVE"


def _legacy(pk, code, gst=ProductCode.GST_TREATMENT_STANDARD, **extra):
    return ProductCode.objects.create(
        id=pk, code=code, description=f"Synthetic {code}", domain=ProductCode.DOMAIN_EXPORT,
        category=ProductCode.CATEGORY_HANDLING, is_gst_applicable=True, gst_rate="0.10",
        gst_treatment=gst, gl_revenue_code="4000", gl_cost_code="5000",
        default_unit=ProductCode.UNIT_SHIPMENT, **extra,
    )


def _airport(name, iata, **extra):
    # Built and saved directly: the legacy-Location guardrail test matches this text pattern.
    location = GeoLocation(
        canonical_name=name, country_code="ZZ", location_type=extra.pop("location_type", "AIRPORT"), **extra
    )
    location.save()
    GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=iata)
    return location


def _party(name, role, **extra):
    party = PartyMaster.objects.create(legal_name=name, entity_type="COMPANY", country_code="ZZ", **extra)
    PartyRole.objects.create(party=party, role_type=role)
    return party


@pytest.fixture
def world(db):
    """Synthetic master data the manifest resolves against."""
    for code in ("XTS", "XXA"):
        Currency.objects.get_or_create(code=code, defaults={"name": f"Synthetic {code}"})
    data = {
        "legacy_freight": _legacy(1901, FREIGHT, gst=ProductCode.GST_TREATMENT_ZERO_RATED),
        "legacy_screen": _legacy(1902, SCREEN),
        "legacy_fsc": _legacy(1903, FSC),
        "legacy_retired": _legacy(1904, RETIRED, is_active=False, retired_at=timezone.now()),
        "legacy_inactive": _legacy(1905, INACTIVE, is_active=False),
        "xaa": _airport("Synthetic Airport A", "XAA"),
        "xbb": _airport("Synthetic Airport B", "XBB"),
        "xcc_inactive": _airport("Synthetic Airport C", "XCC", is_active=False),
        "xdd_city": _airport("Synthetic City D", "XDD", location_type="CITY"),
        "carrier": _party("Synthetic Carrier Ltd", "CARRIER"),
        "agent": _party("Synthetic Agent Pty", "AGENT"),
        "customer": _party("Synthetic Customer Ltd", "CUSTOMER"),
        "dormant": _party("Synthetic Dormant Ltd", "CARRIER", is_active=False),
        "user": get_user_model().objects.create_user(username="synthetic-loader", password="x"),
    }
    return data


def _code(code, legacy_id, gst="STANDARD", category="ORIGIN", basis="FLAT"):
    return {
        "code": code, "name": f"Synthetic {code}", "category": category, "sub_category": "",
        "gst_treatment": gst, "charge_basis_default": basis, "is_active": True,
        "legacy_product_code": {"id": legacy_id, "code": code},
    }


def _applicability(**overrides):
    values = {
        "direction": "EXPORT", "origin_iata": "XAA", "destination_iata": "XBB", "payment_term": "",
        "service_level": "", "commodity_category": "", "equipment_type": "",
    }
    values.update(overrides)
    return values


def _line(product_code, basis, **overrides):
    values = {
        "product_code": product_code, "rate_basis": basis, "unit_rate": None, "additive_flat_amount": None,
        "min_charge": None, "max_charge": None, "percentage_rate": None,
        "percentage_basis_product_code": None, "applicability": _applicability(), "tiers": [],
    }
    values.update(overrides)
    return values


def _sheet(name, rate_type, lines, **overrides):
    values = {
        "name": name, "version": 1, "rate_type": rate_type, "transport_mode": "AIR", "currency_code": "XTS",
        "valid_from": "2030-01-01", "valid_until": "2030-12-31", "is_active": True,
        "source_reference": "SYNTHETIC-TEST-TARIFF", "supplier": None, "customer": None, "lines": lines,
    }
    values.update(overrides)
    return values


CARRIER_REF = {"legal_name": "Synthetic Carrier Ltd", "country_code": "ZZ", "role": "CARRIER"}
TIERS = [
    {"min_quantity": "0", "max_quantity": "100", "unit_rate": "1.11"},
    {"min_quantity": "100", "max_quantity": "500", "unit_rate": "1.05"},
    {"min_quantity": "500", "max_quantity": None, "unit_rate": "0.99"},
]


def valid_manifest():
    return {
        "manifest_version": 1,
        "product_codes": [
            _code(FREIGHT, 1901, gst="ZERO_RATED", category="FREIGHT", basis="TIERED_WEIGHT"),
            _code(SCREEN, 1902, basis="PER_KG"),
            _code(FSC, 1903, basis="PERCENTAGE"),
        ],
        "rate_sheets": [
            _sheet(
                "Synthetic BUY Sheet", "BUY",
                [_line(FREIGHT, "TIERED_WEIGHT", min_charge="11.00", tiers=copy.deepcopy(TIERS))],
                supplier=dict(CARRIER_REF),
            ),
            _sheet(
                "Synthetic SELL Sheet", "SELL",
                [
                    _line(
                        SCREEN, "PER_KG", unit_rate="0.22", additive_flat_amount="4.50",
                        applicability=_applicability(destination_iata=None, payment_term="PREPAID"),
                    ),
                    _line(
                        FSC, "PERCENTAGE", percentage_rate="10.00", percentage_basis_product_code=SCREEN,
                        applicability=_applicability(destination_iata=None),
                    ),
                ],
            ),
        ],
    }


def snapshot():
    """Row counts for the guarded tables and the full content of legacy product_codes."""
    return {
        "counts": {model._meta.db_table: model.objects.count() for model in GUARDED},
        "legacy": list(ProductCode.objects.order_by("id").values()),
        "geo": GeoLocation.objects.count(),
        "parties": PartyMaster.objects.count(),
    }


def codes(report):
    return [(issue.code, issue.path) for issue in report.errors]


def assert_error(report, code, path):
    assert (code, path) in codes(report), f"expected {code} at {path}, got {codes(report)}"
    assert not report.passed


# --------------------------------------------------------------------------- happy path


@pytest.mark.django_db
class TestValidManifest:
    def test_passes_and_reports_proposals(self, world):
        report = validate_manifest(valid_manifest())
        assert report.errors == []
        assert report.warnings == []
        assert report.passed
        assert report.counts() == {
            "product_codes_create": 3, "product_codes_reuse": 0, "geography_reuse": 2, "parties_reuse": 1,
            "rate_sheets_create": 2, "rate_lines_create": 3, "rate_applicabilities_create": 3,
            "rate_tiers_create": 3, "errors": 0, "warnings": 0,
        }
        assert [pc["code"] for pc in report.product_codes] == [FREIGHT, FSC, SCREEN]
        assert {pc["action"] for pc in report.product_codes} == {"CREATE"}
        assert [geo["iata"] for geo in report.geography] == ["XAA", "XBB"]
        assert report.geography[0]["id"] == str(world["xaa"].id)
        assert report.parties == [{
            "role": "CARRIER", "legal_name": "Synthetic Carrier Ltd", "country_code": "ZZ",
            "id": str(world["carrier"].id),
        }]

    def test_text_report_states_dry_run_and_result(self, world):
        text = validate_manifest(valid_manifest()).render_text()
        assert "Mode: DRY RUN" in text
        assert "Result: PASS" in text
        assert text.rstrip().endswith("Writes performed: 0")
        assert f"CREATE {FREIGHT} -> legacy ProductCode 1901" in text
        assert "XAA -> Synthetic Airport A" in text
        assert '"Synthetic BUY Sheet" v1 BUY AIR XTS 2030-01-01..2030-12-31' in text

    def test_json_report_shape(self, world):
        payload = json.loads(validate_manifest(valid_manifest()).render_json())
        assert payload["mode"] == "DRY_RUN"
        assert payload["writes_performed"] == 0
        assert payload["result"] == "PASS"
        assert payload["errors"] == []

    def test_existing_identical_product_code_is_reused(self, world):
        CommercialProductCode.objects.create(
            code=SCREEN, name=f"Synthetic {SCREEN}", category="ORIGIN", gst_treatment="STANDARD",
            charge_basis_default="PER_KG", legacy_product_code=world["legacy_screen"],
        )
        report = validate_manifest(valid_manifest())
        assert report.passed
        actions = {pc["code"]: pc["action"] for pc in report.product_codes}
        assert actions == {FREIGHT: "CREATE", FSC: "CREATE", SCREEN: "REUSE"}

    def test_line_may_reference_existing_mapped_code_not_in_manifest(self, world):
        CommercialProductCode.objects.create(
            code=SCREEN, name="Existing", category="ORIGIN", gst_treatment="STANDARD",
            charge_basis_default="PER_KG", legacy_product_code=world["legacy_screen"],
        )
        manifest = valid_manifest()
        manifest["product_codes"] = [pc for pc in manifest["product_codes"] if pc["code"] != SCREEN]
        report = validate_manifest(manifest)
        assert report.passed
        reused = next(pc for pc in report.product_codes if pc["code"] == SCREEN)
        assert (reused["action"], reused["origin"]) == ("REUSE", "existing")


# --------------------------------------------------------------------------- zero writes


@pytest.mark.django_db
class TestNoWrites:
    def test_successful_dry_run_leaves_database_unchanged(self, world):
        before = snapshot()
        assert validate_manifest(valid_manifest()).passed
        assert snapshot() == before
        assert all(count == 0 for count in before["counts"].values())

    def test_invalid_manifest_leaves_database_unchanged(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["currency_code"] = "QQQ"
        manifest["rate_sheets"][1]["lines"][0]["additive_flat_amount"] = "-1"
        manifest["product_codes"][0]["legacy_product_code"]["id"] = 999999
        before = snapshot()
        assert not validate_manifest(manifest).passed
        assert snapshot() == before

    def test_malformed_json_leaves_database_unchanged(self, world):
        before = snapshot()
        assert not validate_manifest_text("{not json").passed
        assert snapshot() == before

    def test_only_read_statements_are_issued(self, world):
        with CaptureQueriesContext(connection) as queries:
            validate_manifest(valid_manifest())
        statements = [query["sql"].lstrip().upper() for query in queries]
        assert statements
        writes = [
            sql for sql in statements
            if sql.split(None, 1)[0] in {"INSERT", "UPDATE", "DELETE", "CREATE", "ALTER", "DROP", "TRUNCATE"}
        ]
        assert writes == []

    def test_repeated_dry_runs_are_identical(self, world):
        first = validate_manifest(valid_manifest())
        second = validate_manifest(valid_manifest())
        assert first.render_text() == second.render_text()
        assert first.render_json() == second.render_json()

    def test_repeated_failing_dry_runs_are_identical(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["tiers"][1]["min_quantity"] = "150"
        manifest["rate_sheets"][1]["source_reference"] = ""
        first = validate_manifest(copy.deepcopy(manifest))
        second = validate_manifest(copy.deepcopy(manifest))
        assert not first.passed
        assert first.render_text() == second.render_text()

    def test_connection_refuses_writes_inside_validation(self, world):
        with pytest.raises(DatabaseError), read_only_database():
            PartyMaster.objects.create(legal_name="Must Not Persist", entity_type="X", country_code="ZZ")
        assert not PartyMaster.objects.filter(legal_name="Must Not Persist").exists()

    def test_connection_is_writable_again_afterwards(self, world):
        validate_manifest(valid_manifest())
        party = PartyMaster.objects.create(legal_name="Written After", entity_type="X", country_code="ZZ")
        assert PartyMaster.objects.filter(pk=party.pk).exists()


# --------------------------------------------------------------------------- strict manifest


@pytest.mark.django_db
class TestStrictManifest:
    def test_invalid_json_fails_closed(self, world):
        report = validate_manifest_text("{not json")
        assert_error(report, "MANIFEST_NOT_STRICT_JSON", "$")

    def test_duplicate_keys_rejected(self, world):
        report = validate_manifest_text('{"manifest_version": 1, "manifest_version": 1, "product_codes": [], "rate_sheets": []}')
        assert_error(report, "MANIFEST_NOT_STRICT_JSON", "$")
        assert "Duplicate key" in report.errors[0].message

    def test_non_finite_number_rejected(self, world):
        report = validate_manifest_text('{"manifest_version": NaN, "product_codes": [], "rate_sheets": []}')
        assert_error(report, "MANIFEST_NOT_STRICT_JSON", "$")

    def test_unsupported_version(self, world):
        manifest = valid_manifest()
        manifest["manifest_version"] = 2
        assert_error(validate_manifest(manifest), "MANIFEST_VERSION", "$.manifest_version")

    def test_unknown_field_rejected(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["fx_rate"] = "2.50"
        manifest["rate_sheets"][0]["lines"][0]["converted_amount"] = "9.99"
        report = validate_manifest(manifest)
        assert_error(report, "MANIFEST_UNKNOWN_FIELD", "$.rate_sheets[0].fx_rate")

    def test_unknown_line_field_rejected(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["converted_amount"] = "9.99"
        assert_error(
            validate_manifest(manifest), "MANIFEST_UNKNOWN_FIELD", "$.rate_sheets[1].lines[0].converted_amount"
        )

    def test_missing_field_rejected(self, world):
        manifest = valid_manifest()
        del manifest["rate_sheets"][1]["lines"][0]["min_charge"]
        del manifest["product_codes"][0]["category"]
        report = validate_manifest(manifest)
        assert_error(report, "MANIFEST_MISSING_FIELD", "$.rate_sheets[1].lines[0].min_charge")
        assert_error(report, "MANIFEST_MISSING_FIELD", "$.product_codes[0].category")

    @pytest.mark.parametrize(
        "value, code",
        [
            (0.22, "DECIMAL_NOT_STRING"),
            (1, "DECIMAL_NOT_STRING"),
            ("-0.22", "NEGATIVE_AMOUNT"),
            ("0.22222", "DECIMAL_PRECISION"),
            ("1e3", "DECIMAL_INVALID"),
            ("abc", "DECIMAL_INVALID"),
        ],
    )
    def test_amounts_must_be_plain_non_negative_decimal_strings(self, world, value, code):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["unit_rate"] = value
        assert_error(validate_manifest(manifest), code, "$.rate_sheets[1].lines[0].unit_rate")


# --------------------------------------------------------------------------- product codes


@pytest.mark.django_db
class TestProductCodeRules:
    def test_legacy_product_code_must_exist(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][0]["legacy_product_code"]["id"] = 999999
        report = validate_manifest(manifest)
        assert_error(report, "LEGACY_PRODUCT_CODE_NOT_FOUND", "$.product_codes[0].legacy_product_code.id")
        assert_error(report, "PRODUCT_CODE_PROPOSAL_INVALID", "$.rate_sheets[0].lines[0].product_code")

    def test_legacy_code_must_match_exactly(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][1]["legacy_product_code"]["code"] = "EXP-SYNTH-SCREENING"
        assert_error(validate_manifest(manifest), "LEGACY_PRODUCT_CODE_MISMATCH", "$.product_codes[1].legacy_product_code.code")

    def test_proposed_code_must_mirror_legacy_code(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][1]["code"] = "EXP-SYNTH-SCREEN-NEW"
        assert_error(validate_manifest(manifest), "PRODUCT_CODE_NOT_EXACT_MIRROR", "$.product_codes[1].legacy_product_code")

    @pytest.mark.parametrize("legacy_id, code", [(1904, RETIRED), (1905, INACTIVE)])
    def test_inactive_or_retired_legacy_code_rejected(self, world, legacy_id, code):
        manifest = valid_manifest()
        manifest["product_codes"].append(_code(code, legacy_id))
        assert_error(validate_manifest(manifest), "LEGACY_PRODUCT_CODE_INACTIVE", "$.product_codes[3].legacy_product_code.id")

    def test_gst_treatment_must_match_legacy(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][0]["gst_treatment"] = "STANDARD"
        assert_error(validate_manifest(manifest), "GST_TREATMENT_MISMATCH", "$.product_codes[0].legacy_product_code")

    def test_category_and_basis_are_not_inferred(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][0]["category"] = ""
        manifest["product_codes"][1]["charge_basis_default"] = "PER_SHIPMENT"
        report = validate_manifest(manifest)
        assert_error(report, "VALUE_REQUIRED", "$.product_codes[0].category")
        assert_error(report, "VALUE_NOT_ALLOWED", "$.product_codes[1].charge_basis_default")

    def test_gst_vocabulary_limited_to_three_classes(self, world):
        manifest = valid_manifest()
        manifest["product_codes"][0]["gst_treatment"] = "OUT_OF_SCOPE"
        assert_error(validate_manifest(manifest), "VALUE_NOT_ALLOWED", "$.product_codes[0].gst_treatment")

    def test_duplicate_code_in_manifest(self, world):
        manifest = valid_manifest()
        manifest["product_codes"].append(copy.deepcopy(manifest["product_codes"][1]))
        assert_error(validate_manifest(manifest), "PRODUCT_CODE_DUPLICATE_IN_MANIFEST", "$.product_codes[3].code")

    def test_existing_mapping_to_other_legacy_code_conflicts(self, world):
        CommercialProductCode.objects.create(
            code=SCREEN, name="Existing", category="ORIGIN", gst_treatment="STANDARD",
            charge_basis_default="PER_KG", legacy_product_code=world["legacy_fsc"],
        )
        manifest = valid_manifest()
        manifest["product_codes"] = [manifest["product_codes"][1]]
        manifest["rate_sheets"] = []
        assert_error(validate_manifest(manifest), "PRODUCT_CODE_MAPPING_CONFLICT", "$.product_codes[0]")

    def test_legacy_code_already_mapped_under_another_commercial_code(self, world):
        CommercialProductCode.objects.create(
            code="OTHER-CODE", name="Existing", category="ORIGIN", gst_treatment="STANDARD",
            charge_basis_default="PER_KG", legacy_product_code=world["legacy_screen"],
        )
        manifest = valid_manifest()
        assert_error(
            validate_manifest(manifest), "PRODUCT_CODE_MAPPING_CONFLICT", "$.product_codes[1].legacy_product_code.id"
        )

    def test_existing_unmapped_code_conflicts(self, world):
        CommercialProductCode.objects.create(
            code=SCREEN, name=f"Synthetic {SCREEN}", category="ORIGIN", gst_treatment="STANDARD",
            charge_basis_default="PER_KG",
        )
        assert_error(validate_manifest(valid_manifest()), "PRODUCT_CODE_MAPPING_CONFLICT", "$.product_codes[1]")

    def test_existing_row_with_different_fields_is_never_updated(self, world):
        existing = CommercialProductCode.objects.create(
            code=SCREEN, name="A Different Name", category="DESTINATION", gst_treatment="STANDARD",
            charge_basis_default="PER_KG", legacy_product_code=world["legacy_screen"],
        )
        report = validate_manifest(valid_manifest())
        assert_error(report, "PRODUCT_CODE_EXISTING_DIFFERS", "$.product_codes[1]")
        existing.refresh_from_db()
        assert (existing.name, existing.category) == ("A Different Name", "DESTINATION")

    def test_line_referencing_unknown_code(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["product_code"] = "EXP-NOT-A-CODE"
        assert_error(validate_manifest(manifest), "PRODUCT_CODE_UNRESOLVED", "$.rate_sheets[1].lines[0].product_code")

    def test_percentage_basis_code_must_resolve(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][1]["percentage_basis_product_code"] = "EXP-NOT-A-CODE"
        assert_error(
            validate_manifest(manifest), "PRODUCT_CODE_UNRESOLVED",
            "$.rate_sheets[1].lines[1].percentage_basis_product_code",
        )


# --------------------------------------------------------------------------- geography and parties


@pytest.mark.django_db
class TestGeographyAndParties:
    @pytest.mark.parametrize(
        "iata, code",
        [
            ("XZZ", "GEOGRAPHY_NOT_FOUND"),
            ("XCC", "GEOGRAPHY_INACTIVE"),
            ("XDD", "GEOGRAPHY_NOT_AIRPORT"),
            ("xaa", "IATA_INVALID"),
            ("XAAA", "IATA_INVALID"),
        ],
    )
    def test_unresolvable_geography_fails_closed(self, world, iata, code):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["applicability"]["destination_iata"] = iata
        assert_error(validate_manifest(manifest), code, "$.rate_sheets[0].lines[0].applicability.destination_iata")

    def test_same_origin_and_destination_rejected(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["applicability"]["destination_iata"] = "XAA"
        assert_error(validate_manifest(manifest), "ORIGIN_EQUALS_DESTINATION", "$.rate_sheets[0].lines[0].applicability")

    def test_no_location_is_a_warning_not_an_error(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["applicability"].update(origin_iata=None, destination_iata=None)
        report = validate_manifest(manifest)
        assert report.passed
        assert [(w.code, w.path) for w in report.warnings] == [
            ("APPLICABILITY_ANY_LOCATION", "$.rate_sheets[0].lines[0].applicability")
        ]

    def test_geography_tables_are_not_extended(self, world):
        before = (GeoLocation.objects.count(), GeoLocationIdentifier.objects.count())
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["applicability"]["destination_iata"] = "XZZ"
        validate_manifest(manifest)
        assert (GeoLocation.objects.count(), GeoLocationIdentifier.objects.count()) == before

    @pytest.mark.parametrize(
        "ref, code, suffix",
        [
            ({"legal_name": "Nobody Ltd", "country_code": "ZZ", "role": "CARRIER"}, "PARTY_NOT_FOUND", ""),
            ({"legal_name": "Synthetic Carrier Ltd", "country_code": "YY", "role": "CARRIER"}, "PARTY_NOT_FOUND", ""),
            ({"legal_name": "Synthetic Carrier Ltd", "country_code": "ZZ", "role": "AGENT"}, "PARTY_ROLE_MISSING", ".role"),
            ({"legal_name": "Synthetic Dormant Ltd", "country_code": "ZZ", "role": "CARRIER"}, "PARTY_INACTIVE", ""),
            ({"legal_name": "Synthetic Carrier Ltd", "country_code": "ZZ", "role": "CUSTOMER"}, "VALUE_NOT_ALLOWED", ".role"),
        ],
    )
    def test_unresolvable_supplier_fails_closed(self, world, ref, code, suffix):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = ref
        assert_error(validate_manifest(manifest), code, f"$.rate_sheets[0].supplier{suffix}")
        assert PartyMaster.objects.filter(legal_name="Nobody Ltd").count() == 0

    def test_agent_supplier_resolves(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = {"legal_name": "Synthetic Agent Pty", "country_code": "ZZ", "role": "AGENT"}
        report = validate_manifest(manifest)
        assert report.passed
        assert report.parties[0]["role"] == "AGENT"

    def test_customer_resolves_on_sell_sheet(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["customer"] = {"legal_name": "Synthetic Customer Ltd", "country_code": "ZZ", "role": "CUSTOMER"}
        report = validate_manifest(manifest)
        assert report.passed
        assert ("CUSTOMER", "Synthetic Customer Ltd") in {(p["role"], p["legal_name"]) for p in report.parties}

    def test_party_scope_must_match_sheet_side(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["customer"] = {"legal_name": "Synthetic Customer Ltd", "country_code": "ZZ", "role": "CUSTOMER"}
        manifest["rate_sheets"][1]["supplier"] = dict(CARRIER_REF)
        report = validate_manifest(manifest)
        assert_error(report, "BUY_SHEET_HAS_CUSTOMER", "$.rate_sheets[0].customer")
        assert_error(report, "SELL_SHEET_HAS_SUPPLIER", "$.rate_sheets[1].supplier")

    def test_buy_sheet_without_supplier_warns(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = None
        report = validate_manifest(manifest)
        assert report.passed
        assert [w.code for w in report.warnings] == ["BUY_SHEET_WITHOUT_SUPPLIER"]


# --------------------------------------------------------------------------- rate rules


def _mutate_sheet(index, **changes):
    def apply(manifest):
        manifest["rate_sheets"][index].update(changes)
    return apply


def _mutate_line(sheet, line, **changes):
    def apply(manifest):
        manifest["rate_sheets"][sheet]["lines"][line].update(changes)
    return apply


def _mutate_applicability(sheet, line, **changes):
    def apply(manifest):
        manifest["rate_sheets"][sheet]["lines"][line]["applicability"].update(changes)
    return apply


RATE_RULE_CASES = [
    (_mutate_sheet(0, currency_code="QQQ"), "CURRENCY_UNKNOWN", "$.rate_sheets[0].currency_code"),
    (_mutate_sheet(0, currency_code="xts"), "CURRENCY_INVALID", "$.rate_sheets[0].currency_code"),
    (_mutate_sheet(0, source_reference=""), "VALUE_REQUIRED", "$.rate_sheets[0].source_reference"),
    (_mutate_sheet(0, source_reference="  padded  "), "VALUE_NOT_TRIMMED", "$.rate_sheets[0].source_reference"),
    (_mutate_sheet(0, source_reference=None), "MANIFEST_TYPE", "$.rate_sheets[0].source_reference"),
    (_mutate_sheet(0, rate_type="MARGIN"), "VALUE_NOT_ALLOWED", "$.rate_sheets[0].rate_type"),
    (_mutate_sheet(0, version=0), "VERSION_INVALID", "$.rate_sheets[0].version"),
    (_mutate_sheet(0, version="1"), "VERSION_INVALID", "$.rate_sheets[0].version"),
    (_mutate_sheet(0, is_active="yes"), "MANIFEST_TYPE", "$.rate_sheets[0].is_active"),
    (_mutate_sheet(0, valid_from="2030-13-01"), "DATE_INVALID", "$.rate_sheets[0].valid_from"),
    (_mutate_sheet(0, valid_until="2030-01-01"), "VALIDITY_WINDOW_INVALID", "$.rate_sheets[0].valid_until"),
    (_mutate_sheet(0, valid_until="2029-06-01"), "VALIDITY_WINDOW_INVALID", "$.rate_sheets[0].valid_until"),
    (_mutate_sheet(0, lines=[]), "SHEET_HAS_NO_LINES", "$.rate_sheets[0].lines"),
    (_mutate_applicability(0, 0, payment_term="PREPAID"), "BUY_PAYMENT_TERM_NOT_BLANK", "$.rate_sheets[0].lines[0].applicability.payment_term"),
    (_mutate_applicability(1, 0, payment_term="ANY"), "VALUE_NOT_ALLOWED", "$.rate_sheets[1].lines[0].applicability.payment_term"),
    (_mutate_applicability(1, 0, direction=""), "VALUE_REQUIRED", "$.rate_sheets[1].lines[0].applicability.direction"),
    (_mutate_applicability(1, 0, service_level="OVERNIGHT"), "VALUE_NOT_ALLOWED", "$.rate_sheets[1].lines[0].applicability.service_level"),
    (_mutate_line(1, 0, rate_basis="FLAT"), "ADDITIVE_FLAT_NOT_PER_KG", "$.rate_sheets[1].lines[0].additive_flat_amount"),
    (_mutate_line(1, 0, additive_flat_amount="-4.50"), "NEGATIVE_AMOUNT", "$.rate_sheets[1].lines[0].additive_flat_amount"),
    (_mutate_line(1, 0, unit_rate=None), "BASIS_FIELDS", "$.rate_sheets[1].lines[0].unit_rate"),
    (_mutate_line(1, 0, percentage_rate="5.00"), "BASIS_FIELDS", "$.rate_sheets[1].lines[0].percentage_rate"),
    (_mutate_line(1, 0, min_charge="9.00", max_charge="8.00"), "MIN_EXCEEDS_MAX", "$.rate_sheets[1].lines[0].min_charge"),
    (_mutate_line(1, 1, percentage_rate=None), "BASIS_FIELDS", "$.rate_sheets[1].lines[1].percentage_rate"),
    (_mutate_line(1, 1, percentage_basis_product_code=None), "BASIS_FIELDS", "$.rate_sheets[1].lines[1].percentage_basis_product_code"),
    (_mutate_line(1, 1, unit_rate="1.00"), "BASIS_FIELDS", "$.rate_sheets[1].lines[1].unit_rate"),
    (_mutate_line(1, 1, percentage_rate="10.005"), "DECIMAL_PRECISION", "$.rate_sheets[1].lines[1].percentage_rate"),
    (_mutate_line(0, 0, unit_rate="1.00"), "BASIS_FIELDS", "$.rate_sheets[0].lines[0].unit_rate"),
    (_mutate_line(0, 0, rate_basis="PER_HOUR"), "VALUE_NOT_ALLOWED", "$.rate_sheets[0].lines[0].rate_basis"),
    (_mutate_line(0, 0, tiers=[]), "TIERS_REQUIRED", "$.rate_sheets[0].lines[0].tiers"),
    (_mutate_line(1, 0, tiers=copy.deepcopy(TIERS)), "TIERS_NOT_ALLOWED", "$.rate_sheets[1].lines[0].tiers"),
]


@pytest.mark.django_db
class TestRateRules:
    @pytest.mark.parametrize("mutate, code, path", RATE_RULE_CASES, ids=[f"{c[1]}@{c[2]}" for c in RATE_RULE_CASES])
    def test_rule(self, world, mutate, code, path):
        manifest = valid_manifest()
        mutate(manifest)
        assert_error(validate_manifest(manifest), code, path)

    def test_open_ended_validity_is_valid(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["valid_until"] = None
        assert validate_manifest(manifest).passed

    def test_duplicate_sheet_name_and_version_in_manifest(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["name"] = manifest["rate_sheets"][0]["name"]
        assert_error(validate_manifest(manifest), "SHEET_DUPLICATE_IN_MANIFEST", "$.rate_sheets[1]")

    def test_sheet_name_and_version_already_in_database(self, world):
        RateSheet.objects.create(
            name="Synthetic BUY Sheet", version=1, rate_type="BUY", transport_mode="AIR", currency_code="XXA",
            valid_from=datetime.date(2020, 1, 1), valid_until=datetime.date(2020, 12, 31),
            source_reference="OLD-SYNTHETIC", created_by=world["user"],
        )
        report = validate_manifest(valid_manifest())
        assert_error(report, "SHEET_ALREADY_EXISTS", "$.rate_sheets[0]")
        assert RateSheet.objects.get(name="Synthetic BUY Sheet").currency_code == "XXA"

    def test_new_version_of_existing_sheet_is_accepted(self, world):
        RateSheet.objects.create(
            name="Synthetic BUY Sheet", version=1, rate_type="BUY", transport_mode="AIR", currency_code="XTS",
            valid_from=datetime.date(2020, 1, 1), valid_until=datetime.date(2020, 12, 31),
            source_reference="OLD-SYNTHETIC", created_by=world["user"],
        )
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["version"] = 2
        assert validate_manifest(manifest).passed


# --------------------------------------------------------------------------- tiers


def _tiers(*bounds):
    return [{"min_quantity": lo, "max_quantity": hi, "unit_rate": "1.00"} for lo, hi in bounds]


TIER_CASES = [
    (_tiers(("45", "100"), ("100", None)), "TIER_COVERAGE_START", "$.rate_sheets[0].lines[0].tiers[0]"),
    (_tiers(("0", "100"), ("150", None)), "TIER_GAP", "$.rate_sheets[0].lines[0].tiers[1]"),
    (_tiers(("0", "100"), ("90", None)), "TIER_OVERLAP", "$.rate_sheets[0].lines[0].tiers[1]"),
    (_tiers(("0", "100"), ("100", "500")), "TIER_COVERAGE_END", "$.rate_sheets[0].lines[0].tiers[1]"),
    (_tiers(("0", None), ("100", None)), "TIER_OPEN_ENDED_NOT_LAST", "$.rate_sheets[0].lines[0].tiers[0]"),
    (_tiers(("0", "0"), ("0", None)), "TIER_BOUNDS", "$.rate_sheets[0].lines[0].tiers[0]"),
    (_tiers(("0", "100"), ("100", "50")), "TIER_BOUNDS", "$.rate_sheets[0].lines[0].tiers[1]"),
    (_tiers(("100", None), ("0", "100")), "TIER_COVERAGE_START", "$.rate_sheets[0].lines[0].tiers[0]"),
]


@pytest.mark.django_db
class TestTierRules:
    @pytest.mark.parametrize("tiers, code, path", TIER_CASES, ids=[f"{i}-{c[1]}" for i, c in enumerate(TIER_CASES)])
    def test_incomplete_or_ambiguous_coverage_rejected(self, world, tiers, code, path):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["tiers"] = tiers
        assert_error(validate_manifest(manifest), code, path)

    def test_single_open_ended_tier_from_zero_is_complete(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["tiers"] = _tiers(("0", None))
        assert validate_manifest(manifest).passed

    def test_boundary_is_lower_inclusive_upper_exclusive(self, world):
        # 100 belongs to the second tier only: the first ends at 100 exclusive, the second starts at 100 inclusive.
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["tiers"] = _tiers(("0", "100"), ("100", None))
        assert validate_manifest(manifest).passed

    def test_tier_rate_must_be_non_negative_decimal_string(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["tiers"][0]["unit_rate"] = "-1.00"
        assert_error(validate_manifest(manifest), "NEGATIVE_AMOUNT", "$.rate_sheets[0].lines[0].tiers[0].unit_rate")


# --------------------------------------------------------------------------- ambiguity and overlap


def _sell_line(**applicability):
    return _line(SCREEN, "PER_KG", unit_rate="0.22", applicability=_applicability(**applicability))


def _two_sell_sheets(first, second, **second_sheet):
    manifest = valid_manifest()
    manifest["rate_sheets"] = [
        _sheet("Synthetic SELL A", "SELL", [first]),
        _sheet("Synthetic SELL B", "SELL", [second], **second_sheet),
    ]
    return manifest


def _existing_sell_rate(world, **applicability):
    code = CommercialProductCode.objects.create(
        code=SCREEN, name=f"Synthetic {SCREEN}", category="ORIGIN", gst_treatment="STANDARD",
        charge_basis_default="PER_KG", legacy_product_code=world["legacy_screen"],
    )
    sheet = RateSheet.objects.create(
        name="Existing Synthetic SELL", version=1, rate_type="SELL", transport_mode="AIR", currency_code="XTS",
        valid_from=datetime.date(2030, 6, 1), valid_until=None, source_reference="EXISTING-SYNTHETIC",
        created_by=world["user"],
    )
    line = RateLine.objects.create(sheet=sheet, product_code=code, rate_basis="PER_KG", unit_rate=Decimal("0.3300"))
    values = {"direction": "EXPORT", "origin": world["xaa"], "destination": world["xbb"]}
    values.update(applicability)
    RateApplicability.objects.create(rate_line=line, **values)
    return sheet


@pytest.mark.django_db
class TestAmbiguityAndOverlap:
    def test_duplicate_identity_within_manifest(self, world):
        report = validate_manifest(_two_sell_sheets(_sell_line(), _sell_line()))
        assert_error(report, "RATE_DUPLICATE_IDENTITY", "$.rate_sheets[1].lines[0]")
        assert "$.rate_sheets[0].lines[0]" in report.errors[0].message

    def test_duplicate_identity_within_one_sheet(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"] = [_sheet("Synthetic SELL A", "SELL", [_sell_line(), _sell_line()])]
        assert_error(validate_manifest(manifest), "RATE_DUPLICATE_IDENTITY", "$.rate_sheets[0].lines[1]")

    def test_blank_and_specific_payment_term_may_not_coexist(self, world):
        report = validate_manifest(_two_sell_sheets(_sell_line(), _sell_line(payment_term="COLLECT")))
        assert_error(report, "RATE_PAYMENT_TERM_COEXISTENCE", "$.rate_sheets[1].lines[0]")

    def test_two_different_specific_payment_terms_coexist(self, world):
        report = validate_manifest(
            _two_sell_sheets(_sell_line(payment_term="PREPAID"), _sell_line(payment_term="COLLECT"))
        )
        assert report.passed

    def test_blank_location_overlapping_specific_location_is_ambiguous(self, world):
        report = validate_manifest(_two_sell_sheets(_sell_line(destination_iata=None), _sell_line()))
        assert_error(report, "RATE_AMBIGUOUS_MATCH", "$.rate_sheets[1].lines[0]")
        assert "No precedence is applied" in report.errors[0].message

    def test_non_overlapping_validity_is_not_a_conflict(self, world):
        manifest = _two_sell_sheets(
            _sell_line(), _sell_line(), valid_from="2031-01-01", valid_until="2031-12-31"
        )
        assert validate_manifest(manifest).passed

    def test_shared_boundary_day_counts_as_overlap(self, world):
        manifest = _two_sell_sheets(
            _sell_line(), _sell_line(), valid_from="2030-12-31", valid_until="2031-12-31"
        )
        assert_error(validate_manifest(manifest), "RATE_DUPLICATE_IDENTITY", "$.rate_sheets[1].lines[0]")

    def test_open_ended_sheet_overlaps_later_sheet(self, world):
        manifest = _two_sell_sheets(_sell_line(), _sell_line(), valid_from="2035-01-01", valid_until=None)
        manifest["rate_sheets"][0]["valid_until"] = None
        assert_error(validate_manifest(manifest), "RATE_DUPLICATE_IDENTITY", "$.rate_sheets[1].lines[0]")

    def test_different_currency_or_direction_is_a_different_rate(self, world):
        manifest = _two_sell_sheets(_sell_line(), _sell_line(), currency_code="XXA")
        assert validate_manifest(manifest).passed
        manifest = _two_sell_sheets(_sell_line(), _sell_line(direction="IMPORT"))
        assert validate_manifest(manifest).passed

    def test_inactive_sheet_does_not_conflict(self, world):
        manifest = _two_sell_sheets(_sell_line(), _sell_line(), is_active=False)
        assert validate_manifest(manifest).passed

    def test_buy_and_sell_for_same_charge_do_not_conflict(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"] = [
            _sheet("Synthetic SELL A", "SELL", [_sell_line()]),
            _sheet("Synthetic BUY A", "BUY", [_sell_line()], supplier=dict(CARRIER_REF)),
        ]
        assert validate_manifest(manifest).passed

    def test_duplicate_identity_against_existing_rows(self, world):
        existing = _existing_sell_rate(world)
        manifest = valid_manifest()
        manifest["product_codes"] = []
        manifest["rate_sheets"] = [_sheet("Synthetic SELL A", "SELL", [_sell_line()])]
        before = snapshot()
        report = validate_manifest(manifest)
        assert_error(report, "RATE_DUPLICATE_IDENTITY", "$.rate_sheets[0].lines[0]")
        assert f'existing RateSheet "{existing.name}" v1' in report.errors[0].message
        assert snapshot() == before

    def test_payment_term_coexistence_against_existing_rows(self, world):
        _existing_sell_rate(world, payment_term="PREPAID")
        manifest = valid_manifest()
        manifest["product_codes"] = []
        manifest["rate_sheets"] = [_sheet("Synthetic SELL A", "SELL", [_sell_line()])]
        assert_error(validate_manifest(manifest), "RATE_PAYMENT_TERM_COEXISTENCE", "$.rate_sheets[0].lines[0]")

    def test_existing_rows_outside_validity_do_not_conflict(self, world):
        _existing_sell_rate(world)
        manifest = valid_manifest()
        manifest["product_codes"] = []
        manifest["rate_sheets"] = [
            _sheet("Synthetic SELL A", "SELL", [_sell_line()], valid_from="2030-01-01", valid_until="2030-05-31")
        ]
        assert validate_manifest(manifest).passed

    def test_existing_inactive_sheet_does_not_conflict(self, world):
        existing = _existing_sell_rate(world)
        RateSheet.objects.filter(pk=existing.pk).update(is_active=False)
        manifest = valid_manifest()
        manifest["product_codes"] = []
        manifest["rate_sheets"] = [_sheet("Synthetic SELL A", "SELL", [_sell_line()])]
        assert validate_manifest(manifest).passed


# --------------------------------------------------------------------------- command


@pytest.mark.django_db
class TestCommand:
    @staticmethod
    def _write(tmp_path, manifest):
        path = tmp_path / "manifest.json"
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return str(path)

    def test_pass_prints_report_and_writes_nothing(self, world, tmp_path):
        before = snapshot()
        out = StringIO()
        call_command("validate_rate_matrix_manifest", self._write(tmp_path, valid_manifest()), stdout=out)
        assert "Result: PASS" in out.getvalue()
        assert "Writes performed: 0" in out.getvalue()
        assert snapshot() == before

    def test_fail_prints_report_then_exits_non_zero(self, world, tmp_path):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["currency_code"] = "QQQ"
        before = snapshot()
        out = StringIO()
        with pytest.raises(CommandError, match="FAILED with 1 error"):
            call_command("validate_rate_matrix_manifest", self._write(tmp_path, manifest), stdout=out)
        assert "[CURRENCY_UNKNOWN] $.rate_sheets[0].currency_code" in out.getvalue()
        assert "Result: FAIL" in out.getvalue()
        assert snapshot() == before

    def test_json_format(self, world, tmp_path):
        out = StringIO()
        call_command(
            "validate_rate_matrix_manifest", self._write(tmp_path, valid_manifest()), format="json", stdout=out
        )
        assert json.loads(out.getvalue())["result"] == "PASS"

    def test_missing_file(self, world, tmp_path):
        with pytest.raises(CommandError, match="not found"):
            call_command("validate_rate_matrix_manifest", str(tmp_path / "absent.json"))

    def test_command_has_no_apply_mode(self, world, tmp_path):
        with pytest.raises((CommandError, SystemExit, TypeError)):
            call_command("validate_rate_matrix_manifest", self._write(tmp_path, valid_manifest()), "--apply")
