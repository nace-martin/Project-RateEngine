"""Target verification tests for Phase 3: Rate Matrix Foundation.

Covers:
- RateSheet (BUY vs SELL, currency code, validity window, transport mode, version)
- RateLine (ProductCode FK, every rate basis, incompatible field integrity, min/max charges)
- RateApplicability (spatial GeoLocation FKs, direction, service level, OneToOne)
- RateTier (quantities, rates, non-overlapping breaks, open-ended infinity)
- Tiered line requires tiers & non-tiered rejects tiers
- PostgreSQL GiST exclusion constraint & SQLite validation parity
- Model registration and exact table names
"""

import datetime
import uuid
from decimal import Decimal

import pytest
from core.geo_models import GeoLocation
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import DataError, IntegrityError, connection, transaction
from parties.party_models import PartyMaster

from pricing_v4.commercial_models import CommercialProductCode
from pricing_v4.rate_matrix_models import (
    RateApplicability,
    RateLine,
    RateSheet,
    RateTier,
)


@pytest.fixture
def party_customer():
    return PartyMaster.objects.create(
        legal_name="Acme Importers PNG Ltd",
        trade_name="Acme Cargo",
    )


@pytest.fixture
def party_carrier():
    return PartyMaster.objects.create(
        legal_name="Air Niugini Cargo",
        trade_name="Air Niugini",
    )


@pytest.fixture
def product_code_freight():
    return CommercialProductCode.objects.create(
        code="AF-LINEHAUL-STD",
        name="Air Freight Standard Linehaul",
        category=CommercialProductCode.Category.FREIGHT,
        gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_IMPORT,
        charge_basis_default=CommercialProductCode.ChargeBasis.PER_KG,
    )


@pytest.fixture
def product_code_fsc():
    return CommercialProductCode.objects.create(
        code="AF-FSC-PERCENT",
        name="Fuel Surcharge (Percentage)",
        category=CommercialProductCode.Category.FREIGHT,
        gst_treatment=CommercialProductCode.GstTreatment.FREIGHT_IMPORT,
        charge_basis_default=CommercialProductCode.ChargeBasis.PERCENTAGE,
    )


@pytest.fixture
def product_code_clearance():
    return CommercialProductCode.objects.create(
        code="CUST-ENTRY-STD",
        name="Customs Entry Standard",
        category=CommercialProductCode.Category.CLEARANCE,
        gst_treatment=CommercialProductCode.GstTreatment.DOMESTIC_STANDARD,
        charge_basis_default=CommercialProductCode.ChargeBasis.FLAT,
    )


@pytest.fixture
def loc_pom():
    return GeoLocation.objects.create(
        canonical_name="Port Moresby Jackson International Airport",
        country_code="PG",
        location_type=GeoLocation.LocationType.AIRPORT,
    )


@pytest.fixture
def loc_bne():
    return GeoLocation.objects.create(
        canonical_name="Brisbane Airport",
        country_code="AU",
        location_type=GeoLocation.LocationType.AIRPORT,
    )


@pytest.fixture
def buy_sheet(party_carrier):
    return RateSheet.objects.create(
        name="Air Niugini Master Tariff 2026",
        carrier=party_carrier,
        rate_type=RateSheet.RateType.BUY,
        transport_mode=RateSheet.TransportMode.AIR,
        currency_code="PGK",
        valid_from=datetime.date(2026, 1, 1),
        valid_until=datetime.date(2026, 12, 31),
        version=1,
    )


@pytest.fixture
def sell_sheet(party_customer):
    return RateSheet.objects.create(
        name="Acme Customer Tariff 2026",
        party=party_customer,
        rate_type=RateSheet.RateType.SELL,
        transport_mode=RateSheet.TransportMode.AIR,
        currency_code="USD",
        valid_from=datetime.date(2026, 1, 1),
        valid_until=datetime.date(2026, 12, 31),
        version=1,
    )


# =============================================================================
# 1. RateSheet Tests
# =============================================================================


