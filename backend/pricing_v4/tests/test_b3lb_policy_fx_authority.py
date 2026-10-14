"""Pilot Gate B3L-B: commercial authority controls (FX source policy, GST authority, policy loader).

Every value here is synthetic test data. No real FX rate, tariff, or commercial policy appears, and
nothing here is approved for any purpose.
"""

import json
from datetime import date, timedelta
from decimal import Decimal as D
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError

from core.fx_market_models import FxMarketRate
from pricing_v4.commercial_models import CommercialTermsPolicy
from pricing_v4.services import commercial_policy_loader as loader
from pricing_v4.services.commercial_policy import (
    AmbiguousCommercialPolicyError,
    MissingCommercialPolicyError,
    require_standard_gst_rate,
    require_unique_commercial_terms_policy,
    resolve_commercial_terms_policy,
)
from pricing_v4.services.fx_resolver import (
    AmbiguousFxSourceError,
    MissingFxMarketRateError,
    StaleFxMarketRateError,
    resolve_market_fx_pair,
)
from quotes.tax_policy import PNG_GST_REFERENCE_RATE

QUOTE = date(2030, 6, 14)  # a Friday
BSP, MANUAL = "bsp_html", "MANUAL"


def make_policy(code="SYNTH-POLICY", valid_from=date(2030, 1, 1), valid_until=None, **overrides):
    values = {
        "policy_code": code, "valid_from": valid_from, "valid_until": valid_until, "margin_percent": D("16.67"),
        "margin_method": "TARGET_GROSS_MARGIN", "import_caf_percent": D("5.00"), "export_caf_percent": D("10.00"),
        "gst_standard_percent": D("10.00"), "caf_method": "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
        "fx_side_convention": "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL",
        "fx_max_age_days": 5, "fx_primary_source": BSP, "fx_fallback_source": MANUAL, "is_active": True,
    }
    values.update(overrides)
    return CommercialTermsPolicy.objects.create(**values)


def make_rate(source=BSP, days_old=0, base="AUD", quote="PGK", buy="2.60", sell="2.70", on=QUOTE):
    effective = on - timedelta(days=days_old)
    return FxMarketRate.objects.create(
        base_currency=base, quote_currency=quote, effective_date=effective, tt_buy_rate=D(buy),
        tt_sell_rate=D(sell), mid_rate=(D(buy) + D(sell)) / 2, source=source,
    )


@pytest.fixture
def policy(db):
    CommercialTermsPolicy.objects.all().delete()  # a migration seeds the launch policy
    FxMarketRate.objects.all().delete()
    return make_policy()


# --------------------------------------------------------------------------- FX source policy


