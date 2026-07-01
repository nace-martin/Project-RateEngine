from decimal import Decimal
from unittest.mock import patch
import pytest
from quotes.services.table_diagnostics import (
    detect_probable_table_blocks,
    detect_column_headers,
    parse_table_text_to_intermediate,
)

CARRIER_RATE_SHEET_FIXTURE = """
EXPORT AKL AIRFREIGHT
Charge Description        Currency        Unit        Minimum    Per Unit
Airfreight AKL – POM via PX(BNE)    NZD    per KG    315.00    7.30
PX AWB FEE    NZD    Per AWB    25.00    -

EXPORT
Charge Description        Currency        Unit        Minimum    Per Unit
Documentation Fee    NZD    per AWB    60.00
AWB Fee    NZD    per AWB    25.00
Compliance Fee    NZD    per AWB    15.00
Airport Security Fee    NZD    KG    25.00    0.10
Terminal Handling Fee    NZD    KG    65.00    0.22
Air Transfer Fee    NZD    KG    30.00    0.15
Admin Fee    NZD    per AWB    37.50
Customs Clearance    NZD    per Entry    55.00
EDI Fee    NZD    per Entry    10.00
Pick Up - metro area    NZD    KG    35.00    0.32
Fuel Surcharge    22.00%

Security Screening
Charge Description        Currency        Unit        Minimum    Per Unit
*X-ray    NZD    KG    45.00    0.25
*Additional Screening    per shipment    POA
*Subject to additional security screening (Canine / Swab) if required.
**Screening will only be done if required by airline or customs.
"""

def test_detect_probable_table_blocks():
    blocks = detect_probable_table_blocks(CARRIER_RATE_SHEET_FIXTURE)
    # Proves we split distinct tabular areas
    assert len(blocks) >= 3

def test_detect_column_headers():
    headers = ["Charge Description", "Currency", "Unit", "Minimum", "Per Unit"]
    indices = detect_column_headers(headers)
    assert indices["description"] == 0
    assert indices["currency"] == 1
    assert indices["unit"] == 2
    assert indices["minimum"] == 3
    assert indices["rate"] == 4

def test_parse_table_text_to_intermediate():
    results = parse_table_text_to_intermediate(CARRIER_RATE_SHEET_FIXTURE)
    
    # Check total lines parsed
    assert len(results) >= 14
    
    # Map by raw_label for easy checks
    res_map = {r.raw_label: r for r in results}
    
    # Assertions proving the diagnostic layer detects:
    # 1. Airfreight AKL-POM via PX(BNE): NZD, per KG, min 315.00, rate 7.30
    af = res_map["Airfreight AKL – POM via PX(BNE)"]
    assert af.section_context == "EXPORT AKL AIRFREIGHT"
    assert af.currency_hint == "NZD"
    assert af.unit_hint == "per_kg"
    assert af.min_amount == Decimal("315.00")
    assert af.rate_per_unit == Decimal("7.30")
    assert af.is_conditional is False
    assert af.is_poa is False
    
    # 2. PX AWB Fee: NZD, per AWB, min 25.00
    px_awb = res_map["PX AWB FEE"]
    assert px_awb.section_context == "EXPORT AKL AIRFREIGHT"
    assert px_awb.currency_hint == "NZD"
    assert px_awb.unit_hint == "per_awb"
    assert px_awb.min_amount == Decimal("25.00")
    assert px_awb.rate_per_unit is None
    
    # 3. Documentation Fee: NZD, per AWB, min 60.00
    doc = res_map["Documentation Fee"]
    assert doc.section_context == "EXPORT"
    assert doc.currency_hint == "NZD"
    assert doc.unit_hint == "per_awb"
    assert doc.min_amount == Decimal("60.00")
    assert doc.rate_per_unit is None
    
    # 4. Pick Up - metro area: NZD, KG, min 35.00, rate 0.32
    pu = res_map["Pick Up - metro area"]
    assert pu.section_context == "EXPORT"
    assert pu.currency_hint == "NZD"
    assert pu.unit_hint == "per_kg"
    assert pu.min_amount == Decimal("35.00")
    assert pu.rate_per_unit == Decimal("0.32")
    
    # 5. Fuel Surcharge: percentage 22.00
    fuel = res_map["Fuel Surcharge"]
    assert fuel.section_context == "EXPORT"
    # Surcharge row unit/value detection
    assert fuel.percentage == Decimal("22.00")
    
    # 6. X-ray: NZD, KG, min 45.00, rate 0.25, conditional/security context
    xray = res_map["*X-ray"]
    assert xray.section_context == "Security Screening"
    assert xray.currency_hint == "NZD"
    assert xray.unit_hint == "per_kg"
    assert xray.min_amount == Decimal("45.00")
    assert xray.rate_per_unit == Decimal("0.25")
    assert xray.is_conditional is True
    
    # 7. Additional Screening: POA, conditional/security context
    add = res_map["*Additional Screening"]
    assert add.section_context == "Security Screening"
    assert add.is_poa is True
    assert add.is_conditional is True
    assert "airline or customs" in add.raw_notes.lower()


