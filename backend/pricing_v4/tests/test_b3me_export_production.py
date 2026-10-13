"""Pilot Gate B3M-E: Rate Matrix export pricing wired into production behind a feature flag.

The tariffs under test are the controlled repository manifests loaded with the real loaders; FX rates
and legacy rows are test data (the same world as the B3M-C shadow tests). The locked commercial rules
are the Commercial Manager's of 2026-10-12.
"""

# ruff: noqa: F811  (the B3M-C world fixtures are imported by name and requested as arguments)

import uuid
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.dataclasses import LocationRef, Piece, QuoteInput, ShipmentDetails
from core.fx_market_models import FxMarketRate
from pricing_v4.adapter import PricingServiceV4Adapter
from pricing_v4.commercial_models import CommercialProductCode, CommercialTermsPolicy
from pricing_v4.engine.export_engine import ExportPricingEngine, PaymentTerm
from pricing_v4.models import Carrier, ExportCOGS, ExportSellRate, LocalCOGSRate, LocalSellRate
from pricing_v4.services import rate_matrix_resolver as resolver
from pricing_v4.services.export_pilot_components import (
    PILOT_EXPORT_CODES,
    ExportComponentError,
    apply_export_components,
    plan_export_components,
)
from pricing_v4.services.fx_resolver import (
    AmbiguousFxSourceError,
    FxResolutionError,
    MissingFxMarketRateError,
    StaleFxMarketRateError,
)
from pricing_v4.services.rate_matrix_export_pricing import (
    FLAG_SETTING,
    RateMatrixExportPricingEngine,
    RateMatrixExportPricingError,
    rate_matrix_export_enabled,
    select_rate_matrix_export_pricing,
)
from pricing_v4.tests.test_b3mc_export_shadow import (  # noqa: F401  (fixtures and helpers of the B3M-C world)
    QUOTE_DATE,
    TT_BUY,
    _fresh_export_code_cache,
    aud,
    cents,
    loaded,
    world,
)
from services.models import ServiceComponent

PGK_LANES = (("POM", "BNE"), ("POM", "SYD"))
WEIGHTS = tuple(D(w) for w in ("30", "45", "100", "200", "500", "999", "1000", "1001"))


def in_scope(**overrides):
    base = dict(
        shipment_type="EXPORT", mode="AIR", origin="POM", destination="BNE", service_scope="D2A",
        payment_term="PREPAID", quote_currency="PGK", commodity_code="GCR", is_dangerous_goods=False,
    )
    base.update(overrides)
    return select_rate_matrix_export_pricing(**base)


@pytest.fixture
def flag_on(settings):
    setattr(settings, FLAG_SETTING, True)


@pytest.fixture
def twins(loaded):
    plan = plan_export_components()
    apply_export_components(operator=loaded["user"], reviewed_sha256=plan.combined_sha256)
    return loaded


def engine(*, destination="BNE", weight="100", term=PaymentTerm.PREPAID, currency="PGK", **kw):
    return RateMatrixExportPricingEngine(
        quote_date=kw.pop("quote_date", QUOTE_DATE), origin="POM", destination=destination,
        chargeable_weight_kg=D(weight), payment_term=term, quote_currency=currency,
        caf_rate=kw.pop("caf_rate", D("0.10")), policy_code="TEST-LOCKED-2026-10-12", **kw,
    )


def price(*, scope="D2A", **kwargs):
    eng = engine(**kwargs)
    ids = ExportPricingEngine.get_product_codes(
        is_dg=False, service_scope=scope, origin="POM", destination=kwargs.get("destination", "BNE"),
        payment_term=eng.payment_term.value, quote_date=eng.quote_date,
    )
    return eng.calculate_quote(ids, service_scope=scope)


def lines(result):
    return {item.product_code: item for item in result.line_items}


def quote_input(*, destination="BNE", scope="D2A", term="PREPAID", weight="100", currency=None,
                dims=(50, 50, 50), **extra):
    pom = LocationRef(id=uuid.uuid4(), code="POM", name="Port Moresby", country_code="PG", currency_code="PGK")
    dest = LocationRef(id=uuid.uuid4(), code=destination, name=destination, country_code="AU", currency_code="AUD")
    shipment = ShipmentDetails(
        origin_location=pom, destination_location=dest, service_scope=scope, payment_term=term, incoterm="EXW",
        shipment_type="EXPORT", mode="AIR", is_dangerous_goods=False, commodity_code="GCR",
        pieces=[Piece(pieces=1, length_cm=D(dims[0]), width_cm=D(dims[1]), height_cm=D(dims[2]),
                      gross_weight_kg=D(weight))],
    )
    return QuoteInput(
        customer_id=uuid.uuid4(), contact_id=uuid.uuid4(), quote_date=QUOTE_DATE,
        output_currency=currency or ("PGK" if term == "PREPAID" else "AUD"), shipment=shipment, **extra,
    )


