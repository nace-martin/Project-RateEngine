from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from .models import Client, RateCard

from rate_engine.engine import calculate_chargeable_weight
from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token


class CalculateChargeableWeightTests(TestCase):
    def test_single_piece_volumetric_greater(self):
        # Volumetric = (60*50*40)/6000 = 20 kg, actual = 12 kg -> pick 20
        pieces = [{"weight": 12, "length": 60, "width": 50, "height": 40}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 20.0, places=3)

    def test_single_piece_actual_greater(self):
        # Volumetric = (30*30*30)/6000 = 4.5 kg, actual = 10 kg -> pick 10
        pieces = [{"weight": 10, "length": 30, "width": 30, "height": 30}]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.0, places=3)

    def test_multiple_pieces_mixed(self):
        # Piece1: vol 20 vs act 12 -> 20
        # Piece2: vol 4.5 vs act 10 -> 10
        # Total = 30
        pieces = [
            {"weight": 12, "length": 60, "width": 50, "height": 40},
            {"weight": 10, "length": 30, "width": 30, "height": 30},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 30.0, places=3)

    def test_missing_dimensions_defaults_to_actual(self):
        # Missing dims -> volumetric 0 -> pick actual only
        pieces = [
            {"weight": 7.2},
            {"weight": 3.3, "length": None, "width": 50, "height": 40},
        ]
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), 10.5, places=3)

    def test_string_inputs_are_handled(self):
        # Values can be strings; ensure parsing works
        pieces = [
            {"weight": "12", "length": "60", "width": "50", "height": "40"},  # 20
            {"weight": "1.5", "length": "10", "width": "10", "height": "10"},  # vol 1.666.. -> 1.666..
        ]
        # Per-piece rule: choose max(actual vs volumetric) per piece, then sum
        expected = 20.0 + max(1.5, ((10*10*10)/6000))
        self.assertAlmostEqual(calculate_chargeable_weight(pieces), expected, places=3)

class QuoteComputeAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.compute_url = reverse('compute-quote')
        # Authenticate via DRF TokenAuth
        User = get_user_model()
        user = User.objects.create_user(username="testuser", password="testpass")
        token = Token.objects.create(user=user)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        Client.objects.create(name="Test Client")
        RateCard.objects.create(
            origin="BNE",
            destination="POM",
            min_charge=100,
            brk_45=5.50,
            brk_100=5.00,
            brk_250=4.50,
            brk_500=4.00,
            brk_1000=3.50,
        )

    def test_compute_quote_api_success(self):
        data = {
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "shipment_type": "EXPORT",
            "service_scope": "AIRPORT_AIRPORT",
            "audience": "PGK_LOCAL",
            "sell_currency": "PGK",
            "pieces": [
                {"weight": 100, "length": 100, "width": 100, "height": 100}
            ]
        }
        response = self.client.post(self.compute_url, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertIn("buy_lines", response.data)
        self.assertIn("sell_lines", response.data)
        self.assertIn("totals", response.data)
        self.assertIn("snapshot", response.data)
        self.assertEqual(response.data["snapshot"]["shipment_type"], "EXPORT")
        self.assertEqual(response.data["snapshot"]["service_scope"], "AIRPORT_AIRPORT")

    def test_compute_quote_api_missing_fields(self):
        data = {
            "origin_iata": "BNE",
            "dest_iata": "POM",
            "audience": "PGK_LOCAL",
            "sell_currency": "PGK",
            "pieces": [
                {"weight": 100, "length": 100, "width": 100, "height": 100}
            ]
        }
        response = self.client.post(self.compute_url, data, format='json')
        self.assertEqual(response.status_code, 400)
        self.assertIn("shipment_type", response.data)
        self.assertIn("service_scope", response.data)