def test_table_intake_produces_normalized_candidates():
    # We call parse_rate_quote_text directly with the rate sheet text
    from quotes.ai_intake_service import parse_rate_quote_text
    
    result = parse_rate_quote_text(CARRIER_RATE_SHEET_FIXTURE, source_type="TEXT")
    
    # Assert result is populated and has normalized charges
    assert result.quote_input is not None
    
    # Check that we built final SpotChargeLine items
    final_lines = result.lines
    assert len(final_lines) >= 14
    
    def find_line(sub: str):
        for l in final_lines:
            match_str = f"{l.description or ''} {l.original_raw_label or ''}".lower()
            if sub.lower() in match_str:
                return l
        raise KeyError(f"Could not find charge line matching: {sub}")

    # 1. Airfreight AKL-POM via PX(BNE)
    af = find_line("Airfreight")
    assert af.currency == "NZD"
    assert af.unit_basis == "MIN_OR_PER_KG"
    assert af.minimum == Decimal("315.00")
    assert af.rate_per_unit == Decimal("7.30")
    assert af.conditional is False
    
    # 2. PX AWB Fee
    px = find_line("PX AWB")
    assert px.currency == "NZD"
    assert px.unit_basis == "PER_SHIPMENT"
    assert px.amount == Decimal("25.00")
    
    # 3. Documentation Fee
    doc = find_line("Documentation Fee")
    assert doc.currency == "NZD"
    assert doc.unit_basis == "PER_SHIPMENT"
    assert doc.amount == Decimal("60.00")
    
    # 4. Pick Up - metro area
    pu = find_line("Pick Up")
    assert pu.currency == "NZD"
    assert pu.unit_basis == "MIN_OR_PER_KG"
    assert pu.minimum == Decimal("35.00")
    assert pu.rate_per_unit == Decimal("0.32")
    
    # 5. Fuel Surcharge
    fuel = find_line("Fuel Surcharge")
    assert fuel.unit_basis == "PERCENTAGE"
    assert fuel.percentage == Decimal("22.00")
    
    # 6. X-ray
    xray = find_line("X-ray")
    assert xray.currency == "NZD"
    assert xray.unit_basis == "MIN_OR_PER_KG"
    assert xray.minimum == Decimal("45.00")
    assert xray.rate_per_unit == Decimal("0.25")
    assert xray.conditional is True
    
    # 7. Additional Screening
    add = find_line("Additional Screening")
    assert add.conditional is True
    assert add.amount == Decimal("0.00") or add.amount is None or add.minimum == Decimal("0.00")
    assert "poa" in add.notes.lower()


