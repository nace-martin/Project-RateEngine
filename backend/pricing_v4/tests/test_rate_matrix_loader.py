"""Pilot Gate B3H: controlled Rate Matrix tariff loader.

Every value here is synthetic test data. No real tariff, party, or rate appears.
"""

import copy
import json
from decimal import Decimal as D
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from parties.party_models import PartyMaster, PartyRole
from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.models import ProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)
from pricing_v4.services.rate_matrix_loader import (
    TariffApplyError,
    apply_tariffs,
    plan_tariffs,
    reviewed_digest,
)

FREIGHT = "EXP-SYNTH-FRT"
SCREEN = "EXP-SYNTH-SCREEN"
FSC = "EXP-SYNTH-FSC"
RATE_TABLES = (RateSheet, RateLine, RateApplicability, RateTier)
CARRIER_REF = {"legal_name": "Synthetic Carrier Ltd", "country_code": "ZZ", "role": "CARRIER"}
AGENT_REF = {"legal_name": "Synthetic Agent Pty", "country_code": "ZZ", "role": "AGENT"}
TIERS = [
    {"min_quantity": "0", "max_quantity": "100", "unit_rate": "1.11"},
    {"min_quantity": "100", "max_quantity": "500", "unit_rate": "1.05"},
    {"min_quantity": "500", "max_quantity": None, "unit_rate": "0.99"},
]


def _legacy(pk, code, gst="STANDARD"):
    return ProductCode.objects.create(
        id=pk, code=code, description=f"Synthetic {code}", domain=ProductCode.DOMAIN_EXPORT,
        category=ProductCode.CATEGORY_HANDLING, is_gst_applicable=True, gst_rate="0.10",
        gst_treatment=gst, gl_revenue_code="4000", gl_cost_code="5000",
        default_unit=ProductCode.UNIT_SHIPMENT,
    )


def _mirror(legacy, category, basis):
    return CommercialProductCode.objects.create(
        code=legacy.code, name=f"Synthetic {legacy.code}", category=category, sub_category="",
        gst_treatment=legacy.gst_treatment, charge_basis_default=basis, is_active=True,
        legacy_product_code=legacy,
    )


def _airport(name, iata):
    # Built and saved directly: the legacy-Location guardrail test matches this text pattern.
    location = GeoLocation(canonical_name=name, country_code="ZZ", location_type="AIRPORT")
    location.save()
    GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=iata)
    return location


def _party(name, role):
    party = PartyMaster.objects.create(legal_name=name, entity_type="COMPANY", country_code="ZZ")
    PartyRole.objects.create(party=party, role_type=role)
    return party


@pytest.fixture
def world(db):
    """Synthetic master data, as the B3F master-data loader leaves it, for tariffs to resolve against."""
    for code in ("XTS", "XXA"):
        Currency.objects.get_or_create(code=code, defaults={"name": f"Synthetic {code}"})
    freight = _legacy(1901, FREIGHT, gst="ZERO_RATED")
    screen = _legacy(1902, SCREEN)
    fsc = _legacy(1903, FSC)
    _mirror(freight, "FREIGHT", "TIERED_WEIGHT")
    _mirror(screen, "ORIGIN", "PER_KG")
    _mirror(fsc, "ORIGIN", "PERCENTAGE")
    _airport("Synthetic Airport A", "XAA")
    _airport("Synthetic Airport B", "XBB")
    _party("Synthetic Carrier Ltd", "CARRIER")
    _party("Synthetic Agent Pty", "AGENT")
    return {"operator": get_user_model().objects.create_user(username="synthetic-operator", password="x")}


def _code(code, legacy_id, gst="STANDARD", category="ORIGIN", basis="FLAT"):
    return {
        "code": code, "name": f"Synthetic {code}", "category": category, "sub_category": "",
        "gst_treatment": gst, "charge_basis_default": basis, "is_active": True,
        "legacy_product_code": {"id": legacy_id, "code": code},
    }


PRODUCT_CODES = [
    _code(FREIGHT, 1901, gst="ZERO_RATED", category="FREIGHT", basis="TIERED_WEIGHT"),
    _code(SCREEN, 1902, basis="PER_KG"),
    _code(FSC, 1903, basis="PERCENTAGE"),
]


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


def manifest_of(*sheets):
    return {"manifest_version": 1, "product_codes": copy.deepcopy(PRODUCT_CODES), "rate_sheets": list(sheets)}


