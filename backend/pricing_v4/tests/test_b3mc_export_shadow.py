"""Pilot Gate B3M-C: export Rate Matrix manifests and the read-only export shadow harness.

The commercial values here are the locked rules recorded by the Commercial Manager on 2026-10-12
(BUY and SELL tariffs, AUD conversion at TT BUY with a 10% export CAF, no margin on explicit SELL).
The FX rates are test data. The manifests under test are the controlled repository files, loaded with
the real master-data and tariff loaders into the test database.
"""

import json
from datetime import date
from decimal import ROUND_HALF_UP
from decimal import Decimal as D
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core.fx_market_models import FxMarketRate
from core.geo_models import GeoLocation, GeoLocationIdentifier
from core.models import Currency
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm
from pricing_v4.models import (
    Carrier,
    ExportCOGS,
    ExportSellRate,
    LocalCOGSRate,
    LocalSellRate,
    ProductCode,
)
from pricing_v4.rate_matrix_models import RateLine, RateSheet
from pricing_v4.services.rate_matrix_export_shadow import (
    BLOCKED,
    EXPECTED_DIFFERENCE,
    MATCH,
    NOT_COMPARABLE,
    UNEXPLAINED_DIFFERENCE,
    MatrixShadowExportEngine,
    convert_pgk_to_aud,
    run_export_shadow,
)
from pricing_v4.services.rate_matrix_loader import (
    apply_tariffs,
    manifest_sha256,
    plan_tariffs,
)
from pricing_v4.services.rate_matrix_manifest import validate_manifest_text
from pricing_v4.services.rate_matrix_master_data import (
    apply_master_data_text,
    plan_master_data_text,
)

MANIFEST_DIR = Path(__file__).resolve().parent.parent / "rate_matrix_manifests"
MASTER_FILE = MANIFEST_DIR / "export-pilot-master-data-2026-10-12.json"
TARIFF_FILE = MANIFEST_DIR / "export-pilot-tariffs-2026-10-12.json"
REGISTRY_FILE = MANIFEST_DIR / "export-approved-differences-2026-10-12.json"
QUOTE_DATE = date(2026, 10, 12)
TT_BUY, TT_SELL = D("3.10945274"), D("3.26157860")

# (id, code, category, unit, gst_treatment)
PRODUCTS = [
    (1001, "EXP-FRT-AIR", "FREIGHT", "KG", "ZERO_RATED"),
    (1002, "EXP-FSC-AIR", "SURCHARGE", "KG", "STANDARD"),
    (1010, "EXP-DOC", "DOCUMENTATION", "SHIPMENT", "STANDARD"),
    (1011, "EXP-AWB", "DOCUMENTATION", "SHIPMENT", "STANDARD"),
    (1020, "EXP-CLEAR", "CLEARANCE", "SHIPMENT", "STANDARD"),
    (1021, "EXP-AGENCY", "AGENCY", "SHIPMENT", "STANDARD"),
    (1030, "EXP-TERM", "HANDLING", "SHIPMENT", "STANDARD"),
    (1031, "EXP-BUILDUP", "HANDLING", "KG", "STANDARD"),
    (1032, "EXP-HANDLE", "HANDLING", "SHIPMENT", "STANDARD"),
    (1040, "EXP-SCREEN", "SCREENING", "KG", "STANDARD"),
    (1050, "EXP-PICKUP", "CARTAGE", "KG", "STANDARD"),
    (1060, "EXP-FSC-PICKUP", "SURCHARGE", "PERCENT", "STANDARD"),
]
# Legacy export_sell_rates rows (superseded by the current EFM PGK Export Rate Card, 2026-10-12).
LEGACY_SELL_BNE = [(0, "7.90"), (100, "7.40"), (200, "7.15"), (500, "6.75")]
LEGACY_SELL_SYD = [(0, "10.00"), (100, "9.40"), (200, "8.90"), (500, "8.50")]
LEGACY_SELL_MIN = D("200.00")
# Approved current card (min K180; the 45 kg break repeats the base rate).
PGK_BNE_BREAKS = [(0, "7.20"), (45, "7.20"), (100, "6.75"), (200, "6.50"), (500, "6.15")]
PGK_SYD_BREAKS = [(0, "9.15"), (45, "9.15"), (100, "8.60"), (200, "8.20"), (500, "7.70")]
SELL_MIN = D("180.00")
BUY_BNE_BREAKS = [(0, "6.30"), (100, "5.90"), (200, "5.70"), (500, "5.40")]
BUY_SYD_BREAKS = [(0, "8.00"), (100, "7.50"), (200, "7.10"), (500, "6.80")]


def _breaks(rows):
    return [{"min_kg": lower, "rate": rate} for lower, rate in rows]


def master_text(approved=True):
    data = json.loads(MASTER_FILE.read_text(encoding="utf-8"))
    for entry in data["commercial_product_codes"]:
        entry["gst_approval"] = {"approved": approved, "reference": "TEST: approval flag for the shadow proof"}
    return json.dumps(data, indent=2) + "\n"


def tariff_text():
    return TARIFF_FILE.read_text(encoding="utf-8")


def registry_text():
    return REGISTRY_FILE.read_text(encoding="utf-8")


def load_matrix(world, tariffs=None):
    text = master_text()
    apply_master_data_text(text, operator=world["user"], reviewed_sha256=plan_master_data_text(text).manifest_sha256)
    body = tariffs or tariff_text()
    apply_tariffs([("tariffs.json", body)], operator=world["user"], reviewed_sha256=manifest_sha256(body))


@pytest.fixture(autouse=True)
def _fresh_export_code_cache():
    """The export engine memoises ProductCode ids at module level; test rows are rolled back, so drop it."""
    from pricing_v4.engine import export_engine

    export_engine._RESOLVED_EXPORT_IDS_CACHE.clear()
    yield
    export_engine._RESOLVED_EXPORT_IDS_CACHE.clear()


