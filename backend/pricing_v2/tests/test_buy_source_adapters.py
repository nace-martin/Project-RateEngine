import pytest
from pricing_v2.dataclasses_v2 import QuoteContext
from pricing_v2.pricing_service_v2 import build_buy_menu, select_best_offer
from pricing_v2.types_v2 import OrgType, ProvenanceType

# Define which fee codes belong to which side of the journey
ORIGIN_FEES = {"AWB", "DOC", "SCREEN", "PICKUP", "CTO_ORIGIN", "DG"}
DEST_FEES   = {"CLEAR", "AGENCY", "DOC_DEST", "HANDLING", "CTO_DEST", "CARTAGE", "FUEL_PCT"}

def _ctx(**kw):
    """Helper to build a realistic QuoteContext for testing."""
    return QuoteContext(
        mode="AIR",
        scope=kw.get("scope", "A2A"),
        payment_term=kw.get("pt", "COLLECT"),
        origin_iata=kw.get("o", "POM"),
        dest_iata=kw.get("d", "BNE"),
        pieces=[{
            "weight_kg": kw.get("kg", 100),
            "l_cm": kw.get("l", 0), "w_cm": kw.get("w", 0), "h_cm": kw.get("h", 0),
        }],
        commodity="GCR",
        payer=kw.get("payer")
    )

def _spot_ctx(**kw):
    """Helper to build a realistic QuoteContext for testing with a spot offer."""
    return QuoteContext(
        mode="AIR",
        scope=kw.get("scope", "A2A"),
        payment_term=kw.get("pt", "COLLECT"),
        origin_iata=kw.get("o", "POM"),
        dest_iata=kw.get("d", "BNE"),
        pieces=[{
            "weight_kg": kw.get("kg", 100),
            "l_cm": kw.get("l", 0), "w_cm": kw.get("w", 0), "h_cm": kw.get("h", 0),
        }],
        commodity="GCR",
        payer=kw.get("payer"),
        spot_offers=[
            {
                "ccy": "USD",
                "min_kg": 50,
                "af_per_kg": 5.5,
                "min_charge": 500,
                "fees": {
                    "AWB": 50,
                    "SCREEN": 20
                },
                "valid_from": "2025-01-01",
                "valid_to": "2025-12-31"
            }
        ]
    )

def _fee_codes(offer):
    """Helper to get a set of fee codes from a BuyOffer."""
    return {f.code for f in (offer.fees or [])}

def test_export_a2a_png_shipper_pom_to_bne_100kg():
    """
    Tests EXPORT A2A for a PNG_SHIPPER audience.
    Expects: PGK export card to be selected and ONLY origin-side fees.
    """
    ctx = _ctx(scope="A2A", pt="PREPAID", o="POM", d="BNE", kg=100, payer={"org_type": OrgType.PNG_SHIPPER, "country_iso2": "PG"})
    menu = build_buy_menu(ctx, adapters=["ratecard"])
    offer = select_best_offer(menu)

    assert offer is not None, "Should find a PGK export card offer"
    assert offer.ccy == "PGK"
    assert offer.lane.origin == "POM"

    codes = _fee_codes(offer)
    assert codes & ORIGIN_FEES, "Expected origin-side fees to be present"
    assert not (codes & DEST_FEES), "Destination-side fees must NOT be present on an export A2A quote"

def test_import_a2d_collect_bne_to_pom_volumetric():
    """
    Tests IMPORT A2D COLLECT (PGK) with volumetric weight.
    Expects: PGK A2D card, and ONLY destination-side fees.
    """
    # These dimensions will create a volumetric weight of ~112kg
    ctx = _ctx(scope="A2D", pt="COLLECT", o="BNE", d="POM", kg=90, l=120, w=80, h=70)
    menu = build_buy_menu(ctx, adapters=["ratecard"])
    offer = select_best_offer(menu)

    assert offer is not None, "Should find a PGK destination services offer"
    assert offer.ccy == "PGK"
    assert offer.lane.origin == "BNE"

    codes = _fee_codes(offer)
    assert codes & DEST_FEES, "Expected destination-side fees to be present"
    assert not (codes & ORIGIN_FEES), "Origin-side fees must NOT be present on an import A2D quote"

def test_incomplete_when_no_matching_card():
    """
    Tests that the service does not crash when no matching rate card is found.
    It should return an empty menu.
    """
    ctx = _ctx(o="XXX", d="YYY", payer={"org_type": OrgType.OVERSEAS_AGENT, "country_iso2": "US"})
    menu = build_buy_menu(ctx, adapters=["ratecard"])
    offer = select_best_offer(menu)
    assert offer is None, "Should return None when no offer is found"

def test_spot_adapter():
    """
    Tests the SpotAdapter.
    Expects: A BuyOffer created from the spot_offers in the QuoteContext.
    """
    ctx = _spot_ctx(o="LHR", d="JFK")
    menu = build_buy_menu(ctx, adapters=["spot"])
    offer = select_best_offer(menu)

    assert offer is not None, "Should find a spot offer"
    assert offer.ccy == "USD"
    assert offer.lane.origin == "LHR"
    assert offer.lane.dest == "JFK"
    assert offer.provenance.type == ProvenanceType.SPOT
    codes = _fee_codes(offer)
    assert "AWB" in codes
    assert "SCREEN" in codes