@pytest.mark.django_db
class TestFxSourcePolicy:
    def test_legacy_policy_keeps_the_long_standing_resolution(self, db):
        CommercialTermsPolicy.objects.all().delete()
        make_policy(code="LEGACY", caf_method="LEGACY_RATE_ADJUSTMENT", fx_side_convention="LEGACY_COST_AT_TT_BUY",
                    fx_max_age_days=None, fx_primary_source="", fx_fallback_source="")
        make_rate(source="ANY-SOURCE", days_old=90)
        pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert pair.source == "ANY-SOURCE"
        assert pair.source_role == "" and pair.max_age_days is None

    @pytest.mark.parametrize(("days_old", "ok"), [(0, True), (4, True), (5, True), (6, False), (30, False)])
    def test_five_day_maximum_age_edge(self, policy, days_old, ok):
        make_rate(days_old=days_old)
        if ok:
            pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
            assert pair.age_days == days_old and pair.max_age_days == 5
            assert pair.policy_code == "SYNTH-POLICY"
        else:
            with pytest.raises(StaleFxMarketRateError, match="days old"):
                resolve_market_fx_pair("AUD", "PGK", QUOTE)

    def test_weekend_and_holiday_reuse_the_latest_rate_within_the_limit(self, policy):
        make_rate(days_old=0, on=date(2030, 6, 14))  # Friday
        for weekend_quote in (date(2030, 6, 15), date(2030, 6, 16), date(2030, 6, 17)):
            assert resolve_market_fx_pair("AUD", "PGK", weekend_quote).effective_date == date(2030, 6, 14)
        with pytest.raises(StaleFxMarketRateError):
            resolve_market_fx_pair("AUD", "PGK", date(2030, 6, 20))  # six days after

    def test_future_rates_are_never_used(self, policy):
        make_rate(days_old=-1)  # effective tomorrow
        with pytest.raises(MissingFxMarketRateError):
            resolve_market_fx_pair("AUD", "PGK", QUOTE)

    def test_primary_source_wins_over_a_newer_manual_rate_while_suitable(self, policy):
        make_rate(source=BSP, days_old=3, buy="2.60", sell="2.70")
        make_rate(source=MANUAL, days_old=0, buy="9.00", sell="9.50")
        pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert (pair.source, pair.source_role, pair.tt_sell) == (BSP, "PRIMARY", D("2.70"))

    def test_manual_is_used_only_when_primary_is_stale_or_absent(self, policy):
        make_rate(source=BSP, days_old=6)
        make_rate(source=MANUAL, days_old=1, buy="2.65", sell="2.75")
        pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert (pair.source, pair.source_role) == (MANUAL, "FALLBACK")
        FxMarketRate.objects.filter(source=BSP).delete()
        assert resolve_market_fx_pair("AUD", "PGK", QUOTE).source_role == "FALLBACK"

    def test_bsp_and_manual_on_the_same_date_is_resolved_by_policy_not_ambiguity(self, policy):
        make_rate(source=BSP, days_old=0, buy="2.60", sell="2.70")
        make_rate(source=MANUAL, days_old=0, buy="2.61", sell="2.71")
        pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert (pair.source, pair.tt_buy, pair.tt_sell) == (BSP, D("2.60"), D("2.70"))

    def test_unlisted_sources_are_ignored_and_the_gap_fails_closed(self, policy):
        make_rate(source="SOMEONE-ELSE", days_old=0)
        with pytest.raises(MissingFxMarketRateError, match="policy sources"):
            resolve_market_fx_pair("AUD", "PGK", QUOTE)

    def test_stale_primary_and_stale_fallback_fail_closed_with_both_named(self, policy):
        make_rate(source=BSP, days_old=7)
        make_rate(source=MANUAL, days_old=8)
        with pytest.raises(StaleFxMarketRateError) as caught:
            resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert "PRIMARY" in str(caught.value) and "FALLBACK" in str(caught.value)

    def test_direct_and_inverse_on_the_same_date_from_one_source_is_ambiguous(self, policy):
        make_rate(source=BSP, base="AUD", quote="PGK")
        make_rate(source=BSP, base="PGK", quote="AUD", buy="0.37", sell="0.38")
        with pytest.raises(AmbiguousFxSourceError):
            resolve_market_fx_pair("AUD", "PGK", QUOTE)

    def test_inverse_pair_swaps_sides_and_never_silently_keeps_them(self, policy):
        make_rate(source=BSP, base="PGK", quote="AUD", buy="0.37", sell="0.40")
        pair = resolve_market_fx_pair("AUD", "PGK", QUOTE)
        assert pair.is_inverse
        # inverse TT BUY = 1 / stored TT SELL ; inverse TT SELL = 1 / stored TT BUY
        assert pair.tt_buy == (D("1") / D("0.40")).quantize(D("0.00000001"))
        assert pair.tt_sell == (D("1") / D("0.37")).quantize(D("0.00000001"))
        assert pair.tt_sell > pair.tt_buy
        assert pair.source_role == "PRIMARY"

    def test_cross_currency_applies_the_policy_to_each_leg(self, policy):
        make_rate(base="AUD", quote="PGK", days_old=1)
        make_rate(base="USD", quote="PGK", days_old=1, buy="3.60", sell="3.70")
        assert resolve_market_fx_pair("AUD", "USD", QUOTE).is_cross
        FxMarketRate.objects.filter(base_currency="USD").update(effective_date=QUOTE - timedelta(days=9))
        with pytest.raises(StaleFxMarketRateError):
            resolve_market_fx_pair("AUD", "USD", QUOTE)

    def test_explicit_source_bypasses_priority_but_not_the_age_limit(self, policy):
        make_rate(source="OTHER", days_old=2)
        assert resolve_market_fx_pair("AUD", "PGK", QUOTE, source="OTHER").source == "OTHER"
        FxMarketRate.objects.filter(source="OTHER").update(effective_date=QUOTE - timedelta(days=9))
        with pytest.raises(StaleFxMarketRateError):
            resolve_market_fx_pair("AUD", "PGK", QUOTE, source="OTHER")

    def test_identity_needs_no_rate(self, policy):
        assert resolve_market_fx_pair("PGK", "PGK", QUOTE).is_identity