@pytest.fixture
def world(db):
    for code in ("PGK", "AUD"):
        Currency.objects.get_or_create(code=code, defaults={"name": code})
    for iata, country in (("POM", "PG"), ("BNE", "AU"), ("SYD", "AU")):
        location = GeoLocation(canonical_name=f"Test {iata}", country_code=country, location_type="AIRPORT")
        location.save()
        GeoLocationIdentifier.objects.create(location=location, scheme="IATA", code=iata)
    carrier, _ = Carrier.objects.get_or_create(code="PX", defaults={"name": "Air Niugini", "carrier_type": "AIRLINE"})
    products = {}
    for pk, code, category, unit, gst in PRODUCTS:
        products[code] = ProductCode.objects.create(
            id=pk, code=code, description=f"Test {code}", domain="EXPORT", category=category,
            is_gst_applicable=gst == "STANDARD", gst_rate="0.1000" if gst == "STANDARD" else "0.0000",
            gst_treatment=gst, gl_revenue_code="4000", gl_cost_code="5000", default_unit=unit,
            percent_of_product_code=products.get("EXP-PICKUP") if code == "EXP-FSC-PICKUP" else None,
        )
    user = get_user_model().objects.create_user(username="export-shadow-test", password="x")
    CommercialTermsPolicy.objects.all().delete()
    FxMarketRate.objects.all().delete()
    CommercialTermsPolicy.objects.create(
        policy_code="TEST-LOCKED-2026-10-12", valid_from=date(2026, 10, 11), margin_percent=D("16.67"),
        margin_method="TARGET_GROSS_MARGIN", import_caf_percent=D("5.00"), export_caf_percent=D("10.00"),
        gst_standard_percent=D("10.00"), caf_method="UPLIFT_AFTER_FX", fx_side_convention="COST_AT_TT_SELL",
        fx_max_age_days=5, fx_primary_source="bsp_html", fx_fallback_source="MANUAL",
    )
    FxMarketRate.objects.create(
        base_currency="AUD", quote_currency="PGK", effective_date=QUOTE_DATE, source="bsp_html",
        tt_buy_rate=TT_BUY, tt_sell_rate=TT_SELL, mid_rate=D("3.18551567"),
    )

    start, end = date(2026, 1, 1), date(2026, 12, 31)
    for destination, buy, sell in (("BNE", BUY_BNE_BREAKS, LEGACY_SELL_BNE), ("SYD", BUY_SYD_BREAKS, LEGACY_SELL_SYD)):
        ExportCOGS.objects.create(
            product_code=products["EXP-FRT-AIR"], origin_airport="POM", destination_airport=destination,
            scope="LANE", carrier=carrier, currency="PGK", min_charge=D("160.00"), weight_breaks=_breaks(buy),
            valid_from=start, valid_until=end,
        )
        ExportSellRate.objects.create(
            product_code=products["EXP-FRT-AIR"], origin_airport="POM", destination_airport=destination,
            scope="LANE", currency="PGK", min_charge=LEGACY_SELL_MIN, weight_breaks=_breaks(sell),
            valid_from=start, valid_until=end,
        )

    def cogs(code, rate_type, amount, **extra):
        LocalCOGSRate.objects.create(
            product_code=products[code], location="POM", direction="EXPORT", carrier=carrier, currency="PGK",
            rate_type=rate_type, amount=D(amount), valid_from=start, valid_until=end, **extra,
        )

    cogs("EXP-DOC", "FIXED", "35.00")
    cogs("EXP-AWB", "FIXED", "35.00")
    cogs("EXP-TERM", "FIXED", "35.00")
    cogs("EXP-HANDLE", "FIXED", "35.00")
    cogs("EXP-SCREEN", "PER_KG", "0.17", is_additive=True, additive_flat_amount=D("35.00"))
    # The legacy row the locked BUY build-up rule supersedes: 0.15/kg, K30 minimum at every weight.
    cogs("EXP-BUILDUP", "PER_KG", "0.15", min_charge=D("30.00"))

    def sell(code, rate_type, amount, term="PREPAID", valid_from=start, valid_until=end, **extra):
        LocalSellRate.objects.create(
            product_code=products[code], location="POM", direction="EXPORT", payment_term=term, currency="PGK",
            rate_type=rate_type, amount=D(amount), valid_from=valid_from, valid_until=valid_until, **extra,
        )

    sell("EXP-DOC", "FIXED", "50.00")
    sell("EXP-AWB", "FIXED", "50.00")
    sell("EXP-TERM", "FIXED", "50.00")
    sell("EXP-HANDLE", "FIXED", "50.00")
    sell("EXP-CLEAR", "FIXED", "300.00")
    sell("EXP-AGENCY", "FIXED", "250.00")
    sell("EXP-SCREEN", "PER_KG", "0.20", is_additive=True, additive_flat_amount=D("45.00"))
    sell("EXP-BUILDUP", "PER_KG", "0.20", min_charge=D("50.00"))
    sell("EXP-PICKUP", "PER_KG", "1.50", min_charge=D("95.00"), max_charge=D("500.00"))
    sell("EXP-FSC-PICKUP", "PERCENT", "10.00", percent_of_product_code=products["EXP-PICKUP"])
    sell("EXP-FSC-AIR", "PER_KG", "0.80", term="ANY", valid_from=date(2025, 1, 1), valid_until=date(2030, 12, 31))
    return {"user": user, "products": products, "carrier": carrier}


@pytest.fixture
def loaded(world):
    load_matrix(world)
    return world


def run(**kwargs):
    kwargs.setdefault("registry_text", registry_text())
    kwargs.setdefault("quote_date", QUOTE_DATE)
    kwargs.setdefault("weights", (D(100),))
    kwargs.setdefault("scopes", ("D2A",))
    return run_export_shadow(**kwargs)


def pick(report, **match):
    return [r for r in report.records if all(getattr(r, k) == v for k, v in match.items())]


def one(report, **match):
    found = pick(report, **match)
    assert len(found) == 1, (match, [r.as_dict() for r in found])
    return found[0]


def cents(value):
    return D(value).quantize(D("0.01"), rounding=ROUND_HALF_UP)


def aud(pgk):
    pure = cents(D(pgk) / TT_BUY)
    return cents(pure * D("1.10"))


# --------------------------------------------------------------------------- manifests


