from decimal import Decimal
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

