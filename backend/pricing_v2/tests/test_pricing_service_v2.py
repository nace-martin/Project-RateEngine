# backend/pricing_v2/tests/test_pricing_service_v2.py

import pytest
from decimal import Decimal
from datetime import datetime
from uuid import uuid4

from django.utils import timezone
from core.models import Policy, FxSnapshot, City, Country, Currency, LocalTariff, Surcharge
from parties.models import Company, Address
from quotes.models import Quote, QuoteLine
from ratecards.models import RateCard, RateCardBreak

from pricing_v2.pricing_service_v2 import PricingServiceV2

@pytest.mark.django_db
def test_create_import_d2d_collect_quote():
    """
    Tests the full flow for the PricingServiceV2 to create a standard
    Import D2D Collect quote, verifying all calculations and audit trails.
    """
    # 1. ARRANGE: Set up all the necessary data in the test database.
    
    # --- Create Currencies and Tariffs ---
    currency_pgk = Currency.objects.create(code='PGK', name='Papua New Guinean Kina')
    country_pg = Country.objects.create(code='PG', name='Papua New Guinea')
    LocalTariff.objects.create(
        country=country_pg,
        charge_code='CARTAGE',
        description='PNG Destination Cartage',
        basis=LocalTariff.Basis.FORMULA,
        currency=currency_pgk,
        gst_rate=Decimal("0.10")
    )

    # --- Create Parties ---
    city_pom = City.objects.create(country=country_pg, name='Port Moresby')

    bill_to_company = Company.objects.create(name='Test Importer Inc.')
    Address.objects.create(company=bill_to_company, city=city_pom, country=country_pg, address_line_1='123 Main St')

    shipper_company = Company.objects.create(name='Test Exporter Co.')
    consignee_company = bill_to_company # Often the same for D2D

    # --- Create the active Policy ---
    policy = Policy.objects.create(
        name="Test Import Policy",
        caf_import_pct=Decimal("0.05"), # 5%
        margin_pct=Decimal("0.15"),   # 15%
        effective_from=timezone.now()
    )

    # --- Create the FX Snapshot for today ---
    fx_snapshot = FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="BSP",
        rates={
            "AUD": {"tt_buy": "2.50", "tt_sell": "2.60"},
            "USD": {"tt_buy": "3.50", "tt_sell": "3.60"}
        }
    )

    # --- Define the input data for the quote request ---
    request_data = {
        "scenario": Quote.Scenario.IMP_D2D_COLLECT,
        "policy_id": "current",
        "fx_asof": str(timezone.now().date()),
        "bill_to_id": str(bill_to_company.id),
        "shipper_id": str(shipper_company.id),
        "consignee_id": str(consignee_company.id),
        "chargeable_kg": "120.00",
        "buy_lines": [
            {
                "charge_code": "AIR_FREIGHT",
                "description": "Air Freight from BNE",
                "currency": "AUD",
                "amount": "1000.00" 
            },
            {
                "charge_code": "ORIGIN_FEE",
                "description": "Origin Documentation Fee",
                "currency": "AUD",
                "amount": "50.00" 
            }
        ]
    }

    # 2. ACT: Instantiate the service and call the main method.
    service = PricingServiceV2()
    created_quote = service.create_quote(request_data)

    # 3. ASSERT: Verify that the created quote and its lines are correct.
    assert created_quote is not None
    assert created_quote.scenario == Quote.Scenario.IMP_D2D_COLLECT
    assert created_quote.policy == policy
    assert created_quote.fx_snapshot == fx_snapshot
    assert created_quote.bill_to == bill_to_company

    # --- Verify the Calculations ---
    origin_lines = created_quote.lines.filter(section='ORIGIN')
    assert origin_lines.count() == 2
    
    total_sell_from_lines = sum(line.sell_amount_pgk for line in origin_lines)
    assert round(total_sell_from_lines, 2) == Decimal("3169.69")

    first_line = origin_lines.first()
    assert first_line.caf_applied_pct == policy.caf_import_pct
    assert first_line.margin_applied_pct == policy.margin_pct

    totals = created_quote.totals
    assert round(totals.grand_total_pgk, 2) == Decimal("3367.69")
    assert totals.gst_total_pgk == Decimal("18.00")