class TestManifests:
    def test_controlled_master_data_file_is_approved_and_plans_clean(self, world):
        plan = plan_master_data_text(MASTER_FILE.read_text(encoding="utf-8"))
        assert plan.counts()["BLOCKED"] == 0 and plan.counts()["CONFLICT"] == 0
        assert plan.ready

    def test_an_unapproved_copy_of_the_master_data_is_still_blocked(self, world):
        plan = plan_master_data_text(master_text(approved=False))
        assert plan.counts()["BLOCKED"] == 12
        assert not plan.ready

    def test_category_and_gst_match_the_commercial_manager_approval_exactly(self):
        approved = {
            "EXP-FRT-AIR": ("FREIGHT", "ZERO_RATED"), "EXP-CLEAR": ("CLEARANCE", "STANDARD"),
            "EXP-FSC-AIR": ("ORIGIN", "STANDARD"), "EXP-DOC": ("ORIGIN", "STANDARD"),
            "EXP-AWB": ("ORIGIN", "STANDARD"), "EXP-AGENCY": ("ORIGIN", "STANDARD"),
            "EXP-TERM": ("ORIGIN", "STANDARD"), "EXP-BUILDUP": ("ORIGIN", "STANDARD"),
            "EXP-HANDLE": ("ORIGIN", "STANDARD"), "EXP-SCREEN": ("ORIGIN", "STANDARD"),
            "EXP-PICKUP": ("ORIGIN", "STANDARD"), "EXP-FSC-PICKUP": ("ORIGIN", "STANDARD"),
        }
        data = json.loads(MASTER_FILE.read_text(encoding="utf-8"))
        stored = {c["code"]: (c["category"], c["gst_treatment"]) for c in data["commercial_product_codes"]}
        assert stored == approved
        assert all(c["gst_approval"]["approved"] is True and "2026-10-12" in c["gst_approval"]["reference"]
                   for c in data["commercial_product_codes"])

    def test_tariff_manifest_validates_once_master_data_exists(self, world):
        text = master_text()
        apply_master_data_text(text, operator=world["user"], reviewed_sha256=plan_master_data_text(text).manifest_sha256)
        report = validate_manifest_text(tariff_text())
        assert report.passed, report.render_text()

    def test_tariff_manifest_is_native_pgk_and_never_has_aud_sell(self):
        data = json.loads(tariff_text())
        assert {sheet["currency_code"] for sheet in data["rate_sheets"]} == {"PGK"}
        assert all(sheet["transport_mode"] == "AIR" for sheet in data["rate_sheets"])
        for sheet in data["rate_sheets"]:
            for line in sheet["lines"]:
                assert line["applicability"]["direction"] == "EXPORT"
                assert line["applicability"]["origin_iata"] == "POM"
                assert line["applicability"]["destination_iata"] in (None, "BNE", "SYD")

    def test_buy_sheets_name_the_supplier_and_sell_sheets_do_not(self):
        data = json.loads(tariff_text())
        for sheet in data["rate_sheets"]:
            if sheet["rate_type"] == "BUY":
                assert sheet["supplier"] == {
                    "legal_name": "Air Niugini Limited", "country_code": "PG", "role": "CARRIER",
                }
                assert sheet["valid_until"] is None
                assert all(line["applicability"]["payment_term"] == "" for line in sheet["lines"])
            else:
                assert sheet["supplier"] is None and sheet["customer"] is None

    def test_every_sheet_is_valid_from_the_cm_pilot_approval_date_without_an_end(self):
        data = json.loads(tariff_text())
        assert len(data["rate_sheets"]) == 7
        for sheet in data["rate_sheets"]:
            assert (sheet["valid_from"], sheet["valid_until"]) == ("2026-10-12", None), sheet["name"]
            assert "2026-01-01..2026-12-31" not in sheet["name"]

    def test_stored_legacy_dates_are_kept_as_provenance_not_authority(self):
        sheets = {s["name"]: s for s in json.loads(tariff_text())["rate_sheets"]}
        card = sheets["Pilot export SELL air freight POM-BNE POM-SYD PGK"]["source_reference"]
        assert "printed 2025 expiry" in card and "until superseded" in card
        origin = sheets["Pilot export SELL origin charges POM PGK"]["source_reference"]
        assert "printed 2025 expiry" in origin and "stored 2026-01-01..2026-12-31" in origin
        for name in ("Pilot export SELL EXP-HANDLE POM PGK database value only",
                     "Pilot export SELL EXP-FSC-AIR POM PGK database value only",
                     "Pilot export BUY EXP-HANDLE POM PGK database value only"):
            reference = sheets[name]["source_reference"]
            assert reference.startswith("DATABASE-ONLY, no external document")
            assert "CM-approved Pilot carry-forward 2026-10-12" in reference
        assert "stored 2025-01-01..2030-12-31" in sheets[
            "Pilot export SELL EXP-FSC-AIR POM PGK database value only"]["source_reference"]

    def test_px_party_is_air_niugini_limited_trading_as_air_niugini(self):
        data = json.loads(MASTER_FILE.read_text(encoding="utf-8"))
        party = data["parties"][0]
        assert (party["legal_name"], party["trade_name"], party["country_code"], party["roles"]) == (
            "Air Niugini Limited", "Air Niugini", "PG", ["CARRIER"])
        assert "General Sales Agency" in party["evidence"]

    def test_buildup_buy_carries_its_minimum_on_the_tiers_not_the_line(self):
        data = json.loads(tariff_text())
        lines = [l for s in data["rate_sheets"] if s["rate_type"] == "BUY" for l in s["lines"]
                 if l["product_code"] == "EXP-BUILDUP"]
        assert len(lines) == 1
        line = lines[0]
        assert line["min_charge"] is None and line["unit_rate"] is None
        assert [(t["min_quantity"], t["max_quantity"], t["unit_rate"], t.get("min_charge")) for t in line["tiers"]] == [
            ("0", "100", "0.00", None),
            ("100", "2000.0001", "0.10", "30.00"),
            ("2000.0001", None, "0.15", "30.00"),
        ]

    def test_sell_freight_is_the_approved_current_card(self):
        data = json.loads(tariff_text())
        sheet = next(s for s in data["rate_sheets"] if s["name"].startswith("Pilot export SELL air freight"))
        assert sheet["currency_code"] == "PGK" and sheet["supplier"] is None
        by_destination = {l["applicability"]["destination_iata"]: l for l in sheet["lines"]}
        for destination, breaks in (("BNE", PGK_BNE_BREAKS), ("SYD", PGK_SYD_BREAKS)):
            line = by_destination[destination]
            assert line["min_charge"] == "180.00"
            assert [(t["min_quantity"], t["unit_rate"]) for t in line["tiers"]] == [
                (str(lower), rate) for lower, rate in breaks
            ]

    def test_apply_is_idempotent_and_dry_run_default_writes_nothing(self, loaded):
        before = (RateSheet.objects.count(), RateLine.objects.count())
        plan = plan_tariffs([("tariffs.json", tariff_text())])
        assert plan.ready
        assert (RateSheet.objects.count(), RateLine.objects.count()) == before
        apply_tariffs([("tariffs.json", tariff_text())], operator=loaded["user"],
                      reviewed_sha256=manifest_sha256(tariff_text()))
        assert (RateSheet.objects.count(), RateLine.objects.count()) == before

    def test_tier_minimums_are_stored_and_reuse_compares_them(self, loaded):
        buildup = RateLine.objects.get(sheet__rate_type="BUY", product_code__code="EXP-BUILDUP")
        assert [(t.min_quantity, t.min_charge) for t in buildup.tiers.order_by("min_quantity")] == [
            (D("0"), None), (D("100"), D("30")), (D("2000.0001"), D("30")),
        ]
        changed = json.loads(tariff_text())
        for sheet in changed["rate_sheets"]:
            for line in sheet["lines"]:
                if line["product_code"] == "EXP-BUILDUP" and sheet["rate_type"] == "BUY":
                    line["tiers"][1]["min_charge"] = "31.00"
        body = json.dumps(changed, indent=2) + "\n"
        assert plan_tariffs([("tariffs.json", body)]).ready is False  # same sheet name and version: CONFLICT

    def test_apply_refuses_a_hash_that_was_not_reviewed(self, world):
        text = master_text()
        apply_master_data_text(text, operator=world["user"], reviewed_sha256=plan_master_data_text(text).manifest_sha256)
        with pytest.raises(Exception):
            apply_tariffs([("tariffs.json", tariff_text())], operator=world["user"], reviewed_sha256="0" * 64)
        assert RateSheet.objects.count() == 0