def adapter_lines(**kwargs):
    adapter = PricingServiceV4Adapter(quote_input(**kwargs))
    charges = adapter.calculate_charges()
    return adapter, charges, {line.service_component_code: line for line in charges.lines}


# --------------------------------------------------------------------------- flag and scope guard


class TestFlagAndScopeGuard:
    def test_the_flag_is_off_by_default(self, settings):
        assert FLAG_SETTING == "RATE_MATRIX_EXPORT_PRICING_ENABLED"
        assert rate_matrix_export_enabled() is False
        assert in_scope().reason == "FLAG_OFF" and in_scope().selected is False

    @pytest.mark.parametrize("value", ["true", "1", 1, "yes", None, "True"])
    def test_only_a_real_boolean_true_enables_the_path(self, settings, value):
        setattr(settings, FLAG_SETTING, value)
        assert rate_matrix_export_enabled() is False

    def test_the_settings_module_enables_only_on_the_literal_true(self):
        import pathlib

        source = (pathlib.Path(__file__).resolve().parents[2] / "rate_engine" / "settings.py").read_text(
            encoding="utf-8"
        )
        assert "os.environ.get('RATE_MATRIX_EXPORT_PRICING_ENABLED', '').strip().lower() == 'true'" in source

    def test_every_pilot_lane_scope_and_term_is_selected(self, flag_on):
        for destination in ("BNE", "SYD"):
            for scope in ("A2A", "D2A"):
                assert in_scope(destination=destination, service_scope=scope).selected
        assert in_scope(payment_term="COLLECT", quote_currency="AUD").selected

    @pytest.mark.parametrize("overrides, text", [
        ({"origin": "BNE", "destination": "POM"}, "not a Pilot lane"),          # reverse direction
        ({"destination": "LAE"}, "not a Pilot lane"),
        ({"destination": "NAN"}, "not a Pilot lane"),
        ({"origin": "LAE", "destination": "BNE"}, "not a Pilot lane"),
        ({"shipment_type": "IMPORT"}, "not EXPORT"),
        ({"shipment_type": "DOMESTIC"}, "not EXPORT"),
        ({"mode": "SEA"}, "not AIR"),
        ({"service_scope": "D2D"}, "not a Pilot scope"),
        ({"service_scope": "A2D"}, "not a Pilot scope"),
        ({"service_scope": None}, "not a Pilot scope"),
        ({"payment_term": "COLLECT", "quote_currency": "PGK"}, "not a Pilot combination"),
        ({"payment_term": "PREPAID", "quote_currency": "AUD"}, "not a Pilot combination"),
        ({"payment_term": "COLLECT", "quote_currency": "USD"}, "not a Pilot combination"),
        ({"commodity_code": "DGR"}, "not General Cargo"),
        ({"commodity_code": "PER"}, "not General Cargo"),
        ({"is_dangerous_goods": True}, "dangerous goods"),
        ({"spot_envelope_id": uuid.uuid4()}, "SPOT"),
        ({"agent_id": 1}, "preferred agent or carrier"),
        ({"carrier_id": 1}, "preferred agent or carrier"),
        ({"buy_currency": "AUD"}, "non-PGK BUY currency"),
        ({"has_overrides": True}, "manual overrides"),
        ({"has_spot_rates": True}, "manual overrides"),
    ])
    def test_anything_outside_the_exact_pilot_scope_is_legacy(self, flag_on, overrides, text):
        selection = in_scope(**overrides)
        assert selection.selected is False and selection.flag_enabled is True
        assert selection.reason.startswith("OUT_OF_SCOPE") and text in selection.reason

    def test_engine_construction_refuses_a_lane_outside_the_pilot(self, loaded):
        for origin, destination in (("BNE", "POM"), ("POM", "LAE"), ("POM", "NAN")):
            with pytest.raises(RateMatrixExportPricingError) as caught:
                RateMatrixExportPricingEngine(
                    quote_date=QUOTE_DATE, origin=origin, destination=destination, chargeable_weight_kg=D(100),
                    payment_term=PaymentTerm.PREPAID, quote_currency="PGK", caf_rate=D("0.10"),
                )
            assert caught.value.code == "LANE_NOT_PILOT"

    def test_engine_construction_refuses_a_non_pilot_currency_pairing(self, loaded):
        for term, currency in ((PaymentTerm.PREPAID, "AUD"), (PaymentTerm.COLLECT, "PGK"), (PaymentTerm.COLLECT, "USD")):
            with pytest.raises(RateMatrixExportPricingError) as caught:
                engine(term=term, currency=currency)
            assert caught.value.code == "CURRENCY_NOT_PILOT"

    def test_reverse_direction_and_import_applicability_cannot_match(self, loaded):
        base = dict(rate_type=resolver.SELL, effective_date=QUOTE_DATE, product_code="EXP-FRT-AIR",
                    quote_currency="PGK", chargeable_weight=D(100))
        reverse = resolver.resolve(resolver.ResolutionContext(
            direction="EXPORT", origin_iata="BNE", destination_iata="POM", **base))
        as_import = resolver.resolve(resolver.ResolutionContext(
            direction="IMPORT", origin_iata="POM", destination_iata="BNE", **base))
        forward = resolver.resolve(resolver.ResolutionContext(
            direction="EXPORT", origin_iata="POM", destination_iata="BNE", **base))
        assert reverse.outcome == resolver.NO_MATCH and as_import.outcome == resolver.NO_MATCH
        assert forward.outcome == resolver.EXACT_MATCH