# --------------------------------------------------------------------------- policy resolution and GST authority


@pytest.mark.django_db
class TestPolicyAndGstAuthority:
    def test_reference_constant_matches_the_seeded_launch_policy(self, db):
        seeded = CommercialTermsPolicy.objects.get(policy_code="LAUNCH-POLICY-2026")
        assert seeded.gst_standard_rate == PNG_GST_REFERENCE_RATE

    def test_standard_rate_comes_from_the_resolved_policy(self, policy):
        CommercialTermsPolicy.objects.update(gst_standard_percent=D("12.50"))
        assert require_standard_gst_rate(QUOTE) == D("0.125")

    def test_missing_policy_fails_closed(self, db):
        CommercialTermsPolicy.objects.all().delete()
        with pytest.raises(MissingCommercialPolicyError):
            require_standard_gst_rate(QUOTE)

    def test_ambiguous_policy_fails_closed_though_the_older_resolver_picks_the_newest(self, policy):
        make_policy(code="SYNTH-POLICY-2", valid_from=date(2030, 3, 1))
        assert resolve_commercial_terms_policy(QUOTE).policy_code == "SYNTH-POLICY-2"  # long-standing contract
        with pytest.raises(AmbiguousCommercialPolicyError):
            require_unique_commercial_terms_policy(QUOTE)
        with pytest.raises(AmbiguousCommercialPolicyError):
            require_standard_gst_rate(QUOTE)

    def test_incomplete_policy_fails_closed(self, policy, monkeypatch):
        monkeypatch.setattr(CommercialTermsPolicy, "gst_standard_rate", property(lambda self: None))
        with pytest.raises(MissingCommercialPolicyError, match="gst_standard_percent"):
            require_standard_gst_rate(QUOTE)

    def test_inactive_and_expired_policies_do_not_count(self, policy):
        make_policy(code="OLD", valid_from=date(2029, 1, 1), valid_until=date(2029, 12, 31))
        make_policy(code="OFF", is_active=False)
        assert require_unique_commercial_terms_policy(QUOTE).policy_code == "SYNTH-POLICY"

    def test_fx_policy_fields_are_validated(self, db):
        row = CommercialTermsPolicy(
            policy_code="BAD", valid_from=date(2030, 1, 1), gst_standard_percent=D("10"),
            fx_fallback_source=MANUAL, fx_primary_source="",
        )
        with pytest.raises(Exception, match="primary"):
            row.full_clean()
        row.fx_primary_source = MANUAL
        with pytest.raises(Exception, match="differ"):
            row.full_clean()


# --------------------------------------------------------------------------- policy loader


def manifest(**policy_overrides):
    policy = {
        "policy_code": "PILOT-POLICY-SYNTH", "valid_from": "2030-10-11", "margin_percent": "16.67",
        "margin_method": "TARGET_GROSS_MARGIN", "import_caf_percent": "5.00", "export_caf_percent": "10.00",
        "gst_standard_percent": "10.00", "caf_method": "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT",
        "fx_side_convention": "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL",
        "fx_max_age_days": 5, "fx_primary_source": BSP, "fx_fallback_source": MANUAL,
    }
    policy.update(policy_overrides)
    return {
        "manifest_version": 1, "policy": policy,
        "supersedes": {"policy_code": "OLD-POLICY", "expected_valid_until": None, "set_valid_until": "2030-10-10"},
        "evidence": "Synthetic approval record.",
    }


def text_of(data):
    return json.dumps(data, indent=1)


def snapshot():
    return list(CommercialTermsPolicy.objects.order_by("policy_code").values())


