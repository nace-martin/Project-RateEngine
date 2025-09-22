import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

class CurrencyRoutingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.user = U.objects.create_user(username="t_user", password="x")
        cls.token, _ = Token.objects.get_or_create(user=cls.user)

    def setUp(self):
        self.client = Client()
        self.auth = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def _post_quote(self, payment_term: str):
        body = {
            "mode": "AIR",
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "scope": "A2D",
            "payment_term": payment_term,
            "commodity": "GCR",
            "pieces": [{"weight_kg": 81}],
        }
        return self.client.post(
            "/api/quote/compute2",
            data=json.dumps(body),
            content_type="application/json",
            **self.auth,
        )

    def test_import_a2d_prepaid_invoice_is_aud(self):
        r = self._post_quote("PREPAID")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertIn("totals", data)
        self.assertEqual(data["totals"].get("invoice_ccy"), "AUD")

    def test_import_a2d_collect_invoice_is_pgk(self):
        r = self._post_quote("COLLECT")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertIn("totals", data)
        self.assertEqual(data["totals"].get("invoice_ccy"), "PGK")