# --------------------------------------------------------------------------- twins


class TestServiceComponentTwins:
    def test_dry_run_plans_the_twelve_pilot_codes_without_writing(self, loaded):
        before = ServiceComponent.objects.count()
        plan = plan_export_components()
        assert [code for code, _p in plan.plans] == list(PILOT_EXPORT_CODES)
        assert plan.ready and plan.counts()["CREATE"] == 12 and plan.counts()["CONFLICT"] == 0
        assert ServiceComponent.objects.count() == before

    def test_apply_creates_exactly_the_missing_twins_and_is_idempotent(self, loaded):
        plan = plan_export_components()
        done = apply_export_components(operator=loaded["user"], reviewed_sha256=plan.combined_sha256)
        assert done.applied["rows_created"] == 12
        twins_now = ServiceComponent.objects.filter(code__in=PILOT_EXPORT_CODES)
        assert twins_now.count() == 12
        assert all(t.is_active and t.mode == "AIR" and t.audience == "BOTH" for t in twins_now)
        again = plan_export_components()
        assert again.counts() == {"CREATE": 0, "REUSE": 12, "CONFLICT": 0} and again.ready
        redo = apply_export_components(operator=loaded["user"], reviewed_sha256=again.combined_sha256)
        assert redo.applied["rows_created"] == 0
        assert ServiceComponent.objects.filter(code__in=PILOT_EXPORT_CODES).count() == 12

    def test_a_partial_set_creates_only_what_is_missing(self, twins):
        ServiceComponent.objects.filter(code="EXP-DOC").delete()
        plan = plan_export_components()
        assert plan.counts() == {"CREATE": 1, "REUSE": 11, "CONFLICT": 0}
        done = apply_export_components(operator=twins["user"], reviewed_sha256=plan.combined_sha256)
        assert done.applied["rows_created"] == 1

    def test_apply_requires_the_reviewed_hash_and_writes_nothing_otherwise(self, loaded):
        before = ServiceComponent.objects.count()
        with pytest.raises(ExportComponentError):
            apply_export_components(operator=loaded["user"], reviewed_sha256="0" * 64)
        assert ServiceComponent.objects.count() == before

    def test_a_conflicting_stored_twin_blocks_the_whole_set(self, twins):
        ServiceComponent.objects.filter(code="EXP-DOC").update(leg="DESTINATION")
        ServiceComponent.objects.filter(code="EXP-AWB").delete()
        plan = plan_export_components()
        assert not plan.ready and plan.counts()["CONFLICT"] == 1
        done = apply_export_components(operator=twins["user"], reviewed_sha256=plan.combined_sha256)
        assert done.applied is None  # refused as a whole
        assert not ServiceComponent.objects.filter(code="EXP-AWB").exists()

    def test_the_command_is_dry_run_by_default_and_requires_the_hash_to_apply(self, loaded, capsys):
        call_command("ensure_export_pilot_service_components")
        text = capsys.readouterr().out
        assert "DRY RUN" in text and "CREATE 12" in text and "Writes performed: 0" in text
        assert ServiceComponent.objects.filter(code__in=PILOT_EXPORT_CODES).count() == 0
        with pytest.raises(CommandError):
            call_command("ensure_export_pilot_service_components", "--apply")
        with pytest.raises(CommandError):
            call_command("ensure_export_pilot_service_components", "--operator", loaded["user"].username)
        digest = plan_export_components().combined_sha256
        call_command("ensure_export_pilot_service_components", "--apply", "--operator", loaded["user"].username,
                     "--reviewed-sha256", digest)
        assert "12 row(s) created" in capsys.readouterr().out
        call_command("ensure_export_pilot_service_components")
        assert "REUSE 12" in capsys.readouterr().out

    def test_a_missing_twin_fails_the_rate_matrix_quote_instead_of_dropping_the_line(self, twins, flag_on):
        ServiceComponent.objects.filter(code="EXP-DOC").delete()
        with pytest.raises(RateMatrixExportPricingError) as caught:
            adapter_lines()
        assert caught.value.code == "SERVICE_COMPONENT_MISSING" and "EXP-DOC" in caught.value.message