def buy_sheet(name="Synthetic BUY Sheet", **overrides):
    overrides.setdefault("supplier", dict(CARRIER_REF))
    return _sheet(
        name, "BUY", [_line(FREIGHT, "TIERED_WEIGHT", min_charge="11.00", tiers=copy.deepcopy(TIERS))], **overrides
    )


def sell_sheet(name="Synthetic SELL Sheet", **overrides):
    return _sheet(
        name, "SELL",
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
        **overrides,
    )


def valid_manifest():
    return manifest_of(buy_sheet(), sell_sheet())


def text_of(manifest):
    return json.dumps(manifest, indent=1)


def entries_of(*manifests):
    return [(f"m{i}.json", text_of(m)) for i, m in enumerate(manifests, start=1)]


def plan_of(*manifests):
    return plan_tariffs(entries_of(*manifests))


def apply_of(*manifests, world, **kwargs):
    entries = entries_of(*manifests)
    sha = kwargs.pop("reviewed_sha256", reviewed_digest([text for _label, text in entries]))
    return apply_tariffs(entries, operator=world["operator"], reviewed_sha256=sha, **kwargs)


def snapshot():
    return {
        "rate_rows": {m._meta.db_table: sorted(map(str, m.objects.values_list("pk", flat=True))) for m in RATE_TABLES},
        "legacy": list(ProductCode.objects.order_by("id").values()),
        "mirrors": list(CommercialProductCode.objects.order_by("code").values()),
        "parties": list(PartyMaster.objects.order_by("legal_name").values()),
        "geo": list(GeoLocation.objects.order_by("canonical_name").values_list("canonical_name", flat=True)),
    }


def non_rate(snap):
    return {key: value for key, value in snap.items() if key != "rate_rows"}


def error_codes(plan):
    return {(i["code"], i["path"]) for i in plan.issues}


def codes_only(plan):
    return {i["code"] for i in plan.issues}


# --------------------------------------------------------------------------- dry run


@pytest.mark.django_db
class TestDryRun:
    def test_plans_creates_and_is_ready(self, world):
        plan = plan_of(valid_manifest())
        assert plan.ready
        assert plan.mode == "DRY_RUN"
        assert plan.counts() == {
            "sheets_create": 2, "sheets_reuse": 0, "sheets_conflict": 0, "rate_lines_create": 3,
            "rate_applicabilities_create": 3, "rate_tiers_create": 3, "errors": 0, "warnings": 0,
        }
        assert [(s.name, s.action) for s in plan.sheets] == [
            ("Synthetic BUY Sheet", "CREATE"), ("Synthetic SELL Sheet", "CREATE"),
        ]
        assert plan.as_dict()["writes_performed"] == 0

    def test_performs_zero_writes(self, world):
        before = snapshot()
        plan_of(valid_manifest())
        assert snapshot() == before

    def test_not_ready_plan_performs_zero_writes(self, world):
        before = snapshot()
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = None
        assert not plan_of(manifest).ready
        assert snapshot() == before

    def test_issues_no_write_statements(self, world):
        with CaptureQueriesContext(connection) as queries:
            plan_of(valid_manifest())
        verbs = {q["sql"].lstrip().split(None, 1)[0].upper() for q in queries}
        assert not verbs & {"INSERT", "UPDATE", "DELETE"}, verbs

    def test_repeated_dry_runs_are_identical(self, world):
        assert plan_of(valid_manifest()).render_json() == plan_of(valid_manifest()).render_json()

    def test_text_report(self, world):
        text = plan_of(valid_manifest()).render_text()
        assert "Mode: DRY RUN" in text
        assert "Reviewed sha256: " in text
        assert "[CREATE] \"Synthetic BUY Sheet\" v1 BUY AIR XTS" in text
        assert "Result: READY" in text
        assert "Writes performed: 0" in text

    def test_connection_writable_after_dry_run(self, world):
        plan_of(valid_manifest())
        PartyMaster.objects.create(legal_name="Synthetic After", entity_type="COMPANY", country_code="ZZ")
        assert PartyMaster.objects.filter(legal_name="Synthetic After").exists()

    def test_no_manifest_is_not_ready(self, world):
        plan = plan_tariffs([])
        assert not plan.ready
        assert codes_only(plan) == {"NO_MANIFEST"}