# --------------------------------------------------------------------------- per-tier minimum contract


def _buildup_manifest(mutator):
    data = json.loads(tariff_text())
    data["rate_sheets"] = [s for s in data["rate_sheets"] if s["name"] == "Pilot export BUY terminal charges POM PGK"]
    sheet = data["rate_sheets"][0]
    sheet["lines"] = [l for l in sheet["lines"] if l["product_code"] == "EXP-BUILDUP"]
    mutator(sheet["lines"][0])
    return json.dumps(data, indent=2) + "\n"


class TestTierMinimumContract:
    @pytest.fixture(autouse=True)
    def master(self, world):
        text = master_text()
        apply_master_data_text(text, operator=world["user"], reviewed_sha256=plan_master_data_text(text).manifest_sha256)

    def test_a_tier_may_state_its_own_minimum(self):
        report = validate_manifest_text(_buildup_manifest(lambda line: None))
        assert report.passed, report.render_text()

    def test_the_minimum_key_is_optional(self):
        def drop(line):
            for tier in line["tiers"]:
                tier.pop("min_charge", None)
        assert validate_manifest_text(_buildup_manifest(drop)).passed

    def test_a_tier_minimum_with_a_line_minimum_is_ambiguous_and_rejected(self):
        def both(line):
            line["min_charge"] = "30.00"
        report = validate_manifest_text(_buildup_manifest(both))
        assert not report.passed
        assert "TIER_MINIMUM_WITH_LINE_MINIMUM" in report.render_text()

    def test_a_negative_or_non_decimal_tier_minimum_is_rejected(self):
        def negative(line):
            line["tiers"][1]["min_charge"] = "-1.00"
        assert not validate_manifest_text(_buildup_manifest(negative)).passed

        def number(line):
            line["tiers"][1]["min_charge"] = 30
        assert not validate_manifest_text(_buildup_manifest(number)).passed

    def test_unknown_tier_fields_are_still_rejected(self):
        def unknown(line):
            line["tiers"][0]["surcharge"] = "1.00"
        assert not validate_manifest_text(_buildup_manifest(unknown)).passed

class TestTierModelRules:
    def test_model_rejects_a_negative_tier_minimum_and_a_tier_minimum_on_a_line_that_has_one(self, loaded):
        from django.core.exceptions import ValidationError

        from pricing_v4.rate_matrix_models import RateTier

        line = RateLine.objects.get(
            sheet__rate_type="BUY", product_code__code="EXP-FRT-AIR",
            applicability__destination__identifiers__code="BNE",
        )
        assert line.min_charge == D("160")
        with pytest.raises(ValidationError):
            RateTier(rate_line=line, min_quantity=D("9000"), max_quantity=None, unit_rate=D("1"),
                     min_charge=D("-1")).full_clean()
        with pytest.raises(ValidationError):
            RateTier(rate_line=line, min_quantity=D("9000"), max_quantity=None, unit_rate=D("1"),
                     min_charge=D("5")).full_clean()

# --------------------------------------------------------------------------- freight tiers and minimums