# --------------------------------------------------------------------------- production pricing


class TestProductionPricing:
    def test_pgk_prepaid_d2a_100kg_uses_the_approved_card(self, loaded):
        result = price()
        by = lines(result)
        assert by["EXP-FRT-AIR"].sell_amount == D("675.00")       # 6.75 x 100 (legacy row says 740.00)
        assert by["EXP-FRT-AIR"].cost_amount == D("590.00")       # BUY 5.90 x 100
        assert by["EXP-FRT-AIR"].gst_amount == D("0.00") and by["EXP-FRT-AIR"].gst_category == "export_service"
        assert by["EXP-DOC"].sell_amount == D("50.00") and by["EXP-DOC"].gst_amount == D("5.00")
        assert by["EXP-SCREEN"].cost_amount == D("52.00")         # 0.17 x 100 + 35
        assert by["EXP-BUILDUP"].cost_amount == D("30.00")        # tier 100-2000: 0.10 x 100 = 10, minimum 30
        assert result.currency == "PGK" and result.fx_applied is False
        assert result.audit_metadata["conversions"] == [] and result.fx_rate_used is None

    def test_pgk_needs_no_fx_and_no_caf(self, loaded):
        FxMarketRate.objects.all().delete()
        result = price(caf_rate=None)
        assert lines(result)["EXP-FRT-AIR"].sell_amount == D("675.00")
        assert not result.fx_applied and result.caf_rate is None

    def test_aud_collect_is_pgk_over_tt_buy_then_ten_percent_caf_with_no_margin(self, loaded):
        result = price(term=PaymentTerm.COLLECT, currency="AUD")
        frt = lines(result)["EXP-FRT-AIR"]
        assert frt.sell_amount == aud("675.00") == D("238.79")
        assert cents(D("675.00") / TT_BUY) == D("217.08")          # pure FX first, then the uplift
        assert frt.sell_currency == "AUD" and frt.cost_currency == "PGK" and frt.cost_amount == D("590.00")
        assert frt.sell_pgk == D("675.00") and frt.cost_pgk == D("590.00")
        assert frt.margin_applied is False and frt.fx_applied and frt.caf_applied
        # No margin: neither the policy margin nor a TT SELL divisor appears in any amount.
        assert frt.sell_amount != cents(aud("675.00") / (D("1") - D("0.1667")))
        convention = result.audit_metadata["commercial_convention"]
        assert convention["caf_method"] == "UPLIFT_AFTER_FX" and convention["margin_on_explicit_sell"] is False
        leg = result.audit_metadata["conversions"][0]["legs"][0]
        assert leg["side"] == "TT_BUY" and D(leg["rate"]) == TT_BUY and leg["source"] == "bsp_html"
        assert result.fx_rate_used == TT_BUY and result.caf_rate == D("0.10")

    def test_changing_the_policy_margin_changes_no_explicit_sell_amount(self, loaded):
        baseline = {c: l.sell_amount for c, l in lines(price(term=PaymentTerm.COLLECT, currency="AUD")).items()}
        CommercialTermsPolicy.objects.update(margin_percent=D("40.00"), margin_method="MARKUP_ON_COST")
        again = {c: l.sell_amount for c, l in lines(price(term=PaymentTerm.COLLECT, currency="AUD")).items()}
        assert again == baseline

    def test_aud_gst_is_on_the_converted_amount(self, loaded):
        by = lines(price(term=PaymentTerm.COLLECT, currency="AUD"))
        doc = by["EXP-DOC"]
        assert doc.sell_amount == aud("50.00")
        assert doc.gst_amount == cents(doc.sell_amount * D("0.10")) and doc.gst_rate == D("0.10")
        assert by["EXP-FRT-AIR"].gst_amount == D("0.00")
        assert doc.sell_pgk == D("50.00") and doc.sell_pgk_incl_gst == D("55.00")

    def test_no_legacy_rate_table_is_consulted(self, loaded):
        baseline = {c: (l.sell_amount, l.cost_amount) for c, l in lines(price()).items()}
        ExportCOGS.objects.all().delete()
        ExportSellRate.objects.all().delete()
        LocalCOGSRate.objects.all().delete()
        LocalSellRate.objects.all().delete()
        assert {c: (l.sell_amount, l.cost_amount) for c, l in lines(price()).items()} == baseline

    def test_a_missing_rate_matrix_sell_is_a_visible_missing_line_not_a_legacy_fallback(self, loaded):
        from pricing_v4.rate_matrix_models import RateLine

        RateLine.objects.filter(sheet__rate_type="SELL", product_code__code="EXP-AGENCY").delete()
        by = lines(price())
        assert by["EXP-AGENCY"].is_rate_missing and by["EXP-AGENCY"].sell_amount == D("0")
        assert LocalSellRate.objects.filter(product_code__code="EXP-AGENCY").exists()  # legacy has it; not used

    @pytest.mark.parametrize("destination", ["BNE", "SYD"])
    @pytest.mark.parametrize("weight", ["30", "45", "100", "200", "500", "999", "1000", "1001"])
    def test_freight_follows_the_card_at_every_pilot_weight(self, loaded, destination, weight):
        card = {"BNE": [(0, "7.20"), (45, "7.20"), (100, "6.75"), (200, "6.50"), (500, "6.15")],
                "SYD": [(0, "9.15"), (45, "9.15"), (100, "8.60"), (200, "8.20"), (500, "7.70")]}[destination]
        rate = [r for lower, r in card if D(weight) >= lower][-1]
        expected = max(D("180.00"), cents(D(rate) * D(weight)))
        assert lines(price(destination=destination, weight=weight))["EXP-FRT-AIR"].sell_amount == expected

    def test_a2a_omits_the_origin_services_and_d2a_adds_them(self, loaded):
        a2a = set(lines(price(scope="A2A")))
        d2a = set(lines(price(scope="D2A")))
        assert {"EXP-CLEAR", "EXP-AGENCY", "EXP-BUILDUP", "EXP-PICKUP", "EXP-FSC-PICKUP"} <= d2a - a2a

    def test_pickup_cap_and_dependent_fsc(self, loaded):
        by = lines(price(weight="1001"))
        assert by["EXP-PICKUP"].sell_amount == D("500.00")            # 1.50 x 1001 capped at 500
        assert by["EXP-FSC-PICKUP"].sell_amount == D("50.00")         # 10% of the capped base
        small = lines(price(weight="30"))
        assert small["EXP-PICKUP"].sell_amount == D("95.00")          # minimum applies
        assert small["EXP-FSC-PICKUP"].sell_amount == D("9.50")

    def test_aud_dependants_are_computed_in_pgk_then_converted(self, loaded):
        by = lines(price(weight="1001", term=PaymentTerm.COLLECT, currency="AUD"))
        assert by["EXP-PICKUP"].sell_amount == aud("500.00")
        assert by["EXP-FSC-PICKUP"].sell_amount == aud("50.00")       # not 10% of the converted amount

    def test_additive_security_flat_buy_and_sell(self, loaded):
        by = lines(price(weight="1001"))
        assert by["EXP-SCREEN"].sell_amount == cents(D("0.20") * D("1001") + D("45.00"))
        assert by["EXP-SCREEN"].cost_amount == cents(D("0.17") * D("1001") + D("35.00"))

    def test_buildup_tier_minimum_and_boundaries(self, loaded):
        assert lines(price(weight="30"))["EXP-BUILDUP"].cost_amount == D("0.00")       # below 100 kg: no charge
        assert lines(price(weight="100"))["EXP-BUILDUP"].cost_amount == D("30.00")     # 10.00 -> minimum 30
        assert lines(price(weight="1001"))["EXP-BUILDUP"].cost_amount == D("100.10")   # 0.10 x 1001
        assert lines(price(weight="2000"))["EXP-BUILDUP"].cost_amount == D("200.00")   # lower tier at 2000
        assert lines(price(weight="2000.0001"))["EXP-BUILDUP"].cost_amount == D("300.00")  # upper tier

    def test_2000kg_uses_the_lower_tier_and_2000_0001kg_the_upper(self, loaded):
        for weight, rate in (("2000", "0.10"), ("2000.0001", "0.15")):
            tariff = resolver.resolve(resolver.ResolutionContext(
                rate_type=resolver.BUY, direction="EXPORT", effective_date=QUOTE_DATE, product_code="EXP-BUILDUP",
                origin_iata="POM", destination_iata="BNE",
                supplier_id=engine()._lane_supplier()[0], chargeable_weight=D(weight),
            )).tariff
            assert tariff.selected_tier.unit_rate == D(rate)

    @pytest.mark.parametrize("weight", ["100.00001", "2000.00005", "20.833333333", "0.00001"])
    def test_more_than_four_decimals_fails_closed_with_no_rounding(self, loaded, weight):
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price(weight=weight)
        assert "INVALID_CONTEXT" in caught.value.code and "decimal places" in caught.value.message

    @pytest.mark.parametrize("weight", ["100.1234", "100.12340", "30", "2000.0001"])
    def test_up_to_four_decimals_prices(self, loaded, weight):
        assert lines(price(weight=weight))["EXP-FRT-AIR"].sell_amount > 0