# --------------------------------------------------------------------------- strict manifest


@pytest.mark.django_db
class TestStrictManifest:
    def test_invalid_json(self, world):
        plan = plan_tariffs([("bad.json", "{not json")])
        assert not plan.ready
        assert codes_only(plan) == {"MANIFEST_NOT_STRICT_JSON"}
        assert plan.sheets == []

    def test_duplicate_keys_and_non_finite_numbers_rejected(self, world):
        for text in ('{"manifest_version": 1, "manifest_version": 1}', '{"manifest_version": NaN}'):
            assert codes_only(plan_tariffs([("bad.json", text)])) == {"MANIFEST_NOT_STRICT_JSON"}

    def test_unknown_missing_and_numeric_amounts_are_errors(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["surprise"] = 1
        del manifest["rate_sheets"][1]["source_reference"]
        manifest["rate_sheets"].append(
            _sheet("Synthetic Numeric", "SELL", [_line(SCREEN, "FLAT", unit_rate=12.5)])
        )
        plan = plan_of(manifest)
        assert not plan.ready
        assert {"MANIFEST_UNKNOWN_FIELD", "MANIFEST_MISSING_FIELD", "DECIMAL_NOT_STRING"} <= codes_only(plan)
        assert plan.sheets == []

    def test_no_defaults_are_invented(self, world):
        manifest = valid_manifest()
        del manifest["rate_sheets"][0]["lines"][0]["applicability"]["payment_term"]
        plan = plan_of(manifest)
        assert ("MANIFEST_MISSING_FIELD", "$.rate_sheets[0].lines[0].applicability.payment_term") in error_codes(plan)

    def test_unsupported_version(self, world):
        manifest = valid_manifest()
        manifest["manifest_version"] = 2
        assert codes_only(plan_of(manifest)) == {"MANIFEST_VERSION"}


# --------------------------------------------------------------------------- scope


@pytest.mark.django_db
class TestScope:
    def test_loader_never_creates_a_commercial_product_code(self, world):
        CommercialProductCode.objects.filter(code=SCREEN).delete()
        plan = plan_of(valid_manifest())
        assert not plan.ready
        assert "PRODUCT_CODE_CREATE_NOT_SUPPORTED" in codes_only(plan)
        assert plan.sheets == []

    def test_unresolved_product_code_is_refused(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["product_code"] = "EXP-SYNTH-ABSENT"
        assert "PRODUCT_CODE_UNRESOLVED" in codes_only(plan_of(manifest))

    def test_unknown_location_party_and_currency_are_refused(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["lines"][0]["applicability"]["origin_iata"] = "QQQ"
        manifest["rate_sheets"][0]["supplier"] = {**CARRIER_REF, "legal_name": "Nobody Ltd"}
        manifest["rate_sheets"][1]["currency_code"] = "ZZZ"
        assert {"GEOGRAPHY_NOT_FOUND", "PARTY_NOT_FOUND", "CURRENCY_UNKNOWN"} <= codes_only(plan_of(manifest))

    def test_pilot_rules_still_hold(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = None
        manifest["rate_sheets"][1]["customer"] = {**CARRIER_REF, "role": "CUSTOMER"}
        manifest["rate_sheets"][1]["lines"][0]["applicability"]["payment_term"] = "COLLECT"
        assert {"BUY_SHEET_WITHOUT_SUPPLIER", "SELL_SHEET_HAS_CUSTOMER"} <= codes_only(plan_of(manifest))
        buy = valid_manifest()
        buy["rate_sheets"][0]["lines"][0]["applicability"]["payment_term"] = "PREPAID"
        assert "BUY_PAYMENT_TERM_NOT_BLANK" in codes_only(plan_of(buy))


# --------------------------------------------------------------------------- apply


@pytest.mark.django_db
class TestApply:
    def test_creates_every_planned_row_and_nothing_else(self, world):
        before = snapshot()
        plan = apply_of(valid_manifest(), world=world)
        assert plan.ready
        assert plan.mode == "APPLY"
        assert plan.applied == {
            "operator": "synthetic-operator", "rows_created": 11, "sheets": 2, "lines": 3,
            "applicabilities": 3, "tiers": 3,
        }
        assert [m.objects.count() for m in RATE_TABLES] == [2, 3, 3, 3]
        assert non_rate(snapshot()) == non_rate(before)
        assert "Applied by synthetic-operator: 11 row(s) created" in plan.render_text()

    def test_persisted_values_match_the_manifest(self, world):
        apply_of(valid_manifest(), world=world)
        buy = RateSheet.objects.get(name="Synthetic BUY Sheet")
        assert (buy.rate_type, buy.transport_mode, buy.currency_code, buy.version) == ("BUY", "AIR", "XTS", 1)
        assert (str(buy.valid_from), str(buy.valid_until), buy.is_active) == ("2030-01-01", "2030-12-31", True)
        assert buy.source_reference == "SYNTHETIC-TEST-TARIFF"
        assert buy.carrier.legal_name == "Synthetic Carrier Ltd"
        assert buy.party_id is None
        assert buy.created_by.username == "synthetic-operator"
        line = buy.lines.get()
        assert (line.product_code.code, line.rate_basis, line.unit_rate, line.min_charge) == (
            FREIGHT, "TIERED_WEIGHT", None, D(11)
        )
        assert line.applicability.origin.identifiers.get().code == "XAA"
        assert line.applicability.destination.identifiers.get().code == "XBB"
        assert (line.applicability.direction, line.applicability.payment_term) == ("EXPORT", "")
        assert [(t.min_quantity, t.max_quantity, t.unit_rate) for t in line.tiers.order_by("min_quantity")] == [
            (D(0), D(100), D("1.11")), (D(100), D(500), D("1.05")), (D(500), None, D("0.99")),
        ]

        sell = RateSheet.objects.get(name="Synthetic SELL Sheet")
        assert sell.carrier_id is None and sell.party_id is None
        screen = sell.lines.get(product_code__code=SCREEN)
        assert (screen.unit_rate, screen.additive_flat_amount) == (D("0.22"), D("4.5"))
        assert screen.applicability.payment_term == "PREPAID"
        assert screen.applicability.destination_id is None
        fsc = sell.lines.get(product_code__code=FSC)
        assert (fsc.percentage_rate, fsc.percentage_basis_product_code.code) == (D(10), SCREEN)

    def test_second_apply_creates_zero_rows(self, world):
        apply_of(valid_manifest(), world=world)
        before = snapshot()
        plan = apply_of(valid_manifest(), world=world)
        assert plan.ready
        assert plan.counts()["sheets_create"] == 0
        assert plan.counts()["sheets_reuse"] == 2
        assert plan.applied["rows_created"] == 0
        assert snapshot() == before

    def test_dry_run_after_apply_reports_reuse(self, world):
        apply_of(valid_manifest(), world=world)
        plan = plan_of(valid_manifest())
        assert plan.ready
        assert [s.action for s in plan.sheets] == ["REUSE", "REUSE"]
        assert plan.counts()["rate_lines_create"] == 0

    def test_reuse_is_independent_of_line_order(self, world):
        apply_of(valid_manifest(), world=world)
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"].reverse()
        assert [s.action for s in plan_of(manifest).sheets] == ["REUSE", "REUSE"]

    def test_amount_scale_does_not_create_a_false_conflict(self, world):
        apply_of(valid_manifest(), world=world)
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["unit_rate"] = "0.2200"
        manifest["rate_sheets"][0]["lines"][0]["min_charge"] = "11"
        assert [s.action for s in plan_of(manifest).sheets] == ["REUSE", "REUSE"]

    def test_refuses_when_manifest_differs_from_reviewed_dry_run(self, world):
        before = snapshot()
        with pytest.raises(TariffApplyError, match="do not match the reviewed dry run"):
            apply_of(valid_manifest(), world=world, reviewed_sha256="0" * 64)
        assert snapshot() == before

    def test_reviewed_hash_of_edited_manifest_is_refused(self, world):
        reviewed = reviewed_digest([text_of(valid_manifest())])
        edited = valid_manifest()
        edited["rate_sheets"][1]["lines"][0]["unit_rate"] = "9.99"
        before = snapshot()
        with pytest.raises(TariffApplyError, match="do not match"):
            apply_of(edited, world=world, reviewed_sha256=reviewed)
        assert snapshot() == before

    def test_refuses_inactive_operator(self, world):
        world["operator"].is_active = False
        before = snapshot()
        with pytest.raises(TariffApplyError, match="active operator"):
            apply_of(valid_manifest(), world=world)
        assert snapshot() == before

    def test_refuses_missing_operator(self, world):
        with pytest.raises(TariffApplyError, match="active operator"):
            apply_tariffs(entries_of(valid_manifest()), operator=None, reviewed_sha256="0" * 64)

    def test_any_not_ready_sheet_refuses_the_whole_apply(self, world):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["unit_rate"] = None  # BASIS_FIELDS
        before = snapshot()
        plan = apply_of(manifest, world=world)
        assert not plan.ready
        assert plan.applied is None
        assert "Apply refused. Nothing was written." in plan.render_text()
        assert snapshot() == before

    def test_failure_part_way_rolls_everything_back(self, world, monkeypatch):
        def explode(self, *args, **kwargs):
            raise ValidationError("synthetic failure while saving a tier")

        monkeypatch.setattr(RateTier, "save", explode)
        before = snapshot()
        with pytest.raises(ValidationError):
            apply_of(valid_manifest(), world=world)
        assert snapshot() == before
        assert RateSheet.objects.count() == 0

    def test_failed_post_apply_verification_rolls_back(self, world, monkeypatch):
        import pricing_v4.services.rate_matrix_loader as module

        real_execute = module._execute

        def execute_then_drop_a_line(plan, operator, using):
            real_execute(plan, operator, using)
            RateLine.objects.filter(product_code__code=FSC).delete()

        monkeypatch.setattr(module, "_execute", execute_then_drop_a_line)
        before = snapshot()
        with pytest.raises(TariffApplyError, match="Post-apply verification failed"):
            apply_of(valid_manifest(), world=world)
        assert snapshot() == before

    def test_stored_truth_check_rolls_back_a_silently_altered_row(self, world, monkeypatch):
        import pricing_v4.services.rate_matrix_loader as module

        real_execute = module._execute

        def execute_then_change_a_rate(plan, operator, using):
            real_execute(plan, operator, using)
            RateLine.objects.filter(product_code__code=SCREEN).update(unit_rate="9.99")

        monkeypatch.setattr(module, "_execute", execute_then_change_a_rate)
        before = snapshot()
        with pytest.raises(TariffApplyError, match="Post-apply verification failed"):
            apply_of(valid_manifest(), world=world)
        assert snapshot() == before


# --------------------------------------------------------------------------- stored sheets


def _move_tier_boundary(manifest):
    tiers = manifest["rate_sheets"][0]["lines"][0]["tiers"]
    tiers[1]["max_quantity"] = "400"
    tiers[2]["min_quantity"] = "400"


@pytest.mark.django_db
class TestStoredSheets:
    @pytest.fixture(autouse=True)
    def _stored(self, world):
        apply_of(valid_manifest(), world=world)
        self.world = world

    def _conflicts(self, manifest):
        before = snapshot()
        plan = plan_of(manifest)
        assert snapshot() == before
        assert not plan.ready
        assert any(s.action == "CONFLICT" for s in plan.sheets)
        return plan

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("currency_code", "XXA"), ("valid_until", "2030-06-30"), ("valid_from", "2030-01-02"),
            ("is_active", False), ("source_reference", "SYNTHETIC-OTHER-TARIFF"),
        ],
    )
    def test_differing_sheet_field_conflicts(self, field, value):
        manifest = valid_manifest()
        manifest["rate_sheets"][1][field] = value
        plan = self._conflicts(manifest)
        sell = next(s for s in plan.sheets if s.name == "Synthetic SELL Sheet")
        assert sell.action == "CONFLICT"
        assert field in sell.reasons[0]
        assert "never updated" in sell.reasons[0]
        assert next(s for s in plan.sheets if s.name == "Synthetic BUY Sheet").action == "REUSE"

    def test_differing_supplier_conflicts(self):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = dict(AGENT_REF)
        plan = self._conflicts(manifest)
        assert "carrier_id" in plan.sheets[0].reasons[0]

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda m: m["rate_sheets"][1]["lines"][0].update(unit_rate="0.23"),
            lambda m: m["rate_sheets"][1]["lines"][0].update(additive_flat_amount="4.51"),
            lambda m: m["rate_sheets"][1]["lines"][1].update(percentage_rate="11.00"),
            lambda m: m["rate_sheets"][0]["lines"][0].update(min_charge="12.00"),
            lambda m: m["rate_sheets"][0]["lines"][0]["tiers"][1].update(unit_rate="1.06"),
            _move_tier_boundary,
            lambda m: m["rate_sheets"][1]["lines"][0]["applicability"].update(payment_term="COLLECT"),
            lambda m: m["rate_sheets"][1]["lines"][0]["applicability"].update(origin_iata="XBB"),
            lambda m: m["rate_sheets"][1]["lines"][0]["applicability"].update(service_level="EXPRESS"),
            lambda m: m["rate_sheets"][1]["lines"].pop(),
            lambda m: m["rate_sheets"][1]["lines"].append(
                _line(SCREEN, "FLAT", unit_rate="1.00", applicability=_applicability(origin_iata="XBB", destination_iata=None))
            ),
        ],
    )
    def test_differing_line_applicability_or_tier_conflicts(self, mutate):
        manifest = valid_manifest()
        mutate(manifest)
        plan = self._conflicts(manifest)
        assert any(r for s in plan.sheets for r in s.reasons)

    def test_apply_of_a_conflict_writes_nothing_and_never_updates(self):
        manifest = valid_manifest()
        manifest["rate_sheets"][1]["lines"][0]["unit_rate"] = "0.23"
        before = snapshot()
        plan = apply_of(manifest, world=self.world)
        assert not plan.ready
        assert plan.applied is None
        assert snapshot() == before
        assert RateLine.objects.get(product_code__code=SCREEN).unit_rate == D("0.22")

    def test_a_correction_is_a_new_version_with_its_own_window(self):
        manifest = valid_manifest()
        corrected = sell_sheet(valid_from="2031-01-01", valid_until="2031-12-31", version=2)
        corrected["lines"][0]["unit_rate"] = "0.23"
        manifest["rate_sheets"] = [manifest["rate_sheets"][0], manifest["rate_sheets"][1], corrected]
        plan = plan_of(manifest)
        assert plan.ready
        assert [s.action for s in plan.sheets] == ["REUSE", "REUSE", "CREATE"]
        apply_of(manifest, world=self.world)
        assert RateSheet.objects.filter(name="Synthetic SELL Sheet").count() == 2

    def test_a_new_version_overlapping_the_stored_one_is_ambiguous(self):
        manifest = valid_manifest()
        rival = sell_sheet(version=2)
        rival["lines"][0]["unit_rate"] = "0.23"
        manifest["rate_sheets"] = [rival]
        plan = plan_of(manifest)
        assert not plan.ready
        assert "RATE_DUPLICATE_IDENTITY" in codes_only(plan)

    def test_stored_sheet_is_not_a_rival_of_itself(self):
        plan = plan_of(valid_manifest())
        assert plan.ready
        assert not plan.issues