@pytest.fixture
def old_policy(db):
    CommercialTermsPolicy.objects.all().delete()
    return make_policy(
        code="OLD-POLICY", valid_from=date(2030, 1, 1), margin_percent=D("20.00"),
        margin_method="MARKUP_ON_COST", caf_method="LEGACY_RATE_ADJUSTMENT",
        fx_side_convention="LEGACY_COST_AT_TT_BUY", fx_max_age_days=None, fx_primary_source="", fx_fallback_source="",
    )


@pytest.fixture
def operator(db):
    return get_user_model().objects.create_user(username="synthetic-policy-operator", password="x")


def apply(data, operator, **kwargs):
    text = text_of(data)
    sha = kwargs.pop("reviewed_sha256", loader.plan_policy_text(text).manifest_sha256)
    return loader.apply_policy_text(text, operator=operator, reviewed_sha256=sha, **kwargs)


@pytest.mark.django_db
class TestPolicyLoader:
    def test_dry_run_shows_the_supersede_and_writes_nothing(self, old_policy):
        before = snapshot()
        plan = loader.plan_policy_text(text_of(manifest()))
        assert plan.ready
        assert (plan.action, plan.supersede_action) == ("CREATE", "SUPERSEDE")
        assert any("open-ended -> 2030-10-10" in d for d in plan.details)
        assert "Writes performed: 0" in plan.render_text()
        assert snapshot() == before

    def test_apply_ends_the_old_row_and_starts_the_new_one_with_no_overlap(self, old_policy, operator):
        plan = apply(manifest(), operator)
        assert plan.applied == {"operator": "synthetic-policy-operator", "rows_written": 2}
        old = CommercialTermsPolicy.objects.get(policy_code="OLD-POLICY")
        new = CommercialTermsPolicy.objects.get(policy_code="PILOT-POLICY-SYNTH")
        assert old.valid_until == date(2030, 10, 10)
        assert new.valid_from == date(2030, 10, 11) and new.valid_until is None
        assert (new.caf_method, new.fx_side_convention, new.fx_max_age_days) == (
            "TO_PGK_RATE_REDUCTION_FROM_PGK_UPLIFT", "FCY_TO_PGK_AT_TT_BUY_PGK_TO_FCY_AT_TT_SELL", 5)
        assert (new.margin_method, new.margin_percent, new.import_caf_percent) == ("TARGET_GROSS_MARGIN", D("16.67"), D("5.00"))
        # Exactly one policy resolves on every date, and the boundary falls where intended.
        assert require_unique_commercial_terms_policy(date(2030, 10, 10)).policy_code == "OLD-POLICY"
        assert require_unique_commercial_terms_policy(date(2030, 10, 11)).policy_code == "PILOT-POLICY-SYNTH"
        assert require_unique_commercial_terms_policy(date(2031, 6, 1)).policy_code == "PILOT-POLICY-SYNTH"

    def test_the_old_row_is_not_otherwise_edited(self, old_policy, operator):
        before = CommercialTermsPolicy.objects.filter(policy_code="OLD-POLICY").values().get()
        apply(manifest(), operator)
        after = CommercialTermsPolicy.objects.filter(policy_code="OLD-POLICY").values().get()
        assert {k: v for k, v in after.items() if k != "valid_until"} == {k: v for k, v in before.items() if k != "valid_until"}

    def test_second_apply_writes_nothing(self, old_policy, operator):
        apply(manifest(), operator)
        before = snapshot()
        plan = apply(manifest(), operator)
        assert (plan.action, plan.supersede_action) == ("REUSE", "ALREADY_ENDED")
        assert plan.applied["rows_written"] == 0
        assert snapshot() == before

    def test_refuses_a_hash_that_does_not_match(self, old_policy, operator):
        before = snapshot()
        with pytest.raises(loader.PolicyApplyError, match="does not match"):
            apply(manifest(), operator, reviewed_sha256="0" * 64)
        assert snapshot() == before

    def test_refuses_an_inactive_operator(self, old_policy, operator):
        operator.is_active = False
        before = snapshot()
        with pytest.raises(loader.PolicyApplyError, match="active operator"):
            apply(manifest(), operator)
        assert snapshot() == before

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda m: m["policy"].update(valid_from="2030-10-12"),  # gap
            lambda m: m["policy"].update(valid_from="2030-10-10"),  # overlap
            lambda m: m["supersedes"].update(expected_valid_until="2031-01-01"),
            lambda m: m["supersedes"].update(policy_code="NO-SUCH-POLICY"),
            lambda m: m["policy"].update(margin_percent="100.00"),
            lambda m: m["policy"].update(fx_primary_source="", fx_fallback_source=MANUAL),
        ],
    )
    def test_invalid_plans_are_not_ready_and_write_nothing(self, old_policy, operator, mutate):
        data = manifest()
        mutate(data)
        before = snapshot()
        plan = apply(data, operator)
        assert not plan.ready
        assert plan.applied is None
        assert snapshot() == before

    def test_a_third_open_ended_policy_would_overlap_and_blocks(self, old_policy, operator):
        make_policy(code="RIVAL", valid_from=date(2030, 2, 1))
        before = snapshot()
        plan = apply(manifest(), operator)
        assert not plan.ready
        assert any("RIVAL" in reason for reason in plan.reasons)
        assert snapshot() == before

    def test_existing_code_with_different_values_conflicts_and_is_not_edited(self, old_policy, operator):
        apply(manifest(), operator)
        before = snapshot()
        changed = manifest(import_caf_percent="6.00")
        plan = apply(changed, operator)
        assert not plan.ready and plan.action == "CONFLICT"
        assert snapshot() == before

    def test_failure_part_way_rolls_back_the_supersede(self, old_policy, operator, monkeypatch):
        real_save = CommercialTermsPolicy.save

        def explode(self, *args, **kwargs):
            if kwargs.get("force_insert"):
                raise RuntimeError("synthetic failure while inserting the new policy")
            return real_save(self, *args, **kwargs)

        monkeypatch.setattr(CommercialTermsPolicy, "save", explode)
        before = snapshot()
        with pytest.raises(RuntimeError):
            apply(manifest(), operator)
        assert snapshot() == before
        assert CommercialTermsPolicy.objects.get(policy_code="OLD-POLICY").valid_until is None

    def test_strict_manifest(self, old_policy):
        for text in ("{not json", '{"manifest_version": 1}', text_of({**manifest(), "extra": 1})):
            assert not loader.plan_policy_text(text).ready
        bad = manifest()
        bad["policy"]["margin_percent"] = 16.67  # a JSON number, not a decimal string
        assert not loader.plan_policy_text(text_of(bad)).ready