class TestFxFailClosed:
    def test_missing_fx_fails_aud_but_not_pgk(self, loaded):
        FxMarketRate.objects.all().delete()
        with pytest.raises(MissingFxMarketRateError):
            price(term=PaymentTerm.COLLECT, currency="AUD")
        assert price().currency == "PGK"

    def test_a_rate_up_to_five_days_old_is_usable_and_six_is_stale(self, loaded):
        assert price(term=PaymentTerm.COLLECT, currency="AUD",
                     quote_date=QUOTE_DATE + timedelta(days=5)) is not None
        with pytest.raises(StaleFxMarketRateError):
            price(term=PaymentTerm.COLLECT, currency="AUD", quote_date=QUOTE_DATE + timedelta(days=6))

    def test_the_five_day_cap_holds_even_if_the_policy_allows_longer(self, loaded):
        CommercialTermsPolicy.objects.update(fx_max_age_days=30)
        with pytest.raises(StaleFxMarketRateError):
            price(term=PaymentTerm.COLLECT, currency="AUD", quote_date=QUOTE_DATE + timedelta(days=6))

    def test_a_future_dated_rate_is_not_used(self, loaded):
        FxMarketRate.objects.update(effective_date=QUOTE_DATE + timedelta(days=1))
        with pytest.raises(FxResolutionError):
            price(term=PaymentTerm.COLLECT, currency="AUD")

    def test_an_inverse_only_rate_is_never_inferred(self, loaded):
        FxMarketRate.objects.all().delete()
        FxMarketRate.objects.create(
            base_currency="PGK", quote_currency="AUD", effective_date=QUOTE_DATE, source="bsp_html",
            tt_buy_rate=D("0.3216"), tt_sell_rate=D("0.3066"), mid_rate=D("0.3141"),
        )
        with pytest.raises((RateMatrixExportPricingError, FxResolutionError)) as caught:
            price(term=PaymentTerm.COLLECT, currency="AUD")
        assert isinstance(caught.value, FxResolutionError) or caught.value.code == "FX_NOT_DIRECT"

    def test_errors_shown_to_users_carry_no_technical_codes(self, loaded):
        for weight in ("100.00001",):
            with pytest.raises(RateMatrixExportPricingError) as caught:
                price(weight=weight)
            shown = str(caught.value)
            assert "EXP-" not in shown and "RESOLVER" not in shown and "decimal places" in shown
            assert "EXP-FRT-AIR" in caught.value.message or "INVALID_CONTEXT" in caught.value.code
        CommercialProductCode.objects.filter(code="EXP-DOC").update(is_active=False)
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price()
        assert "EXP-" not in str(caught.value) and "EXP-DOC" in caught.value.message

    def test_both_orientations_on_one_day_is_ambiguous(self, loaded):
        FxMarketRate.objects.create(
            base_currency="PGK", quote_currency="AUD", effective_date=QUOTE_DATE, source="bsp_html",
            tt_buy_rate=D("0.3216"), tt_sell_rate=D("0.3066"), mid_rate=D("0.3141"),
        )
        with pytest.raises(AmbiguousFxSourceError):
            price(term=PaymentTerm.COLLECT, currency="AUD")

    def test_missing_caf_fails_a_conversion_closed(self, loaded):
        from pricing_v4.services.commercial_policy import MissingCommercialPolicyError

        with pytest.raises(MissingCommercialPolicyError):
            price(term=PaymentTerm.COLLECT, currency="AUD", caf_rate=None)


