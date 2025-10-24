# In: backend/pricing_v2/tests/test_pricing_service_v3.py

import pytest
import json
from decimal import Decimal
from django.utils import timezone

# V3 Service and Dataclasses
from pricing_v2.pricing_service_v3 import PricingServiceV3
from pricing_v2.dataclasses_v3 import V3QuoteRequest

# Models
from core.models import Airport, FxSnapshot, Currency
from parties.models import Company, Contact, CustomerCommercialProfile
from services.models import ServiceComponent, IncotermRule
from quotes.models import Quote, QuoteVersion, QuoteLine, QuoteTotal

# Mark this whole file as needing database access
pytestmark = pytest.mark.django_db


@pytest.fixture
def setup_v3_golden_test_data():
    """
    Sets up all required data for the V3 golden test.
    This assumes the migrations for services, ratecards, etc., have been run.
    """
    
    # === 1. Create Customer and Contact ===
    customer, _ = Company.objects.get_or_create(
        name="Test Customer V3",
        defaults={'company_type': 'CUSTOMER'}
    )
    contact, _ = Contact.objects.get_or_create(
        company=customer,
        email="test@customerv3.com",
        defaults={'first_name': 'Test', 'last_name': 'User'}
    )
    
    # === 2. Create Customer Commercial Profile ===
    # We set a 30% default margin
    usd, _ = Currency.objects.get_or_create(code='USD')
    profile = CustomerCommercialProfile.objects.create(
        company=customer,
        default_margin_percent=Decimal("30.00"),
        preferred_quote_currency=usd
    )
    
    # === 3. Create FX Snapshot ===
    # We set specific FX rates for our calculation
    fx_rates_json = {
        "AUD": {"tt_buy": "2.20", "tt_sell": "2.10"},
        "USD": {"tt_buy": "3.40", "tt_sell": "0.30"}
    }
    fx, _ = FxSnapshot.objects.get_or_create(
        as_of_timestamp=timezone.now(),
        defaults={
            'rates': json.dumps(fx_rates_json),
            'caf_percent': Decimal("2.00"),     # 2%
            'fx_buffer_percent': Decimal("1.00") # 1%
        }
    )
    
    # === 4. Ensure Airports exist ===
    # These should be seeded, but we ensure they're here
    bne, _ = Airport.objects.get_or_create(iata_code="BNE", defaults={'name': "Brisbane"})
    pom, _ = Airport.objects.get_or_create(iata_code="POM", defaults={'name': "Port Moresby"})
    
    # === 5. Find Services (seeded by migrations) ===
    # These are our COGS services
    try:
        service_freight = ServiceComponent.objects.get(description__iexact="Freight")
        service_pickup = ServiceComponent.objects.get(description__iexact="Origin Pickup")
        service_fuel = ServiceComponent.objects.get(description__iexact="Fuel Surcharge (Origin Pickup)")
        service_security = ServiceComponent.objects.get(description__iexact="Origin Security (X-Ray)")
    except ServiceComponent.DoesNotExist as e:
        pytest.fail(f"Could not find seeded service. Have migrations been run? Missing: {e}")
    
    # These are our PGK base-cost services
    service_handling, _ = ServiceComponent.objects.get_or_create(
        description="Import Handling",
        defaults={
            'code': 'HDL_IMP',
            'category': 'DESTINATION', 'unit': 'PER_SHIPMENT', 'cost_type': 'COGS',
            'cost_source': 'BASE_COST', 'base_pgk_cost': Decimal("150.00"),
            'tax_rate': Decimal("0.10") # 10% GST
        }
    )
    service_clearance, _ = ServiceComponent.objects.get_or_create(
        description="Import Customs Clearance",
        defaults={
            'code': 'CLX_IMP',
            'category': 'DESTINATION', 'unit': 'PER_SHIPMENT', 'cost_type': 'COGS',
            'cost_source': 'BASE_COST', 'base_pgk_cost': Decimal("350.00"),
            'tax_rate': Decimal("0.00") # 0% GST
        }
    )
    
    # === 6. Ensure Incoterm Rule exists ===
    # We link all our services to the AIR/IMPORT/EXW rule
    rule, _ = IncotermRule.objects.get_or_create(
        mode='AIR',
        shipment_type='IMPORT',
        incoterm='EXW'
    )
    rule.service_components.set([
        service_freight,
        service_pickup,
        service_fuel,
        service_security,
        service_handling,
        service_clearance
    ])

    return {
        'customer_id': customer.id,
        'contact_id': contact.id,
    }