@pytest.mark.django_db
class TestRateSheet:
    def test_buy_and_sell_sheets_created_distinctly(self, buy_sheet, sell_sheet):
        assert isinstance(buy_sheet.id, uuid.UUID)
        assert buy_sheet.rate_type == RateSheet.RateType.BUY
        assert buy_sheet.carrier is not None
        assert buy_sheet.party is None

        assert isinstance(sell_sheet.id, uuid.UUID)
        assert sell_sheet.rate_type == RateSheet.RateType.SELL
        assert sell_sheet.party is not None
        assert sell_sheet.carrier is None

    def test_invalid_rate_type_rejected(self):
        sheet = RateSheet(
            name="Invalid Side Tariff",
            rate_type="MARGIN",
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="USD",
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            sheet.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(
                name="Invalid Side DB",
                rate_type="MARGIN",
                transport_mode=RateSheet.TransportMode.AIR,
                currency_code="USD",
                valid_from=datetime.date(2026, 1, 1),
            )

    def test_transport_mode_choices_enforced(self):
        sheet = RateSheet(
            name="Invalid Mode",
            rate_type=RateSheet.RateType.BUY,
            transport_mode="RAIL",
            currency_code="USD",
            valid_from=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            sheet.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(
                name="Invalid Mode DB",
                rate_type=RateSheet.RateType.BUY,
                transport_mode="RAIL",
                currency_code="USD",
                valid_from=datetime.date(2026, 1, 1),
            )

    def test_currency_code_exact_three_uppercase_letters(self):
        # Auto-uppercasing
        sheet_usd = RateSheet.objects.create(
            name="Lower Currency",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="usd",
            valid_from=datetime.date(2026, 1, 1),
        )
        assert sheet_usd.currency_code == "USD"

        # Invalid codes rejected
        invalid_currencies = ["123", "US1", "US$", "€UR", "US", "USDA", ""]
        for bad in invalid_currencies:
            sheet_bad = RateSheet(
                name=f"Bad Currency {bad}",
                rate_type=RateSheet.RateType.BUY,
                transport_mode=RateSheet.TransportMode.AIR,
                currency_code=bad,
                valid_from=datetime.date(2026, 1, 1),
            )
            with pytest.raises(ValidationError):
                sheet_bad.full_clean()

            with pytest.raises((IntegrityError, DataError)), transaction.atomic():
                RateSheet.objects.create(
                    name=f"Bad Currency DB {bad}",
                    rate_type=RateSheet.RateType.BUY,
                    transport_mode=RateSheet.TransportMode.AIR,
                    currency_code=bad,
                    valid_from=datetime.date(2026, 1, 1),
                )

    def test_validity_window_strict_greater_than(self):
        # Open-ended allowed
        s_open = RateSheet.objects.create(
            name="Open Ended",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="PGK",
            valid_from=datetime.date(2026, 1, 1),
            valid_until=None,
        )
        assert s_open.valid_until is None

        # Same-day start/end rejected
        s_same = RateSheet(
            name="Same Day",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="PGK",
            valid_from=datetime.date(2026, 1, 1),
            valid_until=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            s_same.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(
                name="Same Day DB",
                rate_type=RateSheet.RateType.BUY,
                transport_mode=RateSheet.TransportMode.AIR,
                currency_code="PGK",
                valid_from=datetime.date(2026, 1, 1),
                valid_until=datetime.date(2026, 1, 1),
            )

        # Reversed dates rejected
        s_rev = RateSheet(
            name="Reversed Dates",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="PGK",
            valid_from=datetime.date(2026, 6, 1),
            valid_until=datetime.date(2026, 1, 1),
        )
        with pytest.raises(ValidationError):
            s_rev.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(
                name="Reversed Dates DB",
                rate_type=RateSheet.RateType.BUY,
                transport_mode=RateSheet.TransportMode.AIR,
                currency_code="PGK",
                valid_from=datetime.date(2026, 6, 1),
                valid_until=datetime.date(2026, 1, 1),
            )

    def test_version_positive_integer(self):
        v0 = RateSheet(
            name="Version Zero",
            rate_type=RateSheet.RateType.BUY,
            transport_mode=RateSheet.TransportMode.AIR,
            currency_code="USD",
            valid_from=datetime.date(2026, 1, 1),
            version=0,
        )
        with pytest.raises(ValidationError):
            v0.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateSheet.objects.create(
                name="Version Zero DB",
                rate_type=RateSheet.RateType.BUY,
                transport_mode=RateSheet.TransportMode.AIR,
                currency_code="USD",
                valid_from=datetime.date(2026, 1, 1),
                version=0,
            )


# =============================================================================
# 2. RateLine Tests
# =============================================================================


@pytest.mark.django_db
class TestRateLine:
    def test_every_supported_rate_basis_creates_cleanly(
        self, buy_sheet, product_code_freight, product_code_clearance, product_code_fsc
    ):
        # 1. FLAT
        l_flat = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_clearance,
            rate_basis=RateLine.RateBasis.FLAT,
            unit_rate=Decimal("150.0000"),
        )
        assert l_flat.unit_rate == Decimal("150.0000")

        # 2. PER_KG
        l_kg = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("4.5000"),
            min_charge=Decimal("50.0000"),
        )
        assert l_kg.unit_rate == Decimal("4.5000")

        # 3. PER_CBM
        l_cbm = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_CBM,
            unit_rate=Decimal("120.0000"),
        )
        assert l_cbm.unit_rate == Decimal("120.0000")

        # 4. PER_UNIT
        l_unit = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_clearance,
            rate_basis=RateLine.RateBasis.PER_UNIT,
            unit_rate=Decimal("25.0000"),
        )
        assert l_unit.unit_rate == Decimal("25.0000")

        # 5. TIERED_WEIGHT (unit_rate must be NULL)
        l_tiered = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
            unit_rate=None,
            min_charge=Decimal("75.0000"),
        )
        assert l_tiered.unit_rate is None

        # 6. PERCENTAGE (requires percentage_rate + percentage_basis_product_code)
        l_pct = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_fsc,
            rate_basis=RateLine.RateBasis.PERCENTAGE,
            percentage_rate=Decimal("15.50"),
            percentage_basis_product_code=product_code_freight,
            unit_rate=None,
        )
        assert l_pct.percentage_rate == Decimal("15.50")
        assert l_pct.percentage_basis_product_code == product_code_freight

    def test_tiered_weight_must_not_carry_competing_scalar_rate(
        self, buy_sheet, product_code_freight
    ):
        # Model clean() rejection
        line = RateLine(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
            unit_rate=Decimal("5.0000"),
        )
        with pytest.raises(ValidationError):
            line.clean()

        # Database CHECK constraint rejection
        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_freight,
                rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
                unit_rate=Decimal("5.0000"),
            )

    def test_percentage_basis_requirements_and_field_exclusivity(
        self, buy_sheet, product_code_fsc, product_code_freight
    ):
        # Missing percentage_basis_product_code rejected
        no_basis_code = RateLine(
            sheet=buy_sheet,
            product_code=product_code_fsc,
            rate_basis=RateLine.RateBasis.PERCENTAGE,
            percentage_rate=Decimal("10.00"),
            percentage_basis_product_code=None,
        )
        with pytest.raises(ValidationError):
            no_basis_code.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_fsc,
                rate_basis=RateLine.RateBasis.PERCENTAGE,
                percentage_rate=Decimal("10.00"),
                percentage_basis_product_code=None,
            )

        # Missing percentage_rate rejected
        no_pct_rate = RateLine(
            sheet=buy_sheet,
            product_code=product_code_fsc,
            rate_basis=RateLine.RateBasis.PERCENTAGE,
            percentage_rate=None,
            percentage_basis_product_code=product_code_freight,
        )
        with pytest.raises(ValidationError):
            no_pct_rate.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_fsc,
                rate_basis=RateLine.RateBasis.PERCENTAGE,
                percentage_rate=None,
                percentage_basis_product_code=product_code_freight,
            )

        # Competing scalar unit_rate on PERCENTAGE rejected
        competing_scalar = RateLine(
            sheet=buy_sheet,
            product_code=product_code_fsc,
            rate_basis=RateLine.RateBasis.PERCENTAGE,
            percentage_rate=Decimal("10.00"),
            percentage_basis_product_code=product_code_freight,
            unit_rate=Decimal("50.0000"),
        )
        with pytest.raises(ValidationError):
            competing_scalar.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_fsc,
                rate_basis=RateLine.RateBasis.PERCENTAGE,
                percentage_rate=Decimal("10.00"),
                percentage_basis_product_code=product_code_freight,
                unit_rate=Decimal("50.0000"),
            )

    def test_non_percentage_bases_must_not_carry_percentage_fields(
        self, buy_sheet, product_code_freight
    ):
        # Scalar line with percentage_rate rejected
        line_scalar_with_pct = RateLine(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("5.0000"),
            percentage_rate=Decimal("10.00"),
        )
        with pytest.raises(ValidationError):
            line_scalar_with_pct.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_freight,
                rate_basis=RateLine.RateBasis.PER_KG,
                unit_rate=Decimal("5.0000"),
                percentage_rate=Decimal("10.00"),
            )

    def test_min_lte_max_charge_constraint(self, buy_sheet, product_code_freight):
        # min_charge > max_charge rejected
        inverted = RateLine(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("5.0000"),
            min_charge=Decimal("100.0000"),
            max_charge=Decimal("50.0000"),
        )
        with pytest.raises(ValidationError):
            inverted.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_freight,
                rate_basis=RateLine.RateBasis.PER_KG,
                unit_rate=Decimal("5.0000"),
                min_charge=Decimal("100.0000"),
                max_charge=Decimal("50.0000"),
            )

        # min_charge == max_charge allowed
        equal_bounds = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("5.0000"),
            min_charge=Decimal("100.0000"),
            max_charge=Decimal("100.0000"),
        )
        assert equal_bounds.min_charge == equal_bounds.max_charge

    def test_negative_rates_and_charges_rejected(self, buy_sheet, product_code_freight):
        neg_unit = RateLine(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("-1.0000"),
        )
        with pytest.raises(ValidationError):
            neg_unit.clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateLine.objects.create(
                sheet=buy_sheet,
                product_code=product_code_freight,
                rate_basis=RateLine.RateBasis.PER_KG,
                unit_rate=Decimal("-1.0000"),
            )


