"""Target verification tests for Phase 2: Commercial Master Data & Policy.

Tests cover:
- CommercialProductCode
- CommercialChargeAlias
- FxMarketRate
- CommercialTermsPolicy
- GeoCorridorPolicy
- Model registration and exact table names
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from core.corridor_models import GeoCorridorPolicy, TransportMode
from core.fx_market_models import FxMarketRate
from core.geo_models import GeoLocation
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, models, transaction
from parties.party_models import PartyMaster

from pricing_v4.commercial_models import (
    CommercialChargeAlias,
    CommercialProductCode,
    CommercialTermsPolicy,
    normalize_alias_text,
)


@pytest.mark.django_db
class TestCommercialProductCode:
    def test_uuid_identity_and_unique_code(self):
        pc1 = CommercialProductCode.objects.create(
            code="FRT-AIR-STD",
            name="Air Freight Standard",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
            charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
        )
        assert isinstance(pc1.id, uuid.UUID)
        assert pc1.code == "FRT-AIR-STD"
        assert pc1.is_active is True

        with pytest.raises(IntegrityError):
            CommercialProductCode.objects.create(
                code="FRT-AIR-STD",
                name="Duplicate Code",
                category=CommercialProductCode.Category.FREIGHT,
                gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
                charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
            )

    def test_valid_categories(self):
        valid_cats = ["FREIGHT", "ORIGIN", "DESTINATION", "CLEARANCE", "SERVICE"]
        assert list(CommercialProductCode.Category.values) == valid_cats

        for cat in valid_cats:
            pc = CommercialProductCode(
                code=f"TEST-{cat}",
                name=f"Test {cat}",
                category=cat,
                gst_treatment=CommercialProductCode.GstTreatment.DOMESTIC_STANDARD,
                charge_basis_default=CommercialProductCode.ChargeBasis.FLAT,
            )
            pc.full_clean()
            pc.save()

    def test_gst_classification_values_and_ownership(self):
        expected_gst = [
            "FREIGHT_EXPORT",
            "FREIGHT_IMPORT",
            "DOMESTIC_STANDARD",
            "EXEMPT",
            "ZERO_RATED",
        ]
        assert list(CommercialProductCode.GstTreatment.values) == expected_gst

        # Labels must not contain hardcoded percentages; ProductCode owns classification, policy owns rate
        labels = dict(CommercialProductCode.GstTreatment.choices)
        assert labels["FREIGHT_EXPORT"] == "Freight Export"
        assert labels["FREIGHT_IMPORT"] == "Freight Import"
        assert labels["DOMESTIC_STANDARD"] == "Domestic Standard"
        assert labels["EXEMPT"] == "Exempt"
        assert labels["ZERO_RATED"] == "Zero Rated"
        for key, label in labels.items():
            assert "%" not in label, f"Label for {key} contains hardcoded percentage: '{label}'"

        pc = CommercialProductCode.objects.create(
            code="CUSTOMS-DOC",
            name="Customs Documentation",
            category=CommercialProductCode.Category.CLEARANCE,
            gst_treatment=CommercialProductCode.GstTreatment.DOMESTIC_STANDARD,
            charge_basis_default=CommercialProductCode.ChargeBasis.FLAT,
        )
        assert pc.gst_treatment == "DOMESTIC_STANDARD"

    def test_invalid_gst_treatment_rejected(self):
        pc = CommercialProductCode(
            code="INVALID-GST",
            name="Invalid GST",
            category=CommercialProductCode.Category.SERVICE,
            gst_treatment="NOT_A_VALID_GST",
            charge_basis_default=CommercialProductCode.ChargeBasis.FLAT,
        )
        with pytest.raises(ValidationError):
            pc.full_clean()

    def test_charge_basis_controlled_enum(self):
        expected_bases = [
            "FLAT",
            "PER_KG",
            "PER_CBM",
            "PER_UNIT",
            "TIERED_WEIGHT",
            "PERCENTAGE",
        ]
        assert list(CommercialProductCode.ChargeBasis.values) == expected_bases

        pc = CommercialProductCode(
            code="INVALID-BASIS",
            name="Invalid Basis",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
            charge_basis_default="UNCONTROLLED_BASIS",
        )
        with pytest.raises(ValidationError):
            pc.full_clean()

    def test_code_normalization_uppercase(self):
        pc = CommercialProductCode(
            code="  frt-sea-fcl  ",
            name="Ocean Freight FCL",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
            charge_basis_default=CommercialProductCode.ChargeBasis.PER_UNIT,
        )
        pc.clean()
        assert pc.code == "FRT-SEA-FCL"

    def test_inactive_product_code_remains_historically_identifiable(self):
        pc = CommercialProductCode.objects.create(
            code="HIST-OLD-AIR",
            name="Historical Air Linehaul",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
            charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
            is_active=False,
        )
        fetched = CommercialProductCode.objects.get(id=pc.id)
        assert fetched.is_active is False
        assert fetched.code == "HIST-OLD-AIR"

        # Unique constraint remains enforced even when is_active is False
        with pytest.raises(IntegrityError):
            CommercialProductCode.objects.create(
                code="HIST-OLD-AIR",
                name="New with same code",
                category=CommercialProductCode.Category.FREIGHT,
                gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
                charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
            )


@pytest.mark.django_db
class TestCommercialChargeAlias:
    @pytest.fixture
    def product_code(self):
        return CommercialProductCode.objects.create(
            code="SEC-FEE",
            name="Airline Security Fee",
            category=CommercialProductCode.Category.FREIGHT,
            gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_EXPORT,
            charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
        )

    @pytest.fixture
    def alt_product_code(self):
        return CommercialProductCode.objects.create(
            code="TER-HAND",
            name="Terminal Handling",
            category=CommercialProductCode.Category.DESTINATION,
            gst_treatment=CommercialProductCode.GstTreatment.DOMESTIC_STANDARD,
            charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
        )

    @pytest.fixture
    def carrier(self):
        return PartyMaster.objects.create(
            legal_name="Qantas Airways Limited",
            trade_name="Qantas",
            entity_type="AIRLINE",
            country_code="AU",
        )

    @pytest.fixture
    def other_carrier(self):
        return PartyMaster.objects.create(
            legal_name="Air Niugini Limited",
            trade_name="Air Niugini",
            entity_type="AIRLINE",
            country_code="PG",
        )

    def test_deterministic_normalization(self):
        assert normalize_alias_text("  security   fee  ") == "SECURITY FEE"
        assert normalize_alias_text("fsc\n\tsurcharge") == "FSC SURCHARGE"
        assert normalize_alias_text("") == ""

    def test_product_code_fk_and_protected_deletion(self, product_code):
        alias = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="SECURITY SURCHARGE",
            transport_mode=TransportMode.AIR,
        )
        assert alias.product_code == product_code
        assert isinstance(alias.id, uuid.UUID)

        # Deletion of product code is protected
        with pytest.raises(models.ProtectedError):
            product_code.delete()

    def test_transport_mode_scope(self, product_code):
        # Same raw_text under different transport modes may map independently
        alias_air = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="FUEL SURCHARGE",
            transport_mode=TransportMode.AIR,
        )
        alias_sea = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="FUEL SURCHARGE",
            transport_mode=TransportMode.SEA,
        )
        assert alias_air.id != alias_sea.id

        invalid_alias = CommercialChargeAlias(
            product_code=product_code,
            raw_text="FUEL SURCHARGE",
            transport_mode="RAIL",
        )
        with pytest.raises(ValidationError):
            invalid_alias.full_clean()

    def test_optional_carrier_party_scope(self, product_code, carrier):
        alias = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="TERMINAL SECURITY",
            transport_mode=TransportMode.AIR,
            carrier_party=carrier,
        )
        assert alias.carrier_party == carrier

        # Deletion of carrier is protected
        with pytest.raises(models.ProtectedError):
            carrier.delete()

    def test_global_alias_uniqueness_when_carrier_null(self, product_code, alt_product_code):
        CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="GLOBAL SECURITY",
            transport_mode=TransportMode.AIR,
            carrier_party=None,
        )

        # Attempt duplicate global alias via model clean
        dup_alias = CommercialChargeAlias(
            product_code=alt_product_code,
            raw_text="  global   security  ",
            transport_mode=TransportMode.AIR,
            carrier_party=None,
        )
        with pytest.raises(ValidationError):
            dup_alias.full_clean()

        # Attempt duplicate global alias directly via database
        with pytest.raises(IntegrityError):
            CommercialChargeAlias.objects.create(
                product_code=alt_product_code,
                raw_text="GLOBAL SECURITY",
                transport_mode=TransportMode.AIR,
                carrier_party=None,
            )

    def test_carrier_specific_aliases_may_coexist_where_valid(
        self, product_code, alt_product_code, carrier, other_carrier
    ):
        # Global alias
        CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="DOC FEE",
            transport_mode=TransportMode.AIR,
            carrier_party=None,
        )
        # Carrier 1 override
        c1 = CommercialChargeAlias.objects.create(
            product_code=alt_product_code,
            raw_text="DOC FEE",
            transport_mode=TransportMode.AIR,
            carrier_party=carrier,
        )
        # Carrier 2 override
        c2 = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="DOC FEE",
            transport_mode=TransportMode.AIR,
            carrier_party=other_carrier,
        )
        assert c1.id != c2.id

        # Duplicate for Carrier 1 rejected
        with pytest.raises(ValidationError):
            dup = CommercialChargeAlias(
                product_code=product_code,
                raw_text="DOC FEE",
                transport_mode=TransportMode.AIR,
                carrier_party=carrier,
            )
            dup.full_clean()

    def test_conflicting_active_mappings_rejected(
        self, product_code, alt_product_code, carrier
    ):
        CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="ORIGIN HANDLING",
            transport_mode=TransportMode.AIR,
            carrier_party=carrier,
        )

        # Attempt to map same text & carrier to different product code
        conflict = CommercialChargeAlias(
            product_code=alt_product_code,
            raw_text="ORIGIN HANDLING",
            transport_mode=TransportMode.AIR,
            carrier_party=carrier,
        )
        with pytest.raises(ValidationError):
            conflict.full_clean()

    def test_confidence_bounds_validated(self, product_code):
        valid_alias = CommercialChargeAlias(
            product_code=product_code,
            raw_text="VALID CONFIDENCE",
            transport_mode=TransportMode.AIR,
            confidence_score=Decimal("0.8500"),
        )
        valid_alias.full_clean()

        too_high = CommercialChargeAlias(
            product_code=product_code,
            raw_text="TOO HIGH",
            transport_mode=TransportMode.AIR,
            confidence_score=Decimal("1.0001"),
        )
        with pytest.raises(ValidationError):
            too_high.full_clean()

        negative = CommercialChargeAlias(
            product_code=product_code,
            raw_text="NEGATIVE",
            transport_mode=TransportMode.AIR,
            confidence_score=Decimal("-0.0100"),
        )
        with pytest.raises(ValidationError):
            negative.full_clean()

    def test_alias_canonical_form_persisted_on_orm_writes(self, product_code):
        # Save must trim, uppercase, and collapse multiple spaces
        alias = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="   airline    terminal   security   fee   ",
            transport_mode=TransportMode.AIR,
        )
        assert alias.raw_text == "AIRLINE TERMINAL SECURITY FEE"
        fetched = CommercialChargeAlias.objects.get(id=alias.id)
        assert fetched.raw_text == "AIRLINE TERMINAL SECURITY FEE"

    def test_equivalent_whitespace_aliases_rejected_on_orm_writes(
        self, product_code, alt_product_code, carrier
    ):
        CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="SECURITY FEE",
            transport_mode=TransportMode.AIR,
            carrier_party=carrier,
        )
        # Attempting to write an equivalent alias with extra spaces fails unique constraint
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialChargeAlias.objects.create(
                product_code=alt_product_code,
                raw_text="SECURITY   FEE",
                transport_mode=TransportMode.AIR,
                carrier_party=carrier,
            )

        # Global scope equivalent alias also fails
        CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="TERMINAL HANDLING",
            transport_mode=TransportMode.AIR,
            carrier_party=None,
        )
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialChargeAlias.objects.create(
                product_code=alt_product_code,
                raw_text="TERMINAL  HANDLING",
                transport_mode=TransportMode.AIR,
                carrier_party=None,
            )

    def test_source_currency_code_exact_three_uppercase_letters(self, product_code):
        # Blank currency is allowed
        a_blank = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="BLANK CURRENCY",
            transport_mode=TransportMode.AIR,
            source_currency="",
        )
        assert a_blank.source_currency == ""

        # Valid 3-letter currency code auto-uppercased
        a_usd = CommercialChargeAlias.objects.create(
            product_code=product_code,
            raw_text="USD CURRENCY",
            transport_mode=TransportMode.AIR,
            source_currency="usd",
        )
        assert a_usd.source_currency == "USD"

        # Invalid currency codes: numeric, symbol, incorrect length
        invalid_codes = ["123", "US1", "1PG", "US$", "€UR", "AU#", "US", "USDA", "P"]
        for bad in invalid_codes:
            alias = CommercialChargeAlias(
                product_code=product_code,
                raw_text=f"BAD CUR {bad}",
                transport_mode=TransportMode.AIR,
                source_currency=bad,
            )
            with pytest.raises(ValidationError):
                alias.full_clean()
            with pytest.raises((IntegrityError, DataError)), transaction.atomic():
                CommercialChargeAlias.objects.create(
                    product_code=product_code,
                    raw_text=f"DB BAD CUR {bad}",
                    transport_mode=TransportMode.AIR,
                    source_currency=bad,
                )


@pytest.mark.django_db
class TestFxMarketRate:
    def test_unique_currency_pair_date_source(self):
        fx1 = FxMarketRate.objects.create(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("3.85000000"),
            tt_sell_rate=Decimal("3.95000000"),
            mid_rate=Decimal("3.90000000"),
            source="BSP",
        )
        assert isinstance(fx1.id, uuid.UUID)

        with pytest.raises(IntegrityError):
            FxMarketRate.objects.create(
                base_currency="USD",
                quote_currency="PGK",
                effective_date=datetime.date(2026, 9, 22),
                tt_buy_rate=Decimal("3.86000000"),
                tt_sell_rate=Decimal("3.96000000"),
                mid_rate=Decimal("3.91000000"),
                source="BSP",
            )

    def test_tt_buy_sell_mid_stored_as_pure_market_facts(self):
        fx = FxMarketRate.objects.create(
            base_currency="AUD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("2.45100000"),
            tt_sell_rate=Decimal("2.52100000"),
            mid_rate=Decimal("2.48600000"),
            source="KINA_BANK",
        )
        assert fx.tt_buy_rate == Decimal("2.45100000")
        assert fx.tt_sell_rate == Decimal("2.52100000")
        assert fx.mid_rate == Decimal("2.48600000")

    def test_negative_or_zero_rates_rejected(self):
        fx_zero_buy = FxMarketRate(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("0.00000000"),
            tt_sell_rate=Decimal("3.95000000"),
            mid_rate=Decimal("3.90000000"),
            source="TEST",
        )
        with pytest.raises(ValidationError):
            fx_zero_buy.full_clean()

        fx_neg_sell = FxMarketRate(
            base_currency="USD",
            quote_currency="PGK",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("3.85000000"),
            tt_sell_rate=Decimal("-1.00000000"),
            mid_rate=Decimal("3.90000000"),
            source="TEST",
        )
        with pytest.raises(ValidationError):
            fx_neg_sell.full_clean()

    def test_currency_normalization_and_distinctness(self):
        fx = FxMarketRate(
            base_currency=" usd ",
            quote_currency=" pgk ",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("3.85000000"),
            tt_sell_rate=Decimal("3.95000000"),
            mid_rate=Decimal("3.90000000"),
            source="TEST",
        )
        fx.clean()
        assert fx.base_currency == "USD"
        assert fx.quote_currency == "PGK"

        fx_same = FxMarketRate(
            base_currency="USD",
            quote_currency="USD",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("1.00000000"),
            tt_sell_rate=Decimal("1.00000000"),
            mid_rate=Decimal("1.00000000"),
            source="TEST",
        )
        with pytest.raises(ValidationError):
            fx_same.full_clean()

    def test_currency_codes_exact_three_uppercase_letters(self):
        # Valid 3-letter currency code auto-uppercased
        fx_valid = FxMarketRate.objects.create(
            base_currency="usd",
            quote_currency="pgk",
            effective_date=datetime.date(2026, 9, 22),
            tt_buy_rate=Decimal("3.85000000"),
            tt_sell_rate=Decimal("3.95000000"),
            mid_rate=Decimal("3.90000000"),
            source="TEST_VALID",
        )
        assert fx_valid.base_currency == "USD"
        assert fx_valid.quote_currency == "PGK"

        # Invalid currency codes: numeric, symbol, incorrect length
        invalid_codes = ["123", "US1", "1PG", "US$", "€UR", "AU#", "US", "USDA", "P"]
        for bad in invalid_codes:
            # Bad base currency
            fx_bad_base = FxMarketRate(
                base_currency=bad,
                quote_currency="PGK",
                effective_date=datetime.date(2026, 9, 22),
                tt_buy_rate=Decimal("3.85000000"),
                tt_sell_rate=Decimal("3.95000000"),
                mid_rate=Decimal("3.90000000"),
                source=f"TEST_BAD_BASE_{bad}",
            )
            with pytest.raises(ValidationError):
                fx_bad_base.full_clean()
            with pytest.raises((IntegrityError, DataError)), transaction.atomic():
                FxMarketRate.objects.create(
                    base_currency=bad,
                    quote_currency="PGK",
                    effective_date=datetime.date(2026, 9, 22),
                    tt_buy_rate=Decimal("3.85000000"),
                    tt_sell_rate=Decimal("3.95000000"),
                    mid_rate=Decimal("3.90000000"),
                    source=f"TEST_BAD_BASE_{bad}",
                )

            # Bad quote currency
            fx_bad_quote = FxMarketRate(
                base_currency="USD",
                quote_currency=bad,
                effective_date=datetime.date(2026, 9, 22),
                tt_buy_rate=Decimal("3.85000000"),
                tt_sell_rate=Decimal("3.95000000"),
                mid_rate=Decimal("3.90000000"),
                source=f"TEST_BAD_QUOTE_{bad}",
            )
            with pytest.raises(ValidationError):
                fx_bad_quote.full_clean()
            with pytest.raises((IntegrityError, DataError)), transaction.atomic():
                FxMarketRate.objects.create(
                    base_currency="USD",
                    quote_currency=bad,
                    effective_date=datetime.date(2026, 9, 22),
                    tt_buy_rate=Decimal("3.85000000"),
                    tt_sell_rate=Decimal("3.95000000"),
                    mid_rate=Decimal("3.90000000"),
                    source=f"TEST_BAD_QUOTE_{bad}",
                )

    def test_purity_rule_no_caf_or_margin_fields(self):
        field_names = [f.name for f in FxMarketRate._meta.get_fields()]
        forbidden = ["caf", "margin", "markup", "buffer", "policy", "customer"]
        for f in field_names:
            for forbidden_word in forbidden:
                assert forbidden_word not in f.lower(), f"Purity violation: '{f}' on FxMarketRate"


@pytest.mark.django_db
class TestCommercialTermsPolicy:
    def test_validity_windows(self):
        # Open-ended validity (valid_until is None) is permitted
        p_open = CommercialTermsPolicy.objects.create(
            policy_code="STD-OPEN-ENDED",
            valid_from=datetime.date(2026, 10, 1),
            valid_until=None,
            gst_standard_percent=Decimal("10.00"),
        )
        assert p_open.valid_until is None

        # valid_until > valid_from is permitted
        policy = CommercialTermsPolicy.objects.create(
            policy_code="STD-2026-Q4",
            valid_from=datetime.date(2026, 10, 1),
            valid_until=datetime.date(2026, 12, 31),
            gst_standard_percent=Decimal("10.00"),
        )
        assert policy.policy_code == "STD-2026-Q4"

        # Same-day start/end must fail (valid_until == valid_from)
        same_day_policy = CommercialTermsPolicy(
            policy_code="SAME-DAY-START-END",
            valid_from=datetime.date(2026, 10, 1),
            valid_until=datetime.date(2026, 10, 1),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            same_day_policy.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="SAME-DAY-DB",
                valid_from=datetime.date(2026, 10, 1),
                valid_until=datetime.date(2026, 10, 1),
                gst_standard_percent=Decimal("10.00"),
            )

        # Invalid window (until strictly before from)
        invalid_policy = CommercialTermsPolicy(
            policy_code="INV-WINDOW",
            valid_from=datetime.date(2026, 10, 1),
            valid_until=datetime.date(2026, 9, 1),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            invalid_policy.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="INV-WINDOW-DB",
                valid_from=datetime.date(2026, 10, 1),
                valid_until=datetime.date(2026, 9, 1),
                gst_standard_percent=Decimal("10.00"),
            )

    def test_no_universal_or_default_margin(self):
        # target_gross_margin_percent is nullable and has NO database default
        margin_field = CommercialTermsPolicy._meta.get_field("target_gross_margin_percent")
        assert margin_field.null is True
        assert margin_field.default == models.NOT_PROVIDED or margin_field.default is None

        # Policy can be created with null target margin
        policy = CommercialTermsPolicy.objects.create(
            policy_code="NO-MARGIN-FALLBACK",
            valid_from=datetime.date(2026, 1, 1),
            gst_standard_percent=Decimal("10.00"),
        )
        assert policy.target_gross_margin_percent is None

    def test_target_gross_margin_percent_validation(self):
        # Valid margin bounds: 0% <= x < 100%
        policy_zero = CommercialTermsPolicy.objects.create(
            policy_code="MARGIN-0",
            valid_from=datetime.date(2026, 1, 1),
            target_gross_margin_percent=Decimal("0.00"),
            gst_standard_percent=Decimal("10.00"),
        )
        assert policy_zero.target_gross_margin_percent == Decimal("0.00")

        policy_99 = CommercialTermsPolicy.objects.create(
            policy_code="MARGIN-99",
            valid_from=datetime.date(2026, 1, 1),
            target_gross_margin_percent=Decimal("99.99"),
            gst_standard_percent=Decimal("10.00"),
        )
        assert policy_99.target_gross_margin_percent == Decimal("99.99")

        # 100% or greater is rejected at clean() and DB constraint
        policy_100 = CommercialTermsPolicy(
            policy_code="MARGIN-100",
            valid_from=datetime.date(2026, 1, 1),
            target_gross_margin_percent=Decimal("100.00"),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            policy_100.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="MARGIN-100-DB",
                valid_from=datetime.date(2026, 1, 1),
                target_gross_margin_percent=Decimal("100.00"),
                gst_standard_percent=Decimal("10.00"),
            )

        # Negative margin is rejected at clean() and DB constraint
        policy_neg = CommercialTermsPolicy(
            policy_code="MARGIN-NEG",
            valid_from=datetime.date(2026, 1, 1),
            target_gross_margin_percent=Decimal("-0.01"),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            policy_neg.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="MARGIN-NEG-DB",
                valid_from=datetime.date(2026, 1, 1),
                target_gross_margin_percent=Decimal("-0.01"),
                gst_standard_percent=Decimal("10.00"),
            )

    def test_import_and_export_caf_independent_and_bounded(self):
        # CAF can be NULL, 0%, or up to 100%
        policy = CommercialTermsPolicy.objects.create(
            policy_code="CAF-SPLIT-2026",
            valid_from=datetime.date(2026, 1, 1),
            import_caf_percent=Decimal("0.00"),
            export_caf_percent=Decimal("100.00"),
            gst_standard_percent=Decimal("10.00"),
        )
        assert policy.import_caf_percent == Decimal("0.00")
        assert policy.export_caf_percent == Decimal("100.00")

        # Import CAF > 100% rejected
        p_caf_over = CommercialTermsPolicy(
            policy_code="CAF-OVER",
            valid_from=datetime.date(2026, 1, 1),
            import_caf_percent=Decimal("100.01"),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            p_caf_over.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="CAF-OVER-DB",
                valid_from=datetime.date(2026, 1, 1),
                import_caf_percent=Decimal("100.01"),
                gst_standard_percent=Decimal("10.00"),
            )

        # Negative CAF is rejected
        invalid_caf = CommercialTermsPolicy(
            policy_code="INV-CAF",
            valid_from=datetime.date(2026, 1, 1),
            import_caf_percent=Decimal("-0.01"),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            invalid_caf.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="INV-CAF-DB",
                valid_from=datetime.date(2026, 1, 1),
                import_caf_percent=Decimal("-0.01"),
                gst_standard_percent=Decimal("10.00"),
            )

        # Export CAF > 100% rejected
        p_exp_over = CommercialTermsPolicy(
            policy_code="EXP-CAF-OVER",
            valid_from=datetime.date(2026, 1, 1),
            export_caf_percent=Decimal("100.01"),
            gst_standard_percent=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            p_exp_over.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="EXP-CAF-OVER-DB",
                valid_from=datetime.date(2026, 1, 1),
                export_caf_percent=Decimal("100.01"),
                gst_standard_percent=Decimal("10.00"),
            )

    def test_gst_standard_percent_bounds(self):
        # 0% allowed
        p0 = CommercialTermsPolicy.objects.create(
            policy_code="GST-ZERO",
            valid_from=datetime.date(2026, 1, 1),
            gst_standard_percent=Decimal("0.00"),
        )
        assert p0.gst_standard_percent == Decimal("0.00")

        # 100% allowed
        p100 = CommercialTermsPolicy.objects.create(
            policy_code="GST-100",
            valid_from=datetime.date(2026, 1, 1),
            gst_standard_percent=Decimal("100.00"),
        )
        assert p100.gst_standard_percent == Decimal("100.00")

        # > 100% rejected
        p_over = CommercialTermsPolicy(
            policy_code="GST-OVER",
            valid_from=datetime.date(2026, 1, 1),
            gst_standard_percent=Decimal("100.01"),
        )
        with pytest.raises(ValidationError):
            p_over.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="GST-OVER-DB",
                valid_from=datetime.date(2026, 1, 1),
                gst_standard_percent=Decimal("100.01"),
            )

        # Negative rejected
        p_neg = CommercialTermsPolicy(
            policy_code="GST-NEG",
            valid_from=datetime.date(2026, 1, 1),
            gst_standard_percent=Decimal("-0.01"),
        )
        with pytest.raises(ValidationError):
            p_neg.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            CommercialTermsPolicy.objects.create(
                policy_code="GST-NEG-DB",
                valid_from=datetime.date(2026, 1, 1),
                gst_standard_percent=Decimal("-0.01"),
            )

    def test_no_gst_classification_field_on_policy(self):
        field_names = [f.name for f in CommercialTermsPolicy._meta.get_fields()]
        assert "gst_treatment" not in field_names
        assert "gst_classification" not in field_names
        # Only rate/percentage is owned by policy
        assert "gst_standard_percent" in field_names


@pytest.mark.django_db
class TestGeoCorridorPolicy:
    @pytest.fixture
    def pom(self):
        return GeoLocation.objects.create(
            canonical_name="Port Moresby Jackson International Airport",
            country_code="PG",
            location_type=GeoLocation.LocationType.AIRPORT,
        )

    @pytest.fixture
    def bne(self):
        return GeoLocation.objects.create(
            canonical_name="Brisbane Airport",
            country_code="AU",
            location_type=GeoLocation.LocationType.AIRPORT,
        )

    @pytest.fixture
    def sin(self):
        return GeoLocation.objects.create(
            canonical_name="Singapore Changi Airport",
            country_code="SG",
            location_type=GeoLocation.LocationType.AIRPORT,
        )

    @pytest.fixture
    def lae(self):
        return GeoLocation.objects.create(
            canonical_name="Lae Nadzab Airport",
            country_code="PG",
            location_type=GeoLocation.LocationType.AIRPORT,
        )

    def test_geolocation_fk_identity_and_direct_corridor(self, bne, pom):
        corridor = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
            default_transit_days=1,
        )
        assert isinstance(corridor.id, uuid.UUID)
        assert corridor.origin == bne
        assert corridor.destination == pom
        assert corridor.via_hub is None
        assert corridor.automation_enabled is False

    def test_transport_modes_air_sea_road(self, bne, pom):
        assert list(TransportMode.values) == ["AIR", "SEA", "ROAD"]

        invalid = GeoCorridorPolicy(
            origin=bne,
            destination=pom,
            transport_mode="RAIL",
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            invalid.full_clean()

    def test_origin_and_destination_must_be_distinct(self, bne):
        loop_corridor = GeoCorridorPolicy(
            origin=bne,
            destination=bne,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            loop_corridor.full_clean()

    def test_via_hub_validation_and_distinctness(self, bne, pom):
        # Via hub cannot be origin
        hub_is_origin = GeoCorridorPolicy(
            origin=bne,
            destination=pom,
            via_hub=bne,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            hub_is_origin.full_clean()

        # Via hub cannot be destination
        hub_is_dest = GeoCorridorPolicy(
            origin=bne,
            destination=pom,
            via_hub=pom,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            hub_is_dest.full_clean()

    def test_via_hub_required_when_flagged(self, bne, pom):
        flagged_no_hub = GeoCorridorPolicy(
            origin=bne,
            destination=pom,
            via_hub=None,
            requires_transit_hub=True,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            flagged_no_hub.full_clean()

    def test_automation_enabled_defaults_false(self, bne, pom):
        corridor = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        assert corridor.automation_enabled is False

        # Can be explicitly enabled
        corridor.automation_enabled = True
        corridor.save()
        assert GeoCorridorPolicy.objects.get(id=corridor.id).automation_enabled is True

    def test_corridor_uniqueness_direct_and_hubbed(self, bne, pom, sin):
        # Direct corridor
        GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            via_hub=None,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )

        # Duplicate direct corridor rejected
        with pytest.raises(IntegrityError), transaction.atomic():
            GeoCorridorPolicy.objects.create(
                origin=bne,
                destination=pom,
                via_hub=None,
                transport_mode=TransportMode.AIR,
                valid_from=datetime.date(2026, 6, 1),
            )

        # Hubbed corridor with same origin & destination may coexist with direct
        hubbed = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            via_hub=sin,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        assert hubbed.via_hub == sin

        # Duplicate hubbed rejected
        with pytest.raises(IntegrityError), transaction.atomic():
            GeoCorridorPolicy.objects.create(
                origin=bne,
                destination=pom,
                via_hub=sin,
                transport_mode=TransportMode.AIR,
                valid_from=datetime.date(2026, 7, 1),
            )

    def test_no_pom_hardcoding_configured_via_data(self, bne, lae, pom):
        # POM configured as a transit hub through data
        corridor = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=lae,
            via_hub=pom,
            requires_transit_hub=True,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        assert corridor.via_hub.country_code == "PG"
        assert corridor.requires_transit_hub is True

    def test_corridor_existence_alone_does_not_imply_automation(self, bne, pom):
        corridor = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
        )
        # Even though corridor is active, automation is strictly disabled by default
        assert corridor.is_active is True
        assert corridor.automation_enabled is False

    def test_corridor_validity_window(self, bne, pom, lae):
        # Open-ended validity allowed
        c_open = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 1, 1),
            valid_until=None,
        )
        assert c_open.valid_until is None

        # valid_until > valid_from allowed
        c_valid = GeoCorridorPolicy.objects.create(
            origin=bne,
            destination=pom,
            via_hub=None,
            transport_mode=TransportMode.SEA,
            valid_from=datetime.date(2026, 1, 1),
            valid_until=datetime.date(2026, 12, 31),
        )
        assert c_valid.valid_until == datetime.date(2026, 12, 31)

        # Same-day start/end must fail (valid_until == valid_from)
        same_day = GeoCorridorPolicy(
            origin=bne,
            destination=pom,
            transport_mode=TransportMode.ROAD,
            valid_from=datetime.date(2026, 1, 1),
            valid_until=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            same_day.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            GeoCorridorPolicy.objects.create(
                origin=bne,
                destination=pom,
                transport_mode=TransportMode.ROAD,
                valid_from=datetime.date(2026, 1, 1),
                valid_until=datetime.date(2026, 1, 1),
            )

        # valid_until < valid_from must fail
        backwards = GeoCorridorPolicy(
            origin=bne,
            destination=lae,
            transport_mode=TransportMode.AIR,
            valid_from=datetime.date(2026, 6, 1),
            valid_until=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            backwards.full_clean()
        with pytest.raises(IntegrityError), transaction.atomic():
            GeoCorridorPolicy.objects.create(
                origin=bne,
                destination=lae,
                transport_mode=TransportMode.AIR,
                valid_from=datetime.date(2026, 6, 1),
                valid_until=datetime.date(2026, 1, 1),
            )



@pytest.mark.django_db
class TestRegistrationAndMigrations:
    def test_models_registered_and_table_names(self):
        expected_tables = {
            CommercialProductCode: "commercial_product_code",
            CommercialChargeAlias: "commercial_charge_alias",
            CommercialTermsPolicy: "policy_commercial_terms",
            FxMarketRate: "fx_market_rate",
            GeoCorridorPolicy: "geo_corridor_policy",
        }
        for model, table_name in expected_tables.items():
            assert model._meta.db_table == table_name
            registered = apps.get_model(model._meta.app_label, model.__name__)
            assert registered is model

    def test_django_migration_state_has_no_unapplied_changes(self):
        from django.core.management import call_command
        # Verifies that models in affected apps have zero missing migrations
        call_command("makemigrations", "core", "pricing_v4", check=True, dry_run=True)
