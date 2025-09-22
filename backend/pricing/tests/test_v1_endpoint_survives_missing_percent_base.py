import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

class V1EndpointSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        U = get_user_model()
        cls.user = U.objects.create_user(username="v1safe", password="x")
        cls.token, _ = Token.objects.get_or_create(user=cls.user)

    def setUp(self):
        self.c = Client()
        self.h = {"HTTP_AUTHORIZATION": f"Token {self.token.key}"}

    def test_compute_does_not_crash(self):
        """Even if some sell items are percent-of a missing code, the endpoint must not 500."""
        body = {
            "mode": "AIR",
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "scope": "A2D",
            "payment_term": "PREPAID",
            "commodity": "GCR",
            "pieces": [{"weight_kg": 81}],
        }
        r = self.c.post("/api/quote/compute",
                           data=json.dumps(body),
                           content_type="application/json",
                           **self.h)
        assert r.status_code != 500, r.content
        assert r.status_code in (200, 400), r.status_code