class TestFailClosedTariffs:
    def test_no_supplier_buy_sheet_fails_closed(self, loaded):
        from pricing_v4.rate_matrix_models import RateSheet

        RateSheet.objects.filter(rate_type="BUY").update(is_active=False)
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price()
        assert caught.value.code == "SUPPLIER_NOT_SINGLE"

    def test_a_cpc_gst_mismatch_fails_closed(self, loaded):
        CommercialProductCode.objects.filter(code="EXP-DOC").update(gst_treatment="ZERO_RATED")
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price()
        assert caught.value.code == "GST_TREATMENT_MISMATCH"

    def test_a_missing_cpc_fails_closed(self, loaded):
        CommercialProductCode.objects.filter(code="EXP-DOC").update(is_active=False)
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price()
        assert caught.value.code == "CPC_MISSING"

    def test_a_non_pgk_tariff_fails_closed(self, loaded):
        from pricing_v4.rate_matrix_models import RateSheet

        RateSheet.objects.filter(rate_type="BUY", name__contains="terminal").update(currency_code="AUD")
        with pytest.raises(RateMatrixExportPricingError) as caught:
            price()
        assert caught.value.code == "TARIFF_CURRENCY_NOT_PGK"

    def test_a_non_pgk_sell_tariff_is_never_selected(self, loaded):
        from pricing_v4.rate_matrix_models import RateSheet

        RateSheet.objects.filter(rate_type="SELL", name__contains="origin charges").update(currency_code="AUD")
        by = lines(price())
        assert by["EXP-DOC"].is_rate_missing and by["EXP-DOC"].sell_amount == D("0")  # visible, no legacy fallback

    def test_the_engine_cannot_price_dangerous_goods_or_other_commodities(self, loaded):
        eng = engine()
        ids = ExportPricingEngine.get_product_codes(
            is_dg=False, service_scope="D2A", origin="POM", destination="BNE", payment_term="PREPAID",
            quote_date=QUOTE_DATE,
        )
        with pytest.raises(RateMatrixExportPricingError):
            eng.calculate_quote(ids, is_dg=True, service_scope="D2A")
        with pytest.raises(RateMatrixExportPricingError):
            eng.calculate_quote(ids, service_scope="D2A", commodity_code="DGR")
        with pytest.raises(RateMatrixExportPricingError):
            eng.calculate_quote(ids, service_scope="D2D")


