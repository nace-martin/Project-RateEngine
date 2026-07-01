import pytest
from decimal import Decimal
from quotes.services.document_region_diagnostics import detect_regions

IMPORT_AIR_CHARGES_FIXTURE = """
IMPORT AIR CHARGES

Description\t\tAmount (SGD\t
Terminal Fee\t\t35\tmin or 0.25 per KGS\t
Agent Clearance Fee\t\t35\tmin or 0.25 per KGS\t
Clear from agent warehouse\t\t35\tmin or 0.25 per KGS\t(If Applicable)
Airline Doc Fee\t\t15\tper AWB\t
Cargo Terminal Collection Fee\t\t10\tmin or 0.04 per KGS\t
Permit\t\t50\tper set (max 5 lines, thereafter @ sgd 2 / line)\t
Transport\t\t105\tmin or 0.12 per KGS\t
Fuel Surcharge\t\t5\tmin or 0.02 per KGS\t
CMD Fee\t\t20\tper shpt\t
Handling\t\t50\tper shpt\t
DNATA Imp Processing Fee\t\t10\tper shpt\t(If Applicable)
Labour\t\t75\tper man\t
Tailgate Truck\t\t135\tper trip (if applicable) or 0.12 per KGS\t
Service Fee (if via LH/AF/KLM)\t\t12\tper shpt\t(If Applicable)
Import GST to be 9% of Commercial Invoice\t\t\t
"""

HKG_POM_FIXTURE = """
PCS\tG.W\tVolume\tC.W.\tDensity Ratio
3\t1648.0\t2.335\t1648 Kgs\t1:706\t1:1
Booking receipt cut off day\t\t10-Mar\tValidity day\t15-Mar

POL\tPOD\tService level\tATA\tWeight Break\tAirfreight Rate
HKG\tPOM\tDIRECT FLIGHT\tETD D1/3/5/7\t+ 1000 KG\tUSD 7.46 /KG

Above rate apply for mentioned Shipment figure , Cargo Ratio for General / Non-DG cargo only.

HK Gateway charges\tUSD0.35/KG Or Min USD80.00
Cargo screening fee\tUSD0.13/KG or Min USD20.00
Gateway handling fee\tUSD47.00 per shipment

+ Linehaul from Guangzhou Air CFS to Hong Kong AIR WHS Cross-board trucking charges USD0.24/KG or min USD298.00
+ Customs clearance charges: USD52.00 /set(if need ,shipper should provide full set customs clearance docs)
+ Unloading service at HK warehouse: USD0.05/Kg (min: USD38.00/shpt)
"""

CONDITIONAL_LAYOUT_WITH_SIGNATURE_FIXTURE = """
Description\tAmount (SGD)\tUnit\tNote
Clear from agent warehouse\t35\tmin or 0.25 per KGS\t(If Applicable)
Airline Doc Fee\t15\tper AWB\t
DNATA Imp Processing Fee\t10\tper shpt\t(If Applicable)
Tailgate Truck\t135\tper trip (if applicable) or 0.12 per KGS\t

Please contact our agent for any questions.
Email: support@expressfreight.com
Tel: +65 6123 4567
"""

def test_import_air_charges_diagnostics():
    regions = detect_regions(IMPORT_AIR_CHARGES_FIXTURE)
    assert len(regions) >= 1
    
    charges_table = None
    for r in regions:
        if r.detected_region_type == "charges_table":
            charges_table = r
            break
            
    assert charges_table is not None
    assert "charges_table" == charges_table.detected_region_type
    assert charges_table.confidence >= 0.8
    assert "SGD" == charges_table.inherited_context_candidates.get("currency")
    
    # Assert warnings are generated for merged cells / uneven column counts
    assert len(charges_table.warnings) > 0
    assert any("alignment" in w or "merged" in w for w in charges_table.warnings)
    
    # Assert adjacent cells/notes preserved
    assert "If Applicable" in charges_table.raw_text
    assert "Import GST" in charges_table.raw_text
    assert "per set" in charges_text(charges_table.raw_text)

def test_hkg_pom_diagnostics():
    regions = detect_regions(HKG_POM_FIXTURE)
    
    # Expect shipment_context_table, freight_rate_table, notes_terms_block, free_text_charge_block
    region_types = [r.detected_region_type for r in regions]
    assert "shipment_context_table" in region_types
    assert "freight_rate_table" in region_types
    assert "free_text_charge_block" in region_types
    
    # Assert airfreight rate and weight break inherited
    freight_table = next(r for r in regions if r.detected_region_type == "freight_rate_table")
    assert freight_table.inherited_context_candidates.get("pol") == "HKG"
    assert freight_table.inherited_context_candidates.get("pod") == "POM"
    assert freight_table.inherited_context_candidates.get("airfreight_rate") == "7.46"
    assert freight_table.inherited_context_candidates.get("weight_break") == "+ 1000"

    # Gateway charges detected as separate free-text charge block
    free_text_blocks = [r for r in regions if r.detected_region_type == "free_text_charge_block"]
    assert any("HK Gateway charges" in b.raw_text for b in free_text_blocks)
    assert any("Customs clearance charges" in b.raw_text for b in free_text_blocks)

def test_conditional_layout_with_signature():
    regions = detect_regions(CONDITIONAL_LAYOUT_WITH_SIGNATURE_FIXTURE)
    
    region_types = [r.detected_region_type for r in regions]
    assert "charges_table" in region_types
    assert "signature_or_contact_block" in region_types
    
    contact_block = next(r for r in regions if r.detected_region_type == "signature_or_contact_block")
    assert "support@expressfreight.com" in contact_block.raw_text
    assert "+65 6123 4567" in contact_block.raw_text

def charges_text(text: str) -> str:
    return text