@pytest.mark.django_db
def test_create_export_d2d_prepaid_quote():
    """
    Tests the full flow for an Export D2D Prepaid quote, which involves
    rate cards, complex surcharges, and currency conversion of destination charges.
    """
    # 1. ARRANGE: Set up all necessary data for the export scenario.
    
    # --- Create Parties and Core Data (similar to the import test) ---
    country_pg = Country.objects.create(code='PG', name='Papua New Guinea')
    city_pom = City.objects.create(country=country_pg, name='Port Moresby')
    bill_to_company = Company.objects.create(name='Test Exporter Inc.')
    Address.objects.create(company=bill_to_company, city=city_pom, country=country_pg, address_line_1='456 Export St')
    shipper_company = bill_to_company
    consignee_company = Company.objects.create(name='Test Receiver Co.')
    
    pgk_currency = Currency.objects.create(code='PGK', name='Papua New Guinean Kina')

    # --- Create Policy and FX Snapshot ---
    policy = Policy.objects.create(
        name="Test Export Policy",
        caf_import_pct=Decimal("0.05"), # Used for AUD -> PGK conversion
        margin_pct=Decimal("0.15"),
        effective_from=timezone.now()
    )
    fx_snapshot = FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="BSP",
        rates={"AUD": {"tt_buy": "2.50", "tt_sell": "2.60"}}
    )

    # --- Create the Rate Card for POM -> BNE ---
    rate_card = RateCard.objects.create(
        origin_city_code="POM",
        destination_city_code="BNE",
        minimum_charge=Decimal("150.00"),
        effective_from=timezone.now().date()
    )
    # Add weight breaks based on the spec
    RateCardBreak.objects.create(rate_card=rate_card, weight_break_kg=Decimal("45.00"), rate_per_kg=Decimal("6.50"))
    RateCardBreak.objects.create(rate_card=rate_card, weight_break_kg=Decimal("100.00"), rate_per_kg=Decimal("5.60"))
    RateCardBreak.objects.create(rate_card=rate_card, weight_break_kg=Decimal("250.00"), rate_per_kg=Decimal("5.20"))

    # --- Create the PX Surcharges ---
    Surcharge.objects.create(code='AW', description='Airway Bill Fee', basis=Surcharge.Basis.FLAT, rate=Decimal('35.00'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    Surcharge.objects.create(code='BI', description='BSP Clearance', basis=Surcharge.Basis.FLAT, rate=Decimal('35.00'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    Surcharge.objects.create(code='BS', description='Bilateral Security', basis=Surcharge.Basis.FLAT, rate=Decimal('35.00'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    Surcharge.objects.create(code='MY', description='Fuel Surcharge', basis=Surcharge.Basis.PER_KG, rate=Decimal('0.70'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    # Note: SC is a mixed flat + per_kg rate. Our current model doesn't support this well.
    # We will simulate it as two separate charges for the purpose of this test. A future improvement could be a 'FORMULA' basis.
    Surcharge.objects.create(code='SC_PER_KG', description='Security Surcharge (per kg)', basis=Surcharge.Basis.PER_KG, rate=Decimal('0.17'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    Surcharge.objects.create(code='SC_FLAT', description='Security Surcharge (flat)', basis=Surcharge.Basis.FLAT, rate=Decimal('35.00'), currency=pgk_currency, is_active=True, effective_from=timezone.now().date())
    Surcharge.objects.create(code='BP', description='Break Bulk Fee', basis=Surcharge.Basis.PER_KG, rate=Decimal('0.05'), currency=pgk_currency, is_active=True, minimum_charge=Decimal('30.00'), effective_from=timezone.now().date())


    # --- Define the input data for the quote request ---
    request_data = {
        "scenario": Quote.Scenario.EXP_D2D_PREPAID,
        "policy_id": "current",
        "fx_asof": str(timezone.now().date()),
        "bill_to_id": str(bill_to_company.id),
        "shipper_id": str(shipper_company.id),
        "consignee_id": str(consignee_company.id),
        "origin_code": "POM",
        "destination_code": "BNE",
        "chargeable_kg": "120.00",
        "agent_dest_lines_aud": [
            {"amount": "250.00", "description": "Agent Handling and Delivery"}
        ]
    }

    # 2. ACT: Call the service.
    service = PricingServiceV2()
    created_quote = service.create_quote(request_data)

    # 3. ASSERT: Verify the calculations based on Spec C.4.
    assert created_quote is not None
    assert created_quote.scenario == Quote.Scenario.EXP_D2D_PREPAID

    # --- Expected Buy-Side Calculation ---
    # Freight: 120kg * 5.60/kg = 672.00
    # Surcharges:
    #   AW, BI, BS = 35*3 = 105.00
    #   MY = 0.70 * 120 = 84.00
    #   SC = (0.17 * 120) + 35 = 20.40 + 35 = 55.40
    #   BP = 0.05 * 120 = 6.00, which is less than min 30.00, so use 30.00
    # Origin Buy PGK = 672 + 105 + 84 + 55.40 + 30 = 946.40
    # Dest Buy AUD: 250 AUD
    # Dest Buy PGK: 250 * (2.50 TT_BUY * 1.05 CAF) = 250 * 2.625 = 656.25
    # Total Buy PGK = 946.40 + 656.25 = 1602.65
    
    # --- Expected Sell-Side Calculation ---
    # Margin = 15%
    # Total Sell PGK = 1602.65 * 1.15 = 1843.0475, rounded to 1843.05
    
    totals = created_quote.totals
    assert round(totals.grand_total_pgk, 2) == Decimal("1843.05")
    assert totals.gst_total_pgk == Decimal("0.00") # No GST in this example

    # Verify a few key lines
    freight_line = created_quote.lines.get(charge_code='AIR_FREIGHT')
    assert freight_line.buy_amount_native == Decimal("672.00")
    assert freight_line.sell_amount_pgk == Decimal("672.00") * Decimal("1.15") # Check margin is applied
    assert freight_line.margin_applied_pct == policy.margin_pct

    dest_line = created_quote.lines.get(section=QuoteLine.Section.DESTINATION)
    assert dest_line.buy_amount_native == Decimal("250.00")
    assert dest_line.currency == "AUD"
    assert dest_line.caf_applied_pct == policy.caf_import_pct
    assert dest_line.margin_applied_pct == policy.margin_pct

@pytest.mark.django_db
def test_create_import_a2d_agent_quote():
    """
    Tests the special scenario for creating a prepaid quote for an agent in AUD,
    verifying the negative CAF and per-line rounding logic.
    """
    # 1. ARRANGE
    country_pg = Country.objects.create(code='PG', name='Papua New Guinea')
    city_pom = City.objects.create(country=country_pg, name='Port Moresby')
    agent_company = Company.objects.create(name='AUS Agent Logistics')
    Address.objects.create(company=agent_company, city=city_pom, country=country_pg, address_line_1='789 Agent Ave')

    # Policy with a caf_export_pct for the PGK -> AUD conversion
    Policy.objects.create(
        name="Test Agent Quote Policy",
        caf_export_pct=Decimal("0.10"), # 10%
        margin_pct=Decimal("0.0"), # No margin for this scenario
        effective_from=timezone.now()
    )

    # FX Snapshot with a TT_SELL rate
    FxSnapshot.objects.create(
        as_of_timestamp=timezone.now(),
        source="BSP",
        rates={"AUD": {"tt_buy": "2.50", "tt_sell": "2.60"}}
    )

    # --- Define the input data for the quote request ---
    # The agent_dest_lines_aud field isn't used here, this scenario calculates from PGK.
    # A future refactor could make this more consistent.
    request_data = {
        "scenario": Quote.Scenario.IMP_A2D_AGENT,
        "policy_id": "current",
        "fx_asof": str(timezone.now().date()),
        "bill_to_id": str(agent_company.id),
        "shipper_id": str(agent_company.id), # Not relevant but required
        "consignee_id": str(agent_company.id), # Not relevant but required
        "chargeable_kg": "100.00", # Weight not used in this simplified test
        "origin_code": "BNE", # Not relevant but required
        "destination_code": "POM", # Not relevant but required
    }

    # 2. ACT
    service = PricingServiceV2()
    created_quote = service.create_quote(request_data)

    # 3. ASSERT
    assert created_quote is not None
    assert created_quote.scenario == Quote.Scenario.IMP_A2D_AGENT

    # --- Verify Calculations based on Spec B.3 ---
    # PGK lines: 330, 275, 181.5
    # TT SELL = 2.60, CAF = 10% -> effective_fx = 2.60 * (1 - 0.10) = 2.34
    # Per-line rounding:
    #   330 / 2.34 = 141.02 -> ceil(141.02) = 142
    #   275 / 2.34 = 117.52 -> ceil(117.52) = 118
    #   181.5 / 2.34 = 77.56 -> ceil(77.56) = 78
    # Total AUD = 142 + 118 + 78 = 338
    # Note: The spec example has more lines; our test uses a subset. The total is different, but the logic is the same.
    
    totals = created_quote.totals
    assert totals.output_currency == "AUD"
    assert totals.grand_total_output_currency == Decimal("338")

    # Check one line to ensure auditability
    line = created_quote.lines.first()
    assert line.currency == "AUD"
    assert line.rounding_applied is True
    assert line.caf_applied_pct == Decimal("-0.10") # Verify negative CAF is recorded