@pytest.mark.django_db
class TestPolicyCommand:
    def _write(self, tmp_path, data):
        path = tmp_path / "policy.json"
        path.write_text(text_of(data), encoding="utf-8")
        return str(path)

    def test_dry_run_is_the_default(self, old_policy, tmp_path):
        before = snapshot()
        out = StringIO()
        call_command("load_commercial_terms_policy", self._write(tmp_path, manifest()), stdout=out)
        assert "Mode: DRY RUN" in out.getvalue() and "Writes performed: 0" in out.getvalue()
        assert snapshot() == before

    def test_apply_requires_operator_and_reviewed_hash(self, old_policy, operator, tmp_path):
        path = self._write(tmp_path, manifest())
        with pytest.raises(CommandError, match="requires --operator"):
            call_command("load_commercial_terms_policy", path, apply=True)
        with pytest.raises(CommandError, match="only valid with --apply"):
            call_command("load_commercial_terms_policy", path, operator="synthetic-policy-operator")
        with pytest.raises(CommandError, match="No active user"):
            call_command("load_commercial_terms_policy", path, apply=True, operator="nobody", reviewed_sha256="0" * 64)

    def test_apply_with_the_reviewed_hash(self, old_policy, operator, tmp_path):
        path = self._write(tmp_path, manifest())
        dry = StringIO()
        call_command("load_commercial_terms_policy", path, format="json", stdout=dry)
        sha = json.loads(dry.getvalue())["manifest_sha256"]
        out = StringIO()
        call_command("load_commercial_terms_policy", path, apply=True, operator="synthetic-policy-operator",
                     reviewed_sha256=sha, stdout=out)
        assert "Applied by synthetic-policy-operator: 2 row(s) written." in out.getvalue()
