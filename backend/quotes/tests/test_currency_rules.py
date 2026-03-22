from django.test import SimpleTestCase

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
