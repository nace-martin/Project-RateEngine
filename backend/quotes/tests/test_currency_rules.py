from types import SimpleNamespace

from django.test import SimpleTestCase

from pricing_v4.adapter import PricingServiceV4Adapter
from quotes.currency_rules import determine_quote_currency


class DetermineQuoteCurrencyTests(SimpleTestCase):
    def test_export_prepaid_to_australia_is_pgk(self):
        currency = determine_quote_currency("EXPORT", "PREPAID", "PG", "AU")
        self.assertEqual(currency, "PGK")

    def test_export_prepaid_non_au_is_pgk(self):
        currency = determine_quote_currency("EXPORT", "PREPAID", "PG", "SG")
        self.assertEqual(currency, "PGK")

    def test_export_collect_non_au_is_usd(self):
        currency = determine_quote_currency("EXPORT", "COLLECT", "PG", "SG")
        self.assertEqual(currency, "USD")

    def test_export_collect_to_australia_is_aud(self):
        currency = determine_quote_currency("EXPORT", "COLLECT", "PG", "AU")
        self.assertEqual(currency, "AUD")

    def test_import_collect_is_pgk(self):
        currency = determine_quote_currency("IMPORT", "COLLECT", "SG", "PG")
        self.assertEqual(currency, "PGK")

    def test_import_prepaid_from_australia_is_aud(self):
        currency = determine_quote_currency("IMPORT", "PREPAID", "AU", "PG")
        self.assertEqual(currency, "AUD")

    def test_import_prepaid_non_au_is_usd(self):
        currency = determine_quote_currency("IMPORT", "PREPAID", "SG", "PG")
        self.assertEqual(currency, "USD")

    def test_domestic_is_pgk(self):
        currency = determine_quote_currency("DOMESTIC", "PREPAID", "PG", "PG")
        self.assertEqual(currency, "PGK")


class PricingServiceV4AdapterCurrencyTests(SimpleTestCase):
    def _adapter_for(self, payment_term, destination_country_code):
        adapter = PricingServiceV4Adapter.__new__(PricingServiceV4Adapter)
        adapter.quote_input = SimpleNamespace(
            shipment=SimpleNamespace(
                shipment_type="EXPORT",
                payment_term=payment_term,
                origin_location=SimpleNamespace(country_code="PG"),
                destination_location=SimpleNamespace(country_code=destination_country_code),
            )
        )
        return adapter

    def test_adapter_export_prepaid_pom_bne_outputs_pgk(self):
        self.assertEqual(self._adapter_for("PREPAID", "AU").get_output_currency(), "PGK")

    def test_adapter_export_prepaid_pom_non_au_outputs_pgk(self):
        self.assertEqual(self._adapter_for("PREPAID", "SG").get_output_currency(), "PGK")

    def test_adapter_export_collect_pom_bne_outputs_aud(self):
        self.assertEqual(self._adapter_for("COLLECT", "AU").get_output_currency(), "AUD")

    def test_adapter_export_collect_pom_non_au_outputs_usd(self):
        self.assertEqual(self._adapter_for("COLLECT", "HK").get_output_currency(), "USD")