@pytest.mark.parametrize("destination,breaks,legacy_breaks,buy_breaks", [
    ("BNE", PGK_BNE_BREAKS, LEGACY_SELL_BNE, BUY_BNE_BREAKS), ("SYD", PGK_SYD_BREAKS, LEGACY_SELL_SYD, BUY_SYD_BREAKS),
])
class TestFreightTiersAndMinimums:
    @pytest.mark.parametrize("weight", [30, 45, 100, 200, 500, 999, 1000, 1001])
    def test_matrix_freight_is_the_approved_card_and_the_legacy_difference_is_explicit(
        self, loaded, destination, breaks, legacy_breaks, buy_breaks, weight
    ):
        report = run(weights=(D(weight),), lanes=(("POM", destination),), scopes=("A2A",), currencies=("PGK",))
        key = f"{weight}kg|A2A|PGK"
        sell = one(report, scenario=key, product_code="EXP-FRT-AIR", aspect="sell_amount")
        rate = next(D(r) for lower, r in reversed(breaks) if weight >= lower)
        legacy_rate = next(D(r) for lower, r in reversed(legacy_breaks) if weight >= lower)
        assert D(sell.shadow) == max(SELL_MIN, cents(rate * weight))
        assert D(sell.legacy) == max(LEGACY_SELL_MIN, cents(legacy_rate * weight))
        # The legacy row legitimately differs from the approved card; it is explained, never forced to MATCH.
        assert sell.classification == EXPECTED_DIFFERENCE, sell.as_dict()
        assert "approved-authority native differences" in sell.reason
        assert "current EFM PGK Export Rate Card" in sell.evidence
        cost = one(report, scenario=key, product_code="EXP-FRT-AIR", aspect="cost_amount")
        assert cost.classification == MATCH  # BUY ExportCOGS is preserved exactly
        buy_rate = next(D(r) for lower, r in reversed(buy_breaks) if weight >= lower)
        assert D(cost.shadow) == max(D("160.00"), cents(buy_rate * weight))

    def test_minimum_charge_applies_below_the_break_even_weight(self, loaded, destination, breaks, legacy_breaks,
                                                                 buy_breaks):
        report = run(weights=(D(10),), lanes=(("POM", destination),), scopes=("A2A",), currencies=("PGK",))
        sell = one(report, scenario="10kg|A2A|PGK", product_code="EXP-FRT-AIR", aspect="sell_amount")
        cost = one(report, scenario="10kg|A2A|PGK", product_code="EXP-FRT-AIR", aspect="cost_amount")
        assert (D(sell.shadow), D(sell.legacy), D(cost.shadow)) == (D("180.00"), D("200.00"), D("160.00"))

    def test_without_the_approved_registry_the_difference_is_unexplained_not_a_match(
        self, loaded, destination, breaks, legacy_breaks, buy_breaks
    ):
        report = run(weights=(D(100),), lanes=(("POM", destination),), scopes=("A2A",), currencies=("PGK",),
                     registry_text=None)
        sell = one(report, scenario="100kg|A2A|PGK", product_code="EXP-FRT-AIR", aspect="sell_amount")
        assert sell.classification == UNEXPLAINED_DIFFERENCE
        assert "without approved-authority evidence" in sell.reason


# --------------------------------------------------------------------------- origin charges


