import pytest
from pricing_v2.dataclasses_v2 import QuoteContext
from pricing_v2.pricing_service_v2 import build_buy_menu, select_best_offer
from pricing_v2.types_v2 import AudienceType

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
        audience=kw.get("audience")
    )

def _fee_codes(offer):
    """Helper to get a set of fee codes from a BuyOffer."""
    return {f.code for f in (offer.fees or [])}

@pytest.mark.xfail(reason="RateCardAdapter logic not implemented yet.")
def test_export_a2a_png_shipper_pom_to_bne_100kg():
    """
    Tests EXPORT A2A for a PNG_SHIPPER audience.
    Expects: PGK export card to be selected and ONLY origin-side fees.
    """
    ctx = _ctx(scope="A2A", pt="COLLECT", o="POM", d="BNE", kg=100, audience=AudienceType.PNG_SHIPPER)
    menu = build_buy_menu(ctx, adapters=["ratecard"])
    offer = select_best_offer(menu)

    assert offer is not None, "Should find a PGK export card offer"
    assert offer.ccy == "PGK"
    assert offer.lane.origin == "POM"

    codes = _fee_codes(offer)
    assert codes & ORIGIN_FEES, "Expected origin-side fees to be present"
    assert not (codes & DEST_FEES), "Destination-side fees must NOT be present on an export A2A quote"

@pytest.mark.xfail(reason="RateCardAdapter logic not implemented yet.")
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

@pytest.mark.xfail(reason="Empty menu/incomplete path not wired yet.")
def test_incomplete_when_no_matching_card():
    """
    Tests that the service does not crash when no matching rate card is found.
    It should return an empty menu.
    """
    ctx = _ctx(o="XXX", d="YYY", audience=AudienceType.OVERSEAS_AGENT_NON_AU)
    menu = build_buy_menu(ctx, adapters=["ratecard"])
    offer = select_best_offer(menu)
    assert offer is None, "Should return None when no offer is found"