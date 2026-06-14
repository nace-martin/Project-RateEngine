from decimal import Decimal
import pytest
from quotes.ai_intake_schemas import RawExtractedCharge, NormalizedCharge, ExtractionAuditResult
from quotes.ai_intake_service import parse_rate_quote_text, _extract_pattern_charge_candidates

JENNI_CONLON_EMAIL = """
Hi,

Please see below standard NZ export rates which are applicable for any POM imports on collect basis.

EXPORT AKL AIRFREIGHT:
- Airfreight AKL – POM via PX(BNE): USD 3.50/kg (+100kg)
- PX AWB FEE: USD 50.00/awb
- Fuel Surcharge: USD 1.10/kg (subject to change)
- Security Fee: USD 0.15/kg
- Admin Fee: USD 25.00/shipment
- Pick Up - metro area: USD 85.00/shipment (min 50kg, then USD 0.40/kg thereafter)
- X-ray: USD 15.00/shipment (if applicable)
- Additional Screening: POA (optional)

EXPORT:
- Documentation Fee: NZD 35.00/shipment
- AWB Fee: NZD 25.00/shipment
- Compliance Fee: NZD 15.00/shipment
- Airport Security Fee: NZD 12.50/shipment
- Terminal Handling Fee: NZD 45.00/shipment
- Air Transfer Fee: NZD 20.00/shipment
- Customs Clearance: NZD 85.00/shipment
- EDI Fee: NZD 18.00/shipment
"""


class _FakeGeminiClient:
    def GenerativeModel(self, _model_name):
        return object()


@pytest.mark.django_db
def test_pattern_fallback_extracts_all_jenni_conlon_charges():
    # Verify that the regex-based deterministic fallback alone extracts all 15 expected lines
    raw_candidates = _extract_pattern_charge_candidates(JENNI_CONLON_EMAIL)
    assert len(raw_candidates) >= 15

    labels = {c.raw_label for c in raw_candidates}
    expected_labels = {
        "Airfreight AKL – POM via PX(BNE)",
        "PX AWB FEE",
        "Fuel Surcharge",
        "Security Fee",
        "Admin Fee",
        "Pick Up - metro area",
        "X-ray",
        "Documentation Fee",
        "AWB Fee",
        "Compliance Fee",
        "Airport Security Fee",
        "Terminal Handling Fee",
        "Air Transfer Fee",
        "Customs Clearance",
        "EDI Fee",
    }
    
    # Assert each expected label is in the extracted list
    for label in expected_labels:
        assert any(label in x for x in labels), f"Missing expected label: {label}"


@pytest.mark.django_db
def test_ai_intake_recovers_charges_when_normalization_fails(monkeypatch):
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    # Mock extractor to return empty so we fall back to pattern extraction
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [],
    )
    # Force Normalizer to raise Exception simulating malformed output
    def mock_normalize_failed(*_args, **_kwargs):
        raise RuntimeError("Normalizer failed with malformed JSON: Unterminated string starting at line 4")
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        mock_normalize_failed,
    )

    context = {
        "shipment_type": "IMPORT",
        "origin_code": "AKL",
        "destination_code": "POM",
        "service_scope": "D2D",
        "payment_term": "COLLECT",
        "missing_components": ["ORIGIN_LOCAL", "FREIGHT"]
    }

    result = parse_rate_quote_text(
        JENNI_CONLON_EMAIL,
        context=context,
    )

    # Normalization failed, so success must be False (requiring manual review)
    assert result.success is False
    assert len(result.warnings) > 0
    assert any("AI normalization failed" in w for w in result.warnings)
    
    # We must NOT return raw=0
    assert len(result.raw_extracted_charges) >= 15
    assert len(result.normalized_charges) >= 15

    # Fallback charges must be marked correctly
    for charge in result.normalized_charges:
        assert charge.confidence == "LOW"
        assert charge.v4_product_code == "UNMAPPED"
        
        # Verify classification guardrail:
        # Since this is an IMPORT COLLECT shipment and NZ export sections are being parsed,
        # none of these NZ local charges should be classified as PNG destination charges.
        assert charge.v4_bucket in {"ORIGIN", "FREIGHT"}, f"Charge {charge.original_raw_label} was bucketed as {charge.v4_bucket}"

    # Verify key values preserved
    airfreight = next(c for c in result.normalized_charges if "Airfreight" in c.original_raw_label)
    assert airfreight.unit_basis == "PER_KG"
    assert airfreight.amount == Decimal("3.50")
    assert airfreight.rate_per_unit == Decimal("3.50")
    assert airfreight.currency == "USD"

    awb_fee = next(c for c in result.normalized_charges if "PX AWB FEE" in c.original_raw_label)
    assert awb_fee.unit_basis == "PER_SHIPMENT"
    assert awb_fee.amount == Decimal("50.00")
    assert awb_fee.currency == "USD"

    doc_fee = next(c for c in result.normalized_charges if "Documentation Fee" in c.original_raw_label)
    assert doc_fee.unit_basis == "PER_SHIPMENT"
    assert doc_fee.amount == Decimal("35.00")
    assert doc_fee.currency == "NZD"