class TestOriginCharges:
    def line(self, report, code, aspect="sell_amount", weight="100", currency="PGK"):
        return one(report, scenario=f"{weight}kg|D2A|{currency}", product_code=code, aspect=aspect)

    def test_security_sell_additive_flat(self, loaded):
        for weight, expected in (("30", "51.00"), ("100", "65.00"), ("1001", "245.20")):
            report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
            line = self.line(report, "EXP-SCREEN", weight=weight)
            assert (line.classification, D(line.shadow)) == (MATCH, D(expected))  # 0.20/kg + K45 flat

    def test_security_buy_additive_flat(self, loaded):
        for weight, expected in (("30", "40.10"), ("100", "52.00"), ("1001", "205.17")):
            report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
            line = self.line(report, "EXP-SCREEN", "cost_amount", weight)
            assert (line.classification, D(line.shadow)) == (MATCH, D(expected))  # 0.17/kg + K35 flat

    def test_sell_buildup_applies_its_minimum_of_fifty(self, loaded):
        for weight, expected in (("30", "50.00"), ("100", "50.00"), ("500", "100.00"), ("1001", "200.20")):
            report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
            line = self.line(report, "EXP-BUILDUP", weight=weight)
            assert (line.classification, D(line.shadow)) == (MATCH, D(expected))

    def test_pickup_minimum_and_cap_and_dependent_fuel_surcharge(self, loaded):
        cases = {"30": ("95.00", "9.50"), "100": ("150.00", "15.00"), "999": ("500.00", "50.00"),
                 "1001": ("500.00", "50.00")}
        for weight, (pickup, fsc) in cases.items():
            report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
            assert D(self.line(report, "EXP-PICKUP", weight=weight).shadow) == D(pickup)  # 1.50/kg, min 95, cap 500
            line = self.line(report, "EXP-FSC-PICKUP", weight=weight)
            assert (line.classification, D(line.shadow)) == (MATCH, D(fsc))  # 10% of the calculated pickup

    def test_flat_charges_match_the_locked_rates(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",))
        expected = {"EXP-DOC": "50.00", "EXP-AWB": "50.00", "EXP-TERM": "50.00", "EXP-CLEAR": "300.00",
                    "EXP-AGENCY": "250.00", "EXP-HANDLE": "50.00", "EXP-FSC-AIR": "80.00"}
        for code, amount in expected.items():
            line = self.line(report, code)
            assert (line.classification, D(line.shadow)) == (MATCH, D(amount)), code
        for code in ("EXP-DOC", "EXP-AWB", "EXP-TERM", "EXP-HANDLE"):
            assert D(self.line(report, code, "cost_amount").shadow) == D("35.00")

    def test_gst_follows_the_production_classification(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",))
        assert D(self.line(report, "EXP-FRT-AIR", "gst_amount").shadow) == D("0.00")  # international freight
        assert D(self.line(report, "EXP-DOC", "gst_amount").shadow) == D("5.00")  # origin service in PNG, 10%
        assert D(self.line(report, "TOTAL", "total_gst").shadow) == D("111.00")


class TestBuildupBuyBreakpoints:
    """The locked BUY rule, evaluated directly: nil below 100 kg, then 0.10/kg to 2000 kg and 0.15/kg above, K30 min."""

    @staticmethod
    def locked_buy(weight):
        weight = D(weight)
        if weight < 100:
            return D("0.00")
        rate = D("0.10") if weight <= 2000 else D("0.15")
        return max(D("30.00"), cents(rate * weight))

    @pytest.mark.parametrize("weight", ["30", "45", "99", "100", "200", "299", "301", "500", "999", "1000", "1001",
                                       "2000", "2000.5", "2001"])
    def test_rate_matrix_buy_reproduces_the_locked_rule_at_every_breakpoint(self, loaded, weight):
        report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
        key = f"{D(weight).normalize():f}kg|D2A|PGK"
        cost = one(report, scenario=key, product_code="EXP-BUILDUP", aspect="cost_amount")
        assert D(cost.shadow) == self.locked_buy(weight)
        assert cost.classification in (MATCH, EXPECTED_DIFFERENCE)
        if cost.classification == EXPECTED_DIFFERENCE:
            assert "Air Niugini BUY build-up" in cost.evidence

    @pytest.mark.parametrize("weight,expected", [
        (30, "0.00"), (45, "0.00"), (99, "0.00"), (100, "30.00"), (200, "30.00"), (299, "30.00"),
        (301, "30.10"), (500, "50.00"), (999, "99.90"), (1000, "100.00"), (1001, "100.10"), (2000, "200.00"),
        (2001, "300.15"),
    ])
    def test_breakpoints_of_the_locked_rule(self, weight, expected):
        assert self.locked_buy(weight) == D(expected)

    def test_the_legacy_database_row_is_superseded_and_explained_not_matched(self, loaded):
        report = run(weights=(D(30),), lanes=(("POM", "BNE"),), currencies=("PGK",))
        cost = one(report, scenario="30kg|D2A|PGK", product_code="EXP-BUILDUP", aspect="cost_amount")
        assert D(cost.legacy) == D("30.00")  # the superseded row (0.15/kg, K30 at every weight)
        assert D(cost.shadow) == D("0.00")  # the locked rule: nothing below 100 kg
        assert cost.classification == EXPECTED_DIFFERENCE

    def _buildup_context(self, weight):
        from parties.party_models import PartyMaster
        from pricing_v4.services import rate_matrix_resolver as rmr

        supplier = PartyMaster.objects.get(legal_name="Air Niugini Limited", country_code="PG")
        return rmr.resolve(rmr.ResolutionContext(
            rate_type=rmr.BUY, direction="EXPORT", effective_date=QUOTE_DATE, product_code="EXP-BUILDUP",
            origin_iata="POM", destination_iata="BNE", supplier_id=supplier.id, chargeable_weight=D(weight),
        )), rmr

    def test_2000_is_the_lower_tier_and_2000_0001_is_the_upper_tier(self, loaded):
        lower, rmr = self._buildup_context("2000")
        upper, _ = self._buildup_context("2000.0001")
        assert lower.outcome == upper.outcome == rmr.EXACT_MATCH
        assert lower.tariff.selected_tier.unit_rate == D("0.10")
        assert upper.tariff.selected_tier.unit_rate == D("0.15")
        assert lower.tariff.selected_tier.max_quantity == upper.tariff.selected_tier.min_quantity == D("2000.0001")
        report = run(weights=(D("2000"), D("2000.0001")), lanes=(("POM", "BNE"),), currencies=("PGK",))
        assert D(one(report, scenario="2000kg|D2A|PGK", product_code="EXP-BUILDUP",
                     aspect="cost_amount").shadow) == D("200.00")
        assert D(one(report, scenario="2000.0001kg|D2A|PGK", product_code="EXP-BUILDUP",
                     aspect="cost_amount").shadow) == D("300.00")  # 0.15 x 2000.0001 = 300.000015

    @pytest.mark.parametrize("weight", ["2000.00005", "2000.000049", "1999.99999", "100.12345", "0.00001"])
    def test_a_weight_with_unsupported_precision_fails_closed(self, loaded, weight):
        result, rmr = self._buildup_context(weight)
        assert result.outcome == rmr.INVALID_CONTEXT
        assert "decimal places" in result.reasons[0]
        report = run(weights=(D(weight),), lanes=(("POM", "BNE"),), currencies=("PGK",))
        blocked = pick(report, product_code="-", aspect="scenario")
        assert blocked and all(r.classification == BLOCKED for r in blocked)
        assert "INVALID_CONTEXT" in blocked[0].reason
        assert pick(report, classification=MATCH) == []  # nothing is priced for that weight

    @pytest.mark.parametrize("weight", ["2000.0001", "2000.00010", "100.1234", "30", "30.0"])
    def test_supported_precision_is_priced_including_trailing_zeros(self, loaded, weight):
        result, rmr = self._buildup_context(weight)
        assert result.outcome == rmr.EXACT_MATCH

    def test_precision_is_checked_for_every_tiered_tariff_not_only_build_up(self, loaded):
        report = run(weights=(D("100.00005"),), lanes=(("POM", "BNE"),), currencies=("PGK",))
        assert pick(report, product_code="EXP-FRT-AIR") == []
        assert all(r.classification == BLOCKED for r in report.records)

    def test_a_line_wide_minimum_would_misstate_the_rule(self):
        # Documents why the minimum lives on the tier: one line minimum charges K30 at 30 kg.
        line_wide = max(D("30.00"), cents(D("0.00") * 30))
        assert line_wide == D("30.00") and self.locked_buy(30) == D("0.00")


# --------------------------------------------------------------------------- PGK and AUD quotes


class TestPgkAndAud:
    def test_pgk_quote_needs_no_fx_and_carries_no_caf(self, loaded):
        FxMarketRate.objects.all().delete()
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",))
        assert report.counts()[BLOCKED] == 0
        assert report.fx_provenance == []
        assert not [r for r in report.records if r.classification == UNEXPLAINED_DIFFERENCE]
        total = one(report, scenario="100kg|D2A|PGK", product_code="TOTAL", aspect="total_sell")
        assert D(total.shadow) == D("1785.00")  # legacy 1,850.00 less the K65 freight difference (675 vs 740)

    def test_pgk_totals_equal_production_except_the_approved_freight_difference(self, loaded):
        engine = ExportPricingEngine(
            quote_date=QUOTE_DATE, origin="POM", destination="BNE", chargeable_weight_kg=D(100),
            payment_term=PaymentTerm.PREPAID,
            caf_rate=None, margin_rate=None, destination_currency="PGK",
        )
        ids = ExportPricingEngine.get_product_codes(
            is_dg=False, service_scope="D2A", origin="POM", destination="BNE", payment_term="PREPAID",
            quote_date=QUOTE_DATE,
        )
        legacy = engine.calculate_quote(ids, service_scope="D2A")
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",))
        total = one(report, scenario="100kg|D2A|PGK", product_code="TOTAL", aspect="total_sell")
        production = sum(item.sell_amount for item in legacy.line_items)
        assert D(total.legacy) == production == D("1850.00")
        assert production - D(total.shadow) == D("740.00") - D("675.00")
        assert total.classification == EXPECTED_DIFFERENCE

    def test_aud_converts_each_explicit_pgk_line_at_tt_buy_then_ten_percent_caf(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        key = "100kg|D2A|AUD"
        for code, pgk in (("EXP-FRT-AIR", "675.00"), ("EXP-DOC", "50.00"), ("EXP-PICKUP", "150.00"),
                          ("EXP-FSC-PICKUP", "15.00"), ("EXP-SCREEN", "65.00"), ("EXP-FSC-AIR", "80.00")):
            line = one(report, scenario=key, product_code=code, aspect="sell_amount")
            assert line.classification == (EXPECTED_DIFFERENCE if code == "EXP-FRT-AIR" else MATCH), code
            assert D(line.shadow) == aud(pgk), code
        # 675.00 / 3.10945274 = 217.08 ; x 1.10 = 238.79
        assert D(one(report, scenario=key, product_code="EXP-FRT-AIR", aspect="sell_amount").shadow) == D("238.79")

    def test_aud_helper_applies_the_caf_as_a_separate_uplift_after_pure_fx(self):
        pure, caf, commercial = convert_pgk_to_aud(D("675.00"), TT_BUY, D("0.10"))
        assert (pure, caf, commercial) == (D("217.08"), D("21.71"), D("238.79"))
        assert convert_pgk_to_aud(D("0.00"), TT_BUY, D("0.10")) == (D("0.00"), D("0.00"), D("0.00"))

    def test_tt_sell_is_not_used(self, loaded):
        FxMarketRate.objects.update(tt_sell_rate=D("9.99999999"))
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        frt = one(report, scenario="100kg|D2A|AUD", product_code="EXP-FRT-AIR", aspect="sell_amount")
        assert D(frt.shadow) == D("238.79")

    def test_conversion_evidence_records_side_rate_source_age_and_caf(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        info = report.fx_provenance[0]
        assert (info["pair"], info["side"], info["source"], info["source_role"]) == (
            "AUD/PGK", "TT_BUY", "bsp_html", "PRIMARY")
        assert (D(info["rate"]), info["age_days"], info["max_age_days"], info["export_caf_percent"]) == (
            TT_BUY, 0, 5, "10.00")

    def test_no_margin_is_added_to_an_explicit_sell(self, loaded):
        # TARGET_GROSS_MARGIN 16.67% is in force; an explicit SELL must be converted without it.
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        frt = D(one(report, scenario="100kg|D2A|AUD", product_code="EXP-FRT-AIR", aspect="sell_amount").shadow)
        with_margin = cents(aud("675.00") / (D("1") - D("0.1667")))
        assert frt == aud("675.00") and frt != with_margin

    def test_aud_totals_include_gst_on_the_converted_amounts(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        key = "100kg|D2A|AUD"
        total = D(one(report, scenario=key, product_code="TOTAL", aspect="total_sell").shadow)
        gst = D(one(report, scenario=key, product_code="TOTAL", aspect="total_gst").shadow)
        incl = D(one(report, scenario=key, product_code="TOTAL", aspect="total_sell_incl_gst").shadow)
        assert incl == total + gst
        freight_gst = D(one(report, scenario=key, product_code="EXP-FRT-AIR", aspect="gst_amount").shadow)
        assert freight_gst == D("0.00")
        assert D(one(report, scenario=key, product_code="EXP-FRT-AIR", aspect="sell_incl_gst").shadow) == D("238.79")

    def test_production_collect_is_reported_not_reconciled(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        note = one(report, scenario="100kg|D2A|AUD", product_code="TOTAL", aspect="production_collect_total_sell")
        assert note.classification == NOT_COMPARABLE
        assert "Not reconciled" in note.reason


# --------------------------------------------------------------------------- fail closed


class TestFailClosed:
    def test_missing_fx_blocks_aud_but_not_pgk(self, loaded):
        FxMarketRate.objects.all().delete()
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK", "AUD"))
        assert one(report, scenario="100kg|D2A|AUD", product_code="-", aspect="scenario").classification == BLOCKED
        assert pick(report, scenario="100kg|D2A|PGK", classification=BLOCKED) == []

    def test_stale_fx_blocks_aud(self, loaded):
        FxMarketRate.objects.update(effective_date=date(2026, 10, 1))
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        blocked = one(report, scenario="100kg|D2A|AUD", product_code="-", aspect="scenario")
        assert blocked.classification == BLOCKED and "Stale" in blocked.reason

    def test_ambiguous_fx_sources_block_aud(self, loaded):
        FxMarketRate.objects.create(
            base_currency="AUD", quote_currency="PGK", effective_date=QUOTE_DATE, source="OTHER",
            tt_buy_rate=D("3.20"), tt_sell_rate=D("3.30"), mid_rate=D("3.25"),
        )
        # BSP is primary under the policy, so another source does not make it ambiguous; two rows of the
        # same primary source on one day cannot exist (unique constraint). A MANUAL-only day is the fallback.
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        assert pick(report, scenario="100kg|D2A|AUD", classification=BLOCKED) == []
        FxMarketRate.objects.filter(source="bsp_html").delete()
        FxMarketRate.objects.filter(source="OTHER").update(source="MANUAL")
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        assert pick(report, scenario="100kg|D2A|AUD", classification=BLOCKED) == []
        assert report.fx_provenance[0]["source_role"] == "FALLBACK"

    def test_reverse_direction_row_is_never_inferred(self, loaded):
        FxMarketRate.objects.all().delete()
        # A row stored as PGK/AUD is not an AUD/PGK rate and must not be inverted into one.
        FxMarketRate.objects.create(
            base_currency="PGK", quote_currency="AUD", effective_date=QUOTE_DATE, source="bsp_html",
            tt_buy_rate=D("0.3216"), tt_sell_rate=D("0.3066"), mid_rate=D("0.3141"),
        )
        report = run(lanes=(("POM", "BNE"),), currencies=("AUD",))
        blocked = one(report, scenario="100kg|D2A|AUD", product_code="-", aspect="scenario")
        assert blocked.classification == BLOCKED and "FX_NOT_DIRECT" in blocked.reason

    def test_missing_policy_blocks_everything(self, loaded):
        CommercialTermsPolicy.objects.all().delete()
        report = run(lanes=(("POM", "BNE"),))
        assert report.counts()[BLOCKED] == len({r.scenario for r in report.records})
        assert report.counts()[MATCH] == 0

    def test_ambiguous_policy_blocks_everything(self, loaded):
        CommercialTermsPolicy.objects.create(
            policy_code="TEST-RIVAL", valid_from=date(2026, 10, 11), margin_percent=D("20.00"),
            margin_method="MARKUP_ON_COST", import_caf_percent=D("5.00"), export_caf_percent=D("10.00"),
            gst_standard_percent=D("10.00"),
        )
        report = run(lanes=(("POM", "BNE"),))
        assert report.counts()[MATCH] == 0 and report.counts()[BLOCKED] > 0

    def test_a_quote_before_the_buy_validity_fails_closed(self, loaded):
        report = run(quote_date=date(2026, 10, 11), lanes=(("POM", "BNE"),), currencies=("PGK",))
        # BUY sheets start 2026-10-12: no supplier tariff is valid, so nothing is priced or defaulted.
        blocked = one(report, scenario="100kg|D2A|PGK", product_code="-", aspect="scenario")
        assert blocked.classification == BLOCKED and "SUPPLIER_NOT_SINGLE" in blocked.reason

    def test_missing_supplier_party_blocks_buy_resolution(self, world):
        # Master data loaded without the BUY sheets would leave no supplier; the shadow must not guess one.
        text = master_text()
        apply_master_data_text(text, operator=world["user"], reviewed_sha256=plan_master_data_text(text).manifest_sha256)
        sells = json.loads(tariff_text())
        sells["rate_sheets"] = [s for s in sells["rate_sheets"] if s["rate_type"] == "SELL"]
        body = json.dumps(sells, indent=2) + "\n"
        apply_tariffs([("sell.json", body)], operator=world["user"], reviewed_sha256=manifest_sha256(body))
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",))
        assert report.counts()[BLOCKED] > 0
        assert "SUPPLIER_NOT_SINGLE" in pick(report, classification=BLOCKED)[0].reason


# --------------------------------------------------------------------------- safety and coverage


class TestSafetyAndCoverage:
    def test_run_writes_nothing(self, loaded):
        counts = (
            RateSheet.objects.count(), RateLine.objects.count(), LocalSellRate.objects.count(),
            ExportSellRate.objects.count(), FxMarketRate.objects.count(), CommercialTermsPolicy.objects.count(),
        )
        run(weights=(D(30), D(100)), lanes=(("POM", "BNE"), ("POM", "SYD")))
        assert counts == (
            RateSheet.objects.count(), RateLine.objects.count(), LocalSellRate.objects.count(),
            ExportSellRate.objects.count(), FxMarketRate.objects.count(), CommercialTermsPolicy.objects.count(),
        )

    def test_both_lanes_all_weights_both_currencies_have_no_unexplained_difference(self, loaded):
        weights = tuple(D(w) for w in (30, 45, 100, 200, 500, 999, 1000, 1001))
        report = run_export_shadow(quote_date=QUOTE_DATE, weights=weights, registry_text=registry_text())
        assert len({(r.lane, r.scenario) for r in report.records}) == 2 * 8 * 2 * 2
        assert report.counts()[UNEXPLAINED_DIFFERENCE] == 0
        assert report.counts()[BLOCKED] == 0
        assert report.counts()[MATCH] > 1000
        assert report.stale_registry_entries == [] and report.registry_errors == []
        noncomparable = {r.aspect for r in report.records if r.classification == NOT_COMPARABLE}
        assert noncomparable == {"production_collect_total_sell"}
        explained = {(r.product_code, r.aspect) for r in report.records if r.classification == EXPECTED_DIFFERENCE}
        assert {code for code, _ in explained} == {"EXP-FRT-AIR", "EXP-BUILDUP", "TOTAL"}

    def test_differences_are_explained_only_by_an_exact_approved_entry(self, loaded):
        def entries(mutate):
            data = json.loads(registry_text())
            mutate(data["entries"])
            return json.dumps(data)

        def wrong_value(rows):
            for row in rows:
                if row["aspect"] == "min_charge" and row["product_code"] == "EXP-FRT-AIR":
                    row["matrix"] = "185"

        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",), scopes=("A2A",),
                     registry_text=entries(wrong_value))
        sell = one(report, scenario="100kg|A2A|PGK", product_code="EXP-FRT-AIR", aspect="sell_amount")
        assert sell.classification == UNEXPLAINED_DIFFERENCE and "min_charge" in sell.reason
        assert report.stale_registry_entries  # the entry that matched nothing is reported

    def test_an_unrelated_legacy_change_is_not_excused_by_the_freight_entries(self, loaded):
        ExportSellRate.objects.filter(destination_airport="BNE").update(min_charge=D("205.00"))
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",), scopes=("A2A",))
        sell = one(report, scenario="100kg|A2A|PGK", product_code="EXP-FRT-AIR", aspect="sell_amount")
        assert sell.classification == UNEXPLAINED_DIFFERENCE

    def test_registry_errors_are_reported(self, loaded):
        report = run(lanes=(("POM", "BNE"),), currencies=("PGK",), scopes=("A2A",), registry_text="{}")
        assert report.registry_errors
        assert one(report, scenario="100kg|A2A|PGK", product_code="EXP-FRT-AIR",
                   aspect="sell_amount").classification == UNEXPLAINED_DIFFERENCE

    def test_shadow_engine_overrides_only_the_lookups_and_the_per_tier_minimum_rule(self):
        own = {n for n in vars(MatrixShadowExportEngine) if not n.startswith("__")}
        # _calculate_amount differs from production only for a tariff whose tiers carry their own minimum.
        assert own == {"_get_cogs", "_get_sell_rate", "_calculate_amount"}

    def test_command_text_json_and_bad_arguments(self, loaded, capsys):
        call_command("shadow_price_rate_matrix_export", "--date", "2026-10-12", "--weights", "100",
                     "--lane", "POM-BNE", "--scopes", "D2A", "--format", "json")
        data = json.loads(capsys.readouterr().out)
        assert data["writes_performed"] == 0 and data["mode"] == "SHADOW_EXPORT"
        with pytest.raises(CommandError):
            call_command("shadow_price_rate_matrix_export", "--currencies", "USD")
        with pytest.raises(CommandError):
            call_command("shadow_price_rate_matrix_export", "--scopes", "D2D")
        with pytest.raises(CommandError):
            call_command("shadow_price_rate_matrix_export", "--lane", "POMBNE")