def test_compute_v3_efm_bne_pom_scenario(setup_v3_golden_test_data):
    """
    A "Golden Test" to verify the end-to-end calculation for a specific
    110kg shipment using the seeded EFM BNE->POM rate card.
    """
    
    # === 1. Define the Request ===
    # This matches our manual calculation
    request_data = V3QuoteRequest(
        customer_id=setup_v3_golden_test_data['customer_id'],
        contact_id=setup_v3_golden_test_data['contact_id'],
        mode="AIR",
        shipment_type="IMPORT",
        incoterm="EXW",
        origin_airport_code="BNE",
        destination_airport_code="POM",
        pieces=1,
        gross_weight_kg=Decimal("110.00"),
        volume_cbm=Decimal("0.1"), # 110kg is chargeable (0.1*167 = 16.7)
        output_currency="USD" # Override profile default
    )
    
    # === 2. Run the Service ===
    service = PricingServiceV3()
    new_quote = service.compute_v3(request_data)
    
    # === 3. Assertions ===
    assert new_quote is not None
    assert new_quote.customer.id == request_data.customer_id
    assert new_quote.origin_code == "BNE"
    assert new_quote.output_currency == "USD"
    
    # Check that saved objects exist
    version = QuoteVersion.objects.get(quote=new_quote, version_number=1)
    total = QuoteTotal.objects.get(quote_version=version)
    lines = list(QuoteLine.objects.filter(quote_version=version).order_by('service_component__description'))
    
    assert total.has_missing_rates is False
    assert len(lines) == 6 # We expecting 6 service lines
    
    # --- "Golden" Value Assertions ---
    # These values are pre-calculated manually based on the test setup data.
    
    # FX Rates Used:
    # Cost (AUD->PGK): tt_buy=2.20, caf=2%. Rate = 2.20 * (1 + 0.02) = 2.244
    # Sell (PGK->USD): tt_sell=0.30, buf=1%. Rate = 0.30 * (1 - 0.01) = 0.297
    # Margin: 30%. Sell = Cost / (1 - 0.30) = Cost / 0.70
    
    # Helper to find a line
    def get_line(name):
        found = [l for l in lines if l.service_component.description == name]
        assert len(found) > 0, f"Could not find line: {name}"
        return found[0]

    # Line 1: Freight (AUD)
    # 110kg @ $6.75/kg (BNE +100kg tier) = 742.50 AUD
    # Cost_PGK = 742.50 / 2.244 = 330.88 PGK
    # Sell_PGK = 330.88 / 0.70 = 472.69 PGK
    # Sell_USD = 472.69 * 0.297 = 140.38 USD
    line_frt = get_line("Freight")
    assert line_frt.cost_fcy == Decimal("742.50")
    assert line_frt.cost_pgk == Decimal("330.88")
    assert line_frt.sell_pgk == Decimal("472.69")
    assert line_frt.sell_fcy_incl_gst == Decimal("140.38") # 0% tax

    # Line 2: Fuel Surcharge (Origin Pickup) (% of Pickup)
    # Base service (Pickup) cost is 37.88 PGK (see below)
    # Cost_PGK = 37.88 * 20% = 7.58 PGK
    # Sell_PGK = 7.58 / 0.70 = 10.83 PGK
    # Sell_USD = 10.83 * 0.297 = 3.22 USD
    line_fuel = get_line("Fuel Surcharge (Origin Pickup)")
    assert line_fuel.cost_pgk == Decimal("7.58")
    assert line_fuel.sell_pgk == Decimal("10.83")
    assert line_fuel.sell_fcy_incl_gst == Decimal("3.22") # 0% tax

    # Line 3: Import Customs Clearance (PGK)
    # Cost_PGK = 350.00 PGK (from BASE_COST)
    # Sell_PGK = 350.00 / 0.70 = 500.00 PGK
    # Sell_USD = 500.00 * 0.297 = 148.50 USD
    line_clx = get_line("Import Customs Clearance")
    assert line_clx.cost_pgk == Decimal("350.00")
    assert line_clx.sell_pgk == Decimal("500.00")
    assert line_clx.sell_fcy_incl_gst == Decimal("148.50") # 0% tax
    
    # Line 4: Import Handling (PGK)
    # Cost_PGK = 150.00 PGK (from BASE_COST)
    # Sell_PGK = 150.00 / 0.70 = 214.29 PGK
    # Sell_PGK_GST = 214.29 * 1.10 = 235.72 PGK
    # Sell_USD_GST = 235.72 * 0.297 = 70.00 USD
    line_hdl = get_line("Import Handling")
    assert line_hdl.cost_pgk == Decimal("150.00")
    assert line_hdl.sell_pgk == Decimal("214.29")
    assert line_hdl.sell_pgk_incl_gst == Decimal("235.72")
    assert line_hdl.sell_fcy_incl_gst == Decimal("70.00") # 10% tax

    # Line 5: Origin Pickup (AUD)
    # 110kg @ $0.26/kg = 28.60 AUD. Min $85.00.
    # Cost_AUD = 85.00 AUD
    # Cost_PGK = 85.00 / 2.244 = 37.88 PGK
    # Sell_PGK = 37.88 / 0.70 = 54.11 PGK
    # Sell_USD = 54.11 * 0.297 = 16.07 USD
    line_pic = get_line("Origin Pickup")
    assert line_pic.cost_fcy == Decimal("85.00")
    assert line_pic.cost_pgk == Decimal("37.88")
    assert line_pic.sell_pgk == Decimal("54.11")
    assert line_pic.sell_fcy_incl_gst == Decimal("16.07") # 0% tax

    # Line 6: Origin Security (X-Ray) (AUD)
    # 110kg @ $0.36/kg = 39.60 AUD. Min $70.00.
    # Cost_AUD = 70.00 AUD
    # Cost_PGK = 70.00 / 2.244 = 31.19 PGK
    # Sell_PGK = 31.19 / 0.70 = 44.56 PGK
    # Sell_USD = 44.56 * 0.297 = 13.23 USD
    line_sec = get_line("Origin Security (X-Ray)")
    assert line_sec.cost_fcy == Decimal("70.00")
    assert line_sec.cost_pgk == Decimal("31.19")
    assert line_sec.sell_pgk == Decimal("44.56")
    assert line_sec.sell_fcy_incl_gst == Decimal("13.23") # 0% tax

    # === Final Total Assertion ===
    # Total = 140.38 + 3.22 + 148.50 + 70.00 + 16.07 + 13.23
    # Total = 391.40 USD
    assert total.total_sell_fcy_incl_gst == Decimal("391.40")
    assert total.total_sell_fcy_currency == "USD"