# =============================================================================
# 3. RateApplicability Tests
# =============================================================================


@pytest.mark.django_db
class TestRateApplicability:
    def test_applicability_with_spatial_and_service_filters(
        self, buy_sheet, product_code_freight, loc_bne, loc_pom
    ):
        line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("3.5000"),
        )
        app = RateApplicability.objects.create(
            rate_line=line,
            origin=loc_bne,
            destination=loc_pom,
            service_level=RateApplicability.ServiceLevel.EXPRESS,
            direction=RateApplicability.Direction.IMPORT,
            commodity_category="GENERAL",
            equipment_type="AKE",
        )
        assert isinstance(app.id, uuid.UUID)
        assert app.origin == loc_bne
        assert app.destination == loc_pom
        assert app.direction == "IMPORT"
        assert app.service_level == "EXPRESS"

    def test_one_to_one_relationship_enforced(self, buy_sheet, product_code_freight):
        line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("3.5000"),
        )
        RateApplicability.objects.create(
            rate_line=line,
            direction=RateApplicability.Direction.DOMESTIC,
        )

        # Second applicability on same RateLine rejected by OneToOne unique constraint
        with pytest.raises(IntegrityError), transaction.atomic():
            RateApplicability.objects.create(
                rate_line=line,
                direction=RateApplicability.Direction.EXPORT,
            )

    def test_direction_and_service_level_choices_enforced(
        self, buy_sheet, product_code_freight
    ):
        line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.PER_KG,
            unit_rate=Decimal("3.5000"),
        )
        invalid_app = RateApplicability(
            rate_line=line,
            direction="TRANSIT",
            service_level="SUPER_FAST",
        )
        with pytest.raises(ValidationError):
            invalid_app.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            RateApplicability.objects.create(
                rate_line=line,
                direction="TRANSIT",
            )