JENNI_CONLON_TABULAR_EMAIL = """
Hey Nason

See rates below for this one
Rates valid until July 31st

Please be aware that screening will be applicable for this

EXPORT AKL AIRFREIGHT
Charge Description        Currency        Unit        Minimum    Per Unit (100+ KG)
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
*X-ray    NZD    KG    45.00    0.25
*Additional Screening    per shipment    POA
*Subject to additional security screening (Canine / Swab) if required.
**Screening will only be done if required by airline or customs.
"""


@pytest.mark.django_db
def test_tabular_intake_preserves_table_structure(monkeypatch):
    monkeypatch.setattr(
        "quotes.ai_intake_service.get_gemini_client",
        lambda: _FakeGeminiClient(),
    )
    # Mock extractor to return empty so we fall back to pattern extraction + tabular extraction
    monkeypatch.setattr(
        "quotes.ai_intake_service._extract_raw_charges",
        lambda *_args, **_kwargs: [],
    )
    # Force Normalizer to raise Exception simulating malformed output
    def mock_normalize_failed(*_args, **_kwargs):
        raise RuntimeError("Normalizer failed with malformed JSON")
    monkeypatch.setattr(
        "quotes.ai_intake_service._normalize_charges",
        mock_normalize_failed,
    )

    context = {
        "shipment_type": "IMPORT",
        "origin_code": "AKL",
        "destination_code": "POM",
        "service_scope": "D2D",
        "payment_term": "COLLECT",
        "missing_components": ["ORIGIN_LOCAL", "FREIGHT"]
    }

    result = parse_rate_quote_text(
        JENNI_CONLON_TABULAR_EMAIL,
        context=context,
    )

    assert result.success is False
    assert len(result.raw_extracted_charges) >= 15

    # Map raw extracted charges by label for easy inspection
    raw_map = {c.raw_label: c for c in result.raw_extracted_charges}
    
    # 1. Airfreight AKL – POM via PX(BNE)
    af = raw_map["Airfreight AKL – POM via PX(BNE)"]
    assert af.currency_hint == "NZD"
    assert af.raw_unit == "per KG"
    assert af.raw_minimum == "315.00"
    assert af.raw_rate == "7.30"
    assert af.section_context == "EXPORT AKL AIRFREIGHT"
    
    # 2. PX AWB FEE
    px = raw_map["PX AWB FEE"]
    assert px.currency_hint == "NZD"
    assert px.raw_unit == "Per AWB"
    assert px.raw_minimum == "25.00"
    assert px.raw_rate is None
    
    # 3. Documentation Fee
    doc = raw_map["Documentation Fee"]
    assert doc.currency_hint == "NZD"
    assert doc.raw_unit == "per AWB"
    assert doc.raw_minimum == "60.00"
    
    # 4. AWB Fee
    awb = raw_map["AWB Fee"]
    assert awb.currency_hint == "NZD"
    assert awb.raw_unit == "per AWB"
    assert awb.raw_minimum == "25.00"
    
    # 5. Compliance Fee
    comp = raw_map["Compliance Fee"]
    assert comp.currency_hint == "NZD"
    assert comp.raw_unit == "per AWB"
    assert comp.raw_minimum == "15.00"
    
    # 6. Airport Security Fee
    aps = raw_map["Airport Security Fee"]
    assert aps.currency_hint == "NZD"
    assert aps.raw_unit == "KG"
    assert aps.raw_minimum == "25.00"
    assert aps.raw_rate == "0.10"
    
    # 7. Terminal Handling Fee
    thf = raw_map["Terminal Handling Fee"]
    assert thf.currency_hint == "NZD"
    assert thf.raw_unit == "KG"
    assert thf.raw_minimum == "65.00"
    assert thf.raw_rate == "0.22"
    
    # 8. Air Transfer Fee
    atf = raw_map["Air Transfer Fee"]
    assert atf.currency_hint == "NZD"
    assert atf.raw_unit == "KG"
    assert atf.raw_minimum == "30.00"
    assert atf.raw_rate == "0.15"
    
    # 9. Admin Fee
    admin = raw_map["Admin Fee"]
    assert admin.currency_hint == "NZD"
    assert admin.raw_unit == "per AWB"
    assert admin.raw_minimum == "37.50"
    
    # 10. Customs Clearance
    cc = raw_map["Customs Clearance"]
    assert cc.currency_hint == "NZD"
    assert cc.raw_unit == "per Entry"
    assert cc.raw_minimum == "55.00"
    assert cc.section_context == "EXPORT"
    
    # 11. EDI Fee
    edi = raw_map["EDI Fee"]
    assert edi.currency_hint == "NZD"
    assert edi.raw_unit == "per Entry"
    assert edi.raw_minimum == "10.00"
    assert edi.section_context == "EXPORT"
    
    # 12. Pick Up - metro area
    pu = raw_map["Pick Up - metro area"]
    assert pu.currency_hint == "NZD"
    assert pu.raw_unit == "KG"
    assert pu.raw_minimum == "35.00"
    assert pu.raw_rate == "0.32"
    
    # 13. Fuel Surcharge
    fuel = raw_map["Fuel Surcharge"]
    assert fuel.raw_percentage == "22.00%"
    
    # 14. X-ray
    xray = raw_map["X-ray"]
    assert xray.currency_hint == "NZD"
    assert xray.raw_unit == "KG"
    assert xray.raw_minimum == "45.00"
    assert xray.raw_rate == "0.25"
    assert xray.is_conditional is True
    assert "screening" in xray.raw_notes.lower()
    
    # 15. Additional Screening
    add = raw_map["Additional Screening"]
    assert add.raw_unit == "per shipment"
    assert add.raw_minimum == "POA"
    assert add.is_conditional is True
    assert "airline or customs" in add.raw_notes.lower()

    # Now verify normalized/fallback generation outputs
    norm_map = {n.original_raw_label: n for n in result.normalized_charges}
    
    # Check Airfreight bucket and unit basis
    af_norm = norm_map["Airfreight AKL – POM via PX(BNE)"]
    assert af_norm.v4_bucket == "FREIGHT"
    assert af_norm.unit_basis == "MIN_OR_PER_KG"
    assert af_norm.amount == Decimal("7.30")
    assert af_norm.rate_per_unit == Decimal("7.30")
    assert af_norm.minimum_amount == Decimal("315.00")
    assert af_norm.currency == "NZD"
    
    # Check Customs Clearance is ORIGIN bucket (not destination PNG)
    cc_norm = norm_map["Customs Clearance"]
    assert cc_norm.v4_bucket == "ORIGIN"
    
    # Check EDI Fee is ORIGIN bucket
    edi_norm = norm_map["EDI Fee"]
    assert edi_norm.v4_bucket == "ORIGIN"

    # Check Fuel Surcharge is PERCENTAGE unit basis
    fuel_norm = norm_map["Fuel Surcharge"]
    assert fuel_norm.unit_basis == "PERCENTAGE"
    assert fuel_norm.amount == Decimal("22.00")
    assert fuel_norm.percentage == Decimal("22.00")

    # Check Additional Screening is PER_SHIPMENT with 0.00 for POA
    add_norm = norm_map["Additional Screening"]
    assert add_norm.unit_basis == "PER_SHIPMENT"
    assert add_norm.amount == Decimal("0.00")