@pytest.mark.django_db
@patch("quotes.ai_intake_service.parse_rate_quote_text")
def test_table_intake_to_spe_charge_lines_mapping(mock_parse):
    from quotes.spot_services import ReplyAnalysisService
    from quotes.spot_models import SpotPricingEnvelopeDB, SPEChargeLineDB
    from quotes.reply_schemas import AssertionCategory
    from quotes.ai_intake_schemas import SpotChargeLine, QuoteInputPayload
    from quotes.ai_intake_service import AIRateIntakePipelineResult
    
    charge_lines = [
        SpotChargeLine(
            bucket="FREIGHT",
            description="Airfreight",
            original_raw_label="Airfreight AKL – POM via PX(BNE)",
            v4_product_code="AIR_FREIGHT",
            currency="NZD",
            unit_basis="MIN_OR_PER_KG",
            minimum=Decimal("315.00"),
            rate_per_unit=Decimal("7.30"),
        ),
        SpotChargeLine(
            bucket="FREIGHT",
            description="PX AWB FEE",
            original_raw_label="PX AWB FEE",
            v4_product_code="AWB_FEE",
            currency="NZD",
            unit_basis="PER_SHIPMENT",
            unit_type="AWB",
            amount=Decimal("25.00"),
        ),
        SpotChargeLine(
            bucket="ORIGIN",
            description="Documentation Fee",
            original_raw_label="Documentation Fee",
            v4_product_code="DOC_FEE",
            currency="NZD",
            unit_basis="PER_SHIPMENT",
            unit_type="AWB",
            amount=Decimal("60.00"),
        ),
        SpotChargeLine(
            bucket="ORIGIN",
            description="Pick Up - metro area",
            original_raw_label="Pick Up - metro area",
            v4_product_code="PICKUP",
            currency="NZD",
            unit_basis="MIN_OR_PER_KG",
            minimum=Decimal("35.00"),
            rate_per_unit=Decimal("0.32"),
        ),
        SpotChargeLine(
            bucket="FREIGHT",
            description="Fuel Surcharge",
            original_raw_label="Fuel Surcharge",
            v4_product_code="FUEL_SURCHARGE",
            currency="NZD",
            unit_basis="PERCENTAGE",
            percentage=Decimal("22.00"),
            percent_applies_to="FREIGHT",
        ),
        SpotChargeLine(
            bucket="ORIGIN",
            description="X-ray",
            original_raw_label="*X-ray",
            v4_product_code="XRAY",
            currency="NZD",
            unit_basis="MIN_OR_PER_KG",
            minimum=Decimal("45.00"),
            rate_per_unit=Decimal("0.25"),
            conditional=True,
        ),
        SpotChargeLine(
            bucket="ORIGIN",
            description="Additional Screening",
            original_raw_label="*Additional Screening",
            v4_product_code="ADDITIONAL_SCREENING",
            currency="NZD",
            unit_basis="PER_SHIPMENT",
            amount=Decimal("0.00"),
            notes="POA - manual review required",
            conditional=True,
        ),
    ]
    
    mock_parse.return_value = AIRateIntakePipelineResult(
        success=True,
        quote_input=QuoteInputPayload(
            quote_currency="NZD",
            charge_lines=charge_lines,
        ),
        quote_currency="NZD",
        model_used="mock-gemini",
    )
    
    # Analyze the rate sheet text (which runs Phase 8B table candidate extraction)
    analysis = ReplyAnalysisService.analyze_with_ai(CARRIER_RATE_SHEET_FIXTURE)
    
    # Assert currency assertion exists
    currency_assertions = [a for a in analysis.assertions if a.category == AssertionCategory.CURRENCY]
    assert len(currency_assertions) >= 1
    assert currency_assertions[0].rate_currency == "NZD"
    
    print("ASSERTIONS:", analysis.assertions)
    # Run mapping to SPE charge lines
    shipment_context = {
        "origin_country": "NZ",
        "destination_country": "PG",
        "missing_components": ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"],
    }
    spe_charges = ReplyAnalysisService.build_spe_charges_from_analysis(
        analysis,
        source_reference="NZ Agent Quote",
        shipment_context=shipment_context,
    )
    print("SPE CHARGES:", spe_charges)
    
    # Assert SPE charge lines have correct properties
    def find_spe(sub: str):
        for c in spe_charges:
            match_str = f"{c.get('description') or ''}".lower()
            if sub.lower() in match_str:
                return c
        raise KeyError(f"Could not find SPE charge line matching: {sub}")
        
    # 1. Airfreight
    af = find_spe("Airfreight")
    assert af["currency"] == "NZD"
    assert af["unit"] == "per_kg"
    assert af["min_amount"] == "315.00"
    assert af["rate"] == "7.30"
    assert af["bucket"] == "airfreight"
    
    # 2. PX AWB Fee
    px = find_spe("PX AWB")
    assert px["currency"] == "NZD"
    assert px["unit"] == "per_shipment"
    assert px["unit_type"] == "shipment"
    assert px["amount"] == "25.00"
    
    # 3. Documentation Fee
    doc = find_spe("Documentation Fee")
    assert doc["currency"] == "NZD"
    assert doc["unit"] == "per_shipment"
    assert doc["unit_type"] == "shipment"
    assert doc["amount"] == "60.00"
    
    # 4. Pick Up
    pu = find_spe("Pick Up")
    assert pu["currency"] == "NZD"
    assert pu["unit"] == "per_kg"
    assert pu["min_amount"] == "35.00"
    assert pu["rate"] == "0.32"
    
    # 5. Fuel Surcharge
    fuel = find_spe("Fuel Surcharge")
    assert fuel["unit"] == "percentage"
    assert fuel["percent"] == "22.00"
    assert fuel["amount"] == "22.00"
    
    # 6. X-ray (conditional)
    xray = find_spe("X-ray")
    assert xray["currency"] == "NZD"
    assert xray["unit"] == "per_kg"
    assert xray["min_amount"] == "45.00"
    assert xray["rate"] == "0.25"
    assert xray["conditional"] is True
    
    # 7. Additional Screening (POA, conditional, notes preserved)
    add = find_spe("Additional Screening")
    assert add["conditional"] is True
    assert add["amount"] == "0.00"
    assert "poa" in add["note"].lower()
    
    # Let's save the charges to a test envelope
    from django.utils import timezone
    envelope = SpotPricingEnvelopeDB.objects.create(
        shipment_context_json=shipment_context,
        expires_at=timezone.now() + timezone.timedelta(days=7),
    )
    
    # Reconcile SPE charges
    from quotes.spot_views import _reconcile_spe_charge_lines
    from django.utils import timezone
    
    # Pre-populate normalized list with Decimals (similar to views.py POST method)
    normalized_incoming = []
    for c in spe_charges:
        normalized_incoming.append({
            **c,
            "amount": Decimal(c["amount"]),
            "min_charge": Decimal(c["min_charge"]) if c.get("min_charge") else None,
            "rate": Decimal(c["rate"]) if c.get("rate") else None,
            "min_amount": Decimal(c["min_amount"]) if c.get("min_amount") else None,
            "max_amount": Decimal(c["max_amount"]) if c.get("max_amount") else None,
            "percent": Decimal(c["percent"]) if c.get("percent") else None,
        })
        
    _reconcile_spe_charge_lines(
        spe_db=envelope,
        existing_lines=[],
        incoming_charges=normalized_incoming,
        entered_by=None,
        entered_at=timezone.now(),
        shipment_context=shipment_context,
    )
    
    # Check that draft charge lines were successfully created in the database
    db_lines = list(envelope.charge_lines.all())
    assert len(db_lines) == 7
    
    def find_db(sub: str):
        for l in db_lines:
            if sub.lower() in l.description.lower():
                return l
        raise KeyError(f"Could not find db line matching: {sub}")
        
    db_af = find_db("Airfreight")
    assert db_af.currency == "NZD"
    assert db_af.unit == "per_kg"
    assert db_af.min_amount == Decimal("315.00")
    assert db_af.rate == Decimal("7.30")
    
    db_fuel = find_db("Fuel Surcharge")
    assert db_fuel.unit == "percentage"
    assert db_fuel.percent == Decimal("22.00")
    
    db_add = find_db("Additional Screening")
    assert db_add.conditional is True
    assert db_add.amount == Decimal("0.00")
    assert "poa" in db_add.note.lower()