# =============================================================================
# 4. RateTier Tests
# =============================================================================


@pytest.mark.django_db
class TestRateTier:
    @pytest.fixture
    def tiered_line(self, buy_sheet, product_code_freight):
        return RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
            unit_rate=None,
        )

    def test_contiguous_non_overlapping_tiers_create_cleanly(self, tiered_line):
        t1 = RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("45.0000"),
            unit_rate=Decimal("12.5000"),
        )
        t2 = RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("45.0000"),
            max_quantity=Decimal("100.0000"),
            unit_rate=Decimal("10.0000"),
        )
        t3 = RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("100.0000"),
            max_quantity=Decimal("300.0000"),
            unit_rate=Decimal("8.0000"),
        )
        t4 = RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("300.0000"),
            max_quantity=None,  # Open-ended infinity
            unit_rate=Decimal("6.5000"),
        )
        assert tiered_line.tiers.count() == 4
        assert t1.id and t2.id and t3.id and t4.id
        assert t4.max_quantity is None

    def test_overlapping_finite_tiers_rejected(self, tiered_line):
        RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("45.0000"),
            unit_rate=Decimal("12.5000"),
        )

        # Overlapping tier: [40, 100) overlaps [0, 45)
        overlap = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("40.0000"),
            max_quantity=Decimal("100.0000"),
            unit_rate=Decimal("10.0000"),
        )
        with pytest.raises(ValidationError):
            overlap.full_clean()

        with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
            RateTier.objects.create(
                rate_line=tiered_line,
                min_quantity=Decimal("40.0000"),
                max_quantity=Decimal("100.0000"),
                unit_rate=Decimal("10.0000"),
            )

    def test_overlapping_open_ended_tier_rejected(self, tiered_line):
        RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("100.0000"),
            max_quantity=None,  # [100, +inf)
            unit_rate=Decimal("7.0000"),
        )

        # Overlaps [100, +inf)
        overlap = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("150.0000"),
            max_quantity=Decimal("300.0000"),
            unit_rate=Decimal("6.0000"),
        )
        with pytest.raises(ValidationError):
            overlap.full_clean()

        with pytest.raises((ValidationError, IntegrityError)), transaction.atomic():
            RateTier.objects.create(
                rate_line=tiered_line,
                min_quantity=Decimal("150.0000"),
                max_quantity=Decimal("300.0000"),
                unit_rate=Decimal("6.0000"),
            )

    def test_distinct_rate_lines_can_have_identical_tier_brackets(
        self, buy_sheet, sell_sheet, product_code_freight
    ):
        line1 = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
        )
        line2 = RateLine.objects.create(
            sheet=sell_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
        )

        t1 = RateTier.objects.create(
            rate_line=line1,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("100.0000"),
            unit_rate=Decimal("10.0000"),
        )
        t2 = RateTier.objects.create(
            rate_line=line2,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("100.0000"),
            unit_rate=Decimal("15.0000"),
        )
        assert t1.rate_line_id != t2.rate_line_id
        assert t1.min_quantity == t2.min_quantity

    def test_max_quantity_must_be_greater_than_min_quantity(self, tiered_line):
        # max <= min rejected
        same_bounds = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("50.0000"),
            max_quantity=Decimal("50.0000"),
            unit_rate=Decimal("10.0000"),
        )
        with pytest.raises(ValidationError):
            same_bounds.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            # Bypass full_clean to test DB constraint directly
            super(RateTier, same_bounds).save(force_insert=True)

        reversed_bounds = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("100.0000"),
            max_quantity=Decimal("50.0000"),
            unit_rate=Decimal("10.0000"),
        )
        with pytest.raises(ValidationError):
            reversed_bounds.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            super(RateTier, reversed_bounds).save(force_insert=True)

    def test_negative_tier_quantities_and_rates_rejected(self, tiered_line):
        neg_min = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("-1.0000"),
            max_quantity=Decimal("45.0000"),
            unit_rate=Decimal("10.0000"),
        )
        with pytest.raises(ValidationError):
            neg_min.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            super(RateTier, neg_min).save(force_insert=True)

        neg_rate = RateTier(
            rate_line=tiered_line,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("45.0000"),
            unit_rate=Decimal("-0.5000"),
        )
        with pytest.raises(ValidationError):
            neg_rate.full_clean()

        with pytest.raises(IntegrityError), transaction.atomic():
            super(RateTier, neg_rate).save(force_insert=True)

    def test_non_tiered_rate_line_rejects_tiers(self, buy_sheet, product_code_clearance):
        flat_line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_clearance,
            rate_basis=RateLine.RateBasis.FLAT,
            unit_rate=Decimal("100.0000"),
        )
        tier_on_flat = RateTier(
            rate_line=flat_line,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("45.0000"),
            unit_rate=Decimal("10.0000"),
        )
        with pytest.raises(ValidationError):
            tier_on_flat.full_clean()

        with pytest.raises(ValidationError):
            tier_on_flat.save()

    def test_tiered_line_requires_at_least_one_tier(self, buy_sheet, product_code_freight):
        tiered_line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
        )
        # Existing tiered line with 0 tiers fails validation
        with pytest.raises(ValidationError):
            tiered_line.clean()
        with pytest.raises(ValidationError):
            tiered_line.validate_tier_requirements()

        # Adding a tier resolves validation
        RateTier.objects.create(
            rate_line=tiered_line,
            min_quantity=Decimal("0.0000"),
            max_quantity=Decimal("100.0000"),
            unit_rate=Decimal("10.0000"),
        )
        tiered_line.clean()
        tiered_line.validate_tier_requirements()