# --------------------------------------------------------------------------- several manifests


def _one(sheet):
    return manifest_of(sheet)


@pytest.mark.django_db
class TestAcrossManifests:
    def test_non_conflicting_manifests_coexist(self, world):
        sell_xts = _one(sell_sheet("Synthetic SELL XTS"))
        sell_xxa = _one(sell_sheet("Synthetic SELL XXA", currency_code="XXA"))
        plan = plan_of(_one(buy_sheet()), sell_xts, sell_xxa)
        assert plan.ready
        assert [s.manifest for s in plan.sheets] == ["m1.json", "m2.json", "m3.json"]
        assert plan.counts()["sheets_create"] == 3

    def test_identical_active_tariffs_in_two_manifests_conflict(self, world):
        plan = plan_of(_one(sell_sheet("Synthetic SELL A")), _one(sell_sheet("Synthetic SELL B")))
        assert not plan.ready
        assert "RATE_DUPLICATE_IDENTITY" in codes_only(plan)
        assert plan.sheets == []

    def test_blank_payment_term_overlapping_a_specific_one_conflicts(self, world):
        specific = sell_sheet("Synthetic SELL PREPAID")
        any_term = sell_sheet("Synthetic SELL ANY")
        any_term["lines"][0]["applicability"]["payment_term"] = ""
        plan = plan_of(_one(specific), _one(any_term))
        assert "RATE_PAYMENT_TERM_COEXISTENCE" in codes_only(plan)

    def test_buy_costs_that_differ_only_in_currency_conflict(self, world):
        plan = plan_of(_one(buy_sheet("Synthetic BUY A")), _one(buy_sheet("Synthetic BUY B", currency_code="XXA")))
        assert "RATE_BUY_CURRENCY_AMBIGUOUS" in codes_only(plan)

    def test_blank_dimension_overlapping_a_specific_one_is_ambiguous(self, world):
        general = sell_sheet("Synthetic SELL GENERAL")
        specific = sell_sheet("Synthetic SELL SPECIFIC")
        specific["lines"][0]["applicability"]["service_level"] = "EXPRESS"
        assert "RATE_AMBIGUOUS_MATCH" in codes_only(plan_of(_one(general), _one(specific)))

    def test_disjoint_validity_windows_coexist(self, world):
        later = sell_sheet("Synthetic SELL 2031", valid_from="2031-01-01", valid_until="2031-12-31")
        assert plan_of(_one(sell_sheet()), _one(later)).ready

    def test_inactive_sheet_is_not_a_rival(self, world):
        inactive = sell_sheet("Synthetic SELL OFF", is_active=False)
        assert plan_of(_one(sell_sheet()), _one(inactive)).ready

    def test_same_sheet_identity_in_two_manifests_is_refused(self, world):
        plan = plan_of(_one(sell_sheet()), _one(sell_sheet()))
        assert "SHEET_DUPLICATE_ACROSS_MANIFESTS" in codes_only(plan)
        assert not plan.ready

    def test_conflict_is_reported_against_the_later_manifest(self, world):
        plan = plan_of(_one(sell_sheet("Synthetic SELL A")), _one(sell_sheet("Synthetic SELL B")))
        issue = next(i for i in plan.issues if i["code"] == "RATE_DUPLICATE_IDENTITY")
        assert issue["manifest"] == "m2.json"
        assert "m1.json" in issue["message"]

    def test_a_stored_sheet_still_conflicts_with_a_rival_in_a_later_manifest(self, world):
        apply_of(_one(sell_sheet("Synthetic SELL A")), world=world)
        plan = plan_of(_one(sell_sheet("Synthetic SELL B")))
        assert "RATE_DUPLICATE_IDENTITY" in codes_only(plan)

    def test_apply_is_all_or_nothing_across_manifests(self, world):
        good = _one(buy_sheet())
        rival_a, rival_b = _one(sell_sheet("Synthetic SELL A")), _one(sell_sheet("Synthetic SELL B"))
        before = snapshot()
        plan = apply_of(good, rival_a, rival_b, world=world)
        assert not plan.ready
        assert plan.applied is None
        assert snapshot() == before

    def test_apply_of_several_manifests_creates_all_and_is_idempotent(self, world):
        manifests = (_one(buy_sheet()), _one(sell_sheet()), _one(sell_sheet("Synthetic SELL XXA", currency_code="XXA")))
        plan = apply_of(*manifests, world=world)
        assert plan.applied["sheets"] == 3
        assert RateSheet.objects.count() == 3
        again = apply_of(*manifests, world=world)
        assert again.applied["rows_created"] == 0
        assert RateSheet.objects.count() == 3

    def test_reviewed_digest_binds_the_set_not_the_order(self, world):
        a, b = text_of(_one(buy_sheet())), text_of(_one(sell_sheet()))
        assert reviewed_digest([a, b]) == reviewed_digest([b, a])
        assert reviewed_digest([a, b]) != reviewed_digest([a])
        assert reviewed_digest([a, b]) != reviewed_digest([a, text_of(_one(sell_sheet("Other")))])
        assert reviewed_digest([a]) == plan_tariffs([("a.json", a)]).reviewed_sha256

    def test_digest_of_a_subset_is_refused(self, world):
        a, b = _one(buy_sheet()), _one(sell_sheet())
        before = snapshot()
        with pytest.raises(TariffApplyError, match="do not match"):
            apply_of(a, b, world=world, reviewed_sha256=reviewed_digest([text_of(a)]))
        assert snapshot() == before

    def test_one_invalid_manifest_blocks_the_others(self, world):
        bad = _one(sell_sheet("Synthetic SELL BAD"))
        bad["rate_sheets"][0]["lines"][0]["unit_rate"] = "-1"
        plan = plan_of(_one(buy_sheet()), bad)
        assert not plan.ready
        assert "NEGATIVE_AMOUNT" in codes_only(plan)