SINGAPORE_AGENT_TABLE_FIXTURE = """
IMPORT AIR CHARGES

Description                    Amount (SGD $)

Terminal Fee                   35    min or 0.25 per KGS
Agent Clearance Fee            35    min or 0.25 per KGS
Clear from agent warehouse      35    min or 0.25 per KGS    (If Applicable)
Airline Doc Fee                15    per AWB
Cargo Terminal Collection Fee  10    min or 0.04 per KGS
Permit                         50    per set (max 5 lines, thereafter @ sgd 2 / line)
Transport                      105   min or 0.12 per KGS
Fuel Surcharge                 5     min or 0.02 per KGS
CMD Fee                        20    per shpt
Handling                       50    per shpt
DNATA Imp Processing Fee       10    per shpt    (If Applicable)
Labour                         75    per man
Tailgate Truck                 135   per trip (if applicable) or 0.12 per KGS
Service Fee (if via LH/AF/KLM) 12    per shpt    (If Applicable)
Import GST to be 9% of Commercial Invoice
"""

def test_singapore_agent_table_diagnostics():
    results = parse_table_text_to_intermediate(SINGAPORE_AGENT_TABLE_FIXTURE)
    res_map = {r.raw_label: r for r in results}
    
    # 1. Terminal Fee: SGD, minimum 35, rate 0.25, unit per_kg
    tf = res_map["Terminal Fee"]
    assert tf.currency_hint == "SGD"
    assert tf.min_amount == Decimal("35")
    assert tf.rate_per_unit == Decimal("0.25")
    assert tf.unit_hint == "per_kg"
    assert tf.is_conditional is False
    
    # 2. Clear from agent warehouse: SGD, minimum 35, rate 0.25, unit per_kg, conditional
    cf = res_map["Clear from agent warehouse"]
    assert cf.currency_hint == "SGD"
    assert cf.min_amount == Decimal("35")
    assert cf.rate_per_unit == Decimal("0.25")
    assert cf.unit_hint == "per_kg"
    assert cf.is_conditional is True
    
    # 3. Airline Doc Fee: SGD, 15, per_awb
    adf = res_map["Airline Doc Fee"]
    assert adf.currency_hint == "SGD"
    assert adf.min_amount == Decimal("15")
    assert adf.rate_per_unit is None
    assert adf.unit_hint == "per_awb"
    
    # 4. Permit: SGD, 50, per_set
    permit = res_map["Permit"]
    assert permit.currency_hint == "SGD"
    assert permit.min_amount == Decimal("50")
    assert permit.unit_hint == "per_set"
    
    # 5. Tailgate Truck: SGD, 135, per_trip, conditional
    tt = res_map["Tailgate Truck"]
    assert tt.currency_hint == "SGD"
    assert tt.min_amount == Decimal("135")
    assert tt.rate_per_unit == Decimal("0.12")
    assert tt.unit_hint == "per_trip"
    assert tt.is_conditional is True
    
    # 6. Service Fee: SGD, 12, per_shipment, conditional
    sf = res_map["Service Fee (if via LH/AF/KLM)"]
    assert sf.currency_hint == "SGD"
    assert sf.min_amount == Decimal("12")
    assert sf.unit_hint == "per_shipment"
    assert sf.is_conditional is True