# =============================================================================
# 5. PostgreSQL GiST Exclusion Constraint Specific Test
# =============================================================================


@pytest.mark.django_db
class TestPostgresExclusionConstraint:
    def test_database_level_exclusion_constraint_on_postgresql(
        self, buy_sheet, product_code_freight
    ):
        """Verifies that on PostgreSQL, overlapping tiers are rejected at the DB engine level."""
        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL GiST exclusion test requires PostgreSQL connection")

        line = RateLine.objects.create(
            sheet=buy_sheet,
            product_code=product_code_freight,
            rate_basis=RateLine.RateBasis.TIERED_WEIGHT,
        )

        # Insert first tier directly via SQL to bypass any model validation
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rate_tier (id, rate_line_id, min_quantity, max_quantity, unit_rate)
                VALUES (%s, %s, %s, %s, %s)
                """,
                [str(uuid.uuid4()), str(line.id), Decimal("0.00"), Decimal("45.00"), Decimal("10.00")],
            )

            # Insert overlapping tier directly via SQL: must raise IntegrityError
            with pytest.raises(IntegrityError):
                cursor.execute(
                    """
                    INSERT INTO rate_tier (id, rate_line_id, min_quantity, max_quantity, unit_rate)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    [
                        str(uuid.uuid4()),
                        str(line.id),
                        Decimal("40.00"),
                        Decimal("100.00"),
                        Decimal("8.00"),
                    ],
                )


# =============================================================================
# 6. Model Registration & Exact Table Names
# =============================================================================


@pytest.mark.django_db
class TestModelRegistrationAndTableNames:
    def test_exact_table_names(self):
        expected_tables = {
            RateSheet: "rate_sheet",
            RateLine: "rate_line",
            RateApplicability: "rate_applicability",
            RateTier: "rate_tier",
        }
        for model, expected_name in expected_tables.items():
            assert model._meta.db_table == expected_name
            registered = apps.get_model(model._meta.app_label, model.__name__)
            assert registered is model

    def test_django_migration_state_in_sync(self):
        from django.core.management import call_command

        call_command("makemigrations", "core", "pricing_v4", check=True, dry_run=True)