# --------------------------------------------------------------------------- command


@pytest.mark.django_db
class TestCommand:
    @staticmethod
    def _write(tmp_path, *manifests):
        paths = []
        for index, manifest in enumerate(manifests, start=1):
            path = tmp_path / f"tariff-{index}.json"
            path.write_text(text_of(manifest), encoding="utf-8")
            paths.append(str(path))
        return paths

    def test_dry_run_is_the_default(self, world, tmp_path):
        before = snapshot()
        out = StringIO()
        call_command("load_rate_matrix_manifest", *self._write(tmp_path, valid_manifest()), stdout=out)
        assert "Mode: DRY RUN" in out.getvalue()
        assert "Writes performed: 0" in out.getvalue()
        assert snapshot() == before

    def test_not_ready_exits_non_zero_after_printing(self, world, tmp_path):
        manifest = valid_manifest()
        manifest["rate_sheets"][0]["supplier"] = None
        out = StringIO()
        with pytest.raises(CommandError, match="NOT READY"):
            call_command("load_rate_matrix_manifest", *self._write(tmp_path, manifest), stdout=out)
        assert "BUY_SHEET_WITHOUT_SUPPLIER" in out.getvalue()

    def test_several_files_are_checked_together(self, world, tmp_path):
        paths = self._write(tmp_path, _one(sell_sheet("Synthetic SELL A")), _one(sell_sheet("Synthetic SELL B")))
        out = StringIO()
        with pytest.raises(CommandError, match="NOT READY"):
            call_command("load_rate_matrix_manifest", *paths, stdout=out)
        assert "RATE_DUPLICATE_IDENTITY" in out.getvalue()
        assert "tariff-2.json" in out.getvalue()

    def test_apply_requires_operator_and_reviewed_hash(self, world, tmp_path):
        paths = self._write(tmp_path, valid_manifest())
        before = snapshot()
        with pytest.raises(CommandError, match="requires --operator and --reviewed-sha256"):
            call_command("load_rate_matrix_manifest", *paths, apply=True)
        with pytest.raises(CommandError, match="requires --operator and --reviewed-sha256"):
            call_command("load_rate_matrix_manifest", *paths, apply=True, operator="synthetic-operator")
        with pytest.raises(CommandError, match="No active user"):
            call_command("load_rate_matrix_manifest", *paths, apply=True, operator="nobody", reviewed_sha256="0" * 64)
        with pytest.raises(CommandError, match="do not match the reviewed dry run"):
            call_command(
                "load_rate_matrix_manifest", *paths, apply=True, operator="synthetic-operator",
                reviewed_sha256="0" * 64,
            )
        assert snapshot() == before

    def test_inactive_operator_is_refused(self, world, tmp_path):
        world["operator"].is_active = False
        world["operator"].save()
        with pytest.raises(CommandError, match="No active user"):
            call_command(
                "load_rate_matrix_manifest", *self._write(tmp_path, valid_manifest()), apply=True,
                operator="synthetic-operator", reviewed_sha256="0" * 64,
            )

    def test_operator_flags_rejected_without_apply(self, world, tmp_path):
        with pytest.raises(CommandError, match="only valid with --apply"):
            call_command(
                "load_rate_matrix_manifest", *self._write(tmp_path, valid_manifest()), operator="synthetic-operator"
            )

    def test_apply_with_reviewed_hash(self, world, tmp_path):
        paths = self._write(tmp_path, _one(buy_sheet()), _one(sell_sheet()))
        dry = StringIO()
        call_command("load_rate_matrix_manifest", *paths, format="json", stdout=dry)
        report = json.loads(dry.getvalue())
        assert report["result"] == "READY"
        assert report["writes_performed"] == 0
        out = StringIO()
        call_command(
            "load_rate_matrix_manifest", *paths, apply=True, operator="synthetic-operator",
            reviewed_sha256=report["reviewed_sha256"], format="json", stdout=out,
        )
        applied = json.loads(out.getvalue())
        assert applied["applied"]["operator"] == "synthetic-operator"
        assert applied["writes_performed"] == applied["applied"]["rows_created"] == 11
        assert RateSheet.objects.count() == 2

    def test_missing_file(self, world, tmp_path):
        with pytest.raises(CommandError, match="not found"):
            call_command("load_rate_matrix_manifest", str(tmp_path / "absent.json"))

    def test_non_utf8_file(self, world, tmp_path):
        path = tmp_path / "bad.json"
        path.write_bytes(b"\xff\xfe\x00bad")
        with pytest.raises(CommandError, match="not valid UTF-8"):
            call_command("load_rate_matrix_manifest", str(path))
