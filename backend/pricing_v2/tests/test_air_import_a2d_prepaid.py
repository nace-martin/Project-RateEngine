import pytest
from rest_framework.test import APIClient
from pricing.management.commands.seed_bne_to_pom import Command as SeedCommand

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def seed_bne_pom(db):
    SeedCommand().handle()

@pytest.mark.django_db
def test_air_import_a2d_prepaid_quotes_dest_fees_in_aud(api_client, seed_bne_pom):
    payload = {
        "mode": "AIR", "origin_iata": "BNE", "dest_iata": "POM",
        "scope": "A2D", "payment_term": "PREPAID", "commodity": "GCR",
        "pieces": [{"weight_kg": 100}],
    }
    r = api_client.post("/api/quote/compute2", payload, format="json")
    assert r.status_code == 200
    data = r.json()
    assert data["manual_required"] is False
    assert data["totals"]["invoice_ccy"] == "AUD"

    sell_codes = [l["code"] for l in data["sell_lines"]]
    # Must include dest-side fees, not export ones
    assert "CUSTOMS_CLEARANCE" in sell_codes
    assert "CARTAGE_DELIVERY_KG" in sell_codes
    assert "INTERNATIONAL_TERMINAL_FEE" in sell_codes
    assert "PICKUP" not in sell_codes
    assert "X_RAY" not in sell_codes
