import pytest
from unittest.mock import patch
from pricing_v2.pricing_service_v2 import build_buy_menu, select_best_offer
from pricing_v2.dataclasses_v2 import QuoteContext, BuyFee, FeeBasis, Side

class TestPricingServiceV2:
    @pytest.mark.xfail
    def test_selection_logic(self):
        # This test will fail until the selection logic is implemented
        assert False

    @patch('pricing_v2.adapters.ratecard_adapter.resolve_currency_and_fee_scope')
    def test_a2d_collect_shipment_pricing(self, mock_resolve):
        # Arrange
        mock_resolve.return_value = ('PGK', 'DESTINATION_ONLY_COLLECT', 'test')
        ctx = QuoteContext(
            scope="A2D",
            payment_term="COLLECT",
            origin_iata="LAE",
            dest_iata="POM",
            pieces=[{"weight_kg": 100, "length_cm": 50, "width_cm": 50, "height_cm": 50}]
        )

        # Act
        buy_menu = build_buy_menu(context=ctx, adapters=["ratecard"])

        # Assert
        assert len(buy_menu.offers) == 1
        offer = buy_menu.offers[0]

        assert offer.lane.origin == "LAE"
        assert offer.lane.dest == "POM"
        assert offer.ccy == "PGK"
        assert offer.provenance.ref == "2025_A2D_PGK_COLLECT.html"

        # Check for a few specific fees
        clearance_fee = next((f for f in offer.fees if f.code == "CLEAR"), None)
        assert clearance_fee is not None
        assert clearance_fee.basis == FeeBasis.PER_SHIPMENT
        assert clearance_fee.rate == 300.0

        cartage_fee = next((f for f in offer.fees if f.code == "CARTAGE"), None)
        assert cartage_fee is not None
        assert cartage_fee.basis == FeeBasis.PER_KG
        assert cartage_fee.rate == 1.5
        assert cartage_fee.minimum == 95.0

        fuel_fee = next((f for f in offer.fees if f.code == "FUEL_PCT"), None)
        assert fuel_fee is not None
        assert fuel_fee.basis == FeeBasis.PERCENT_OF_BASE
        assert fuel_fee.rate == 0.10

    @patch('pricing_v2.adapters.ratecard_adapter.resolve_currency_and_fee_scope')
    def test_d2a_collect_shipment_pricing(self, mock_resolve):
        # Arrange
        mock_resolve.return_value = ('AUD', 'ORIGIN_ONLY_D2A', 'test')
        ctx = QuoteContext(
            scope="D2A",
            payment_term="COLLECT",
            origin_iata="BNE",
            dest_iata="POM",
            pieces=[{"weight_kg": 100, "length_cm": 50, "width_cm": 50, "height_cm": 50}]
        )

        # Act
        buy_menu = build_buy_menu(context=ctx, adapters=["ratecard"])

        # Assert
        assert len(buy_menu.offers) == 1
        offer = buy_menu.offers[0]

        assert offer.lane.origin == "BNE"
        assert offer.lane.dest == "POM"
        assert offer.ccy == "AUD"
        assert offer.provenance.ref == "2025_D2A_AUD_BNE_POM.html"

        # Check for a few specific fees
        pickup_fee = next((f for f in offer.fees if f.code == "PICKUP"), None)
        assert pickup_fee is not None
        assert pickup_fee.basis == FeeBasis.PER_KG
        assert pickup_fee.rate == 0.26
        assert pickup_fee.minimum == 85.0

        export_doc_fee = next((f for f in offer.fees if f.code == "EXPORT_DOC"), None)
        assert export_doc_fee is not None
        assert export_doc_fee.basis == FeeBasis.FLAT
        assert export_doc_fee.rate == 80.0
