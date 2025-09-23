import pytest
from backend.pricing_v2.pricing_service_v2 import PricingServiceV2

class MockQuoteRequest:
    def __init__(self, payment_terms, origin_country_currency, destination_country_currency, service_scope, direction):
        self.payment_terms = payment_terms
        self.origin_country_currency = origin_country_currency
        self.destination_country_currency = destination_country_currency
        self.service_scope = service_scope
        self.direction = direction

def test_prepaid_a2d_import():
    quote_request = MockQuoteRequest(
        payment_terms="PREPAID",
        origin_country_currency="AUD",
        destination_country_currency="PGK",
        service_scope="A2D",
        direction="IMPORT"
    )
    pricing_service = PricingServiceV2(quote_request)
    final_quote = pricing_service.price_quote()

    assert final_quote["totals"]["invoice_ccy"] == "AUD"
    assert "CUSTOMS_CLEARANCE" in final_quote["sell_lines"]
    assert "TERMINAL_HANDLING" in final_quote["sell_lines"]
    assert "DELIVERY" in final_quote["sell_lines"]

def test_collect_a2d_import():
    quote_request = MockQuoteRequest(
        payment_terms="COLLECT",
        origin_country_currency="AUD",
        destination_country_currency="PGK",
        service_scope="A2D",
        direction="IMPORT"
    )
    pricing_service = PricingServiceV2(quote_request)
    final_quote = pricing_service.price_quote()

    assert final_quote["totals"]["invoice_ccy"] == "PGK"
    assert "CUSTOMS_CLEARANCE" in final_quote["sell_lines"]
    assert "TERMINAL_HANDLING" in final_quote["sell_lines"]
    assert "DELIVERY" in final_quote["sell_lines"]