# --------------------------------------------------------------------------- adapter integration


class TestAdapter:
    def test_flag_off_is_the_unchanged_legacy_path(self, twins, settings):
        setattr(settings, FLAG_SETTING, False)
        adapter, charges, by = adapter_lines()
        assert by["EXP-FRT-AIR"].sell_pgk == D("740.00")          # legacy export_sell_rates row
        assert "export_pricing_path" not in charges.totals.audit_metadata
        assert "rate_matrix_export" not in charges.totals.audit_metadata

    def test_flag_off_aud_collect_keeps_the_legacy_margin_and_tt_sell_convention(self, twins, settings):
        setattr(settings, FLAG_SETTING, False)
        _a, _c, by = adapter_lines(term="COLLECT")
        legacy_aud = by["EXP-FRT-AIR"].sell_fcy
        assert legacy_aud != aud("675.00") and legacy_aud != aud("740.00")

    def test_flag_on_pgk_prices_the_approved_card_with_provenance(self, twins, flag_on):
        adapter, charges, by = adapter_lines()
        frt = by["EXP-FRT-AIR"]
        assert frt.sell_pgk == D("675.00") and frt.cost_pgk == D("590.00")
        assert frt.gst_amount == D("0.00") and by["EXP-DOC"].gst_amount == D("5.00")
        meta = charges.totals.audit_metadata
        assert meta["export_pricing_path"] == {
            "path": "RATE_MATRIX_EXPORT", "flag": FLAG_SETTING, "flag_enabled": True, "reason": "IN_SCOPE",
        }
        provenance = meta["rate_matrix_export"]
        assert provenance["path"] == "RATE_MATRIX_EXPORT" and provenance["margin_applied_to_explicit_sell"] is False
        freight = [t for t in provenance["tariffs"] if t["product_code"] == "EXP-FRT-AIR" and t["side"] == "SELL"][0]
        assert freight["sheet"] and freight["sheet_version"] and freight["line_id"] and freight["rate_basis"] == "TIERED_WEIGHT"
        assert meta["fx_audit"]["applied"] is False

    def test_provenance_is_json_serialisable_and_persisted_with_the_quote_totals(self, twins, flag_on):
        import json

        from quotes.quote_result_contract import build_persisted_quote_total_metadata

        _a, charges, _by = adapter_lines(term="COLLECT")
        persisted = build_persisted_quote_total_metadata(charges.totals)
        stored = json.loads(json.dumps(persisted["audit_metadata_json"]))
        assert stored["rate_matrix_export"]["tariffs"] and stored["export_pricing_path"]["reason"] == "IN_SCOPE"
        assert stored["fx_audit"]["conversions"] and stored["fx_audit"]["conversions"][0]["legs"][0]["side"] == "TT_BUY"
        assert {t["side"] for t in stored["rate_matrix_export"]["tariffs"]} == {"BUY", "SELL"}

    def test_flag_on_aud_collect_applies_the_locked_rule_and_records_the_conversion(self, twins, flag_on):
        adapter, charges, by = adapter_lines(term="COLLECT")
        frt = by["EXP-FRT-AIR"]
        assert frt.sell_fcy == D("238.79") and frt.sell_fcy_currency == "AUD"
        assert frt.sell_pgk == D("675.00") and frt.cost_pgk == D("590.00")
        assert frt.sell_fcy_incl_gst == D("238.79")
        fx = charges.totals.audit_metadata["fx_audit"]
        assert fx["applied"] is True and fx["base_rate_type"] == "TT_BUY" and D(fx["base_rate"]) == TT_BUY
        assert fx["caf_operation"] == "UPLIFTED_AFTER_FX" and fx["fx_market_source"] == "bsp_html"
        assert charges.totals.total_sell_fcy == sum((l.sell_fcy for l in charges.lines), D("0.00"))
        assert charges.totals.total_sell_pgk == sum((l.sell_pgk for l in charges.lines), D("0.00"))

    def test_flag_on_out_of_scope_shipment_stays_on_the_legacy_engine(self, twins, flag_on):
        carrier = Carrier.objects.get(code="PX")
        adapter, charges, by = adapter_lines(carrier_id=carrier.id)
        assert by["EXP-FRT-AIR"].sell_pgk == D("740.00")
        path = charges.totals.audit_metadata["export_pricing_path"]
        assert path["path"] == "LEGACY_EXPORT" and path["reason"].startswith("OUT_OF_SCOPE")
        assert "rate_matrix_export" not in charges.totals.audit_metadata

    def test_flag_on_volumetric_weight_beyond_four_decimals_fails_closed(self, twins, flag_on):
        # 50 x 50 x 50 cm / 6000 = 20.8333... kg, which exceeds the weight of 10 kg actual.
        with pytest.raises(RateMatrixExportPricingError) as caught:
            adapter_lines(weight="10", dims=(50, 50, 50))
        assert "decimal places" in caught.value.message

    def test_flag_on_missing_fx_fails_the_aud_quote_and_does_not_fall_back(self, twins, flag_on):
        FxMarketRate.objects.all().delete()
        with pytest.raises(FxResolutionError):
            adapter_lines(term="COLLECT")

    def test_flag_on_pgk_quote_needs_no_fx(self, twins, flag_on):
        FxMarketRate.objects.all().delete()
        _a, _c, by = adapter_lines()
        assert by["EXP-FRT-AIR"].sell_pgk == D("675.00")

    def test_import_pricing_is_untouched_by_the_flag(self, flag_on):
        # Import shipments never reach the Rate Matrix export selection.
        selection = in_scope(shipment_type="IMPORT", origin="BNE", destination="POM")
        assert selection.selected is False
        from pricing_v4.engine import import_engine

        assert "rate_matrix_export_pricing" not in vars(import_engine)
        import inspect

        assert "rate_matrix_export" not in inspect.getsource(import_engine)

    def test_spot_is_untouched_by_the_flag(self, flag_on):
        assert in_scope(spot_envelope_id=uuid.uuid4()).selected is False

    def test_the_legacy_export_engine_source_is_not_modified_for_rate_matrix(self):
        import inspect

        from pricing_v4.engine import export_engine

        assert "rate_matrix" not in inspect.getsource(export_engine).lower()
