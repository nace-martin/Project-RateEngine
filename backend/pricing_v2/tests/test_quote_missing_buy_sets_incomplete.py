import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from unittest.mock import patch

pytestmark = pytest.mark.django_db

@pytest.fixture
def api_client():
    return APIClient()

@pytest.fixture
def authenticated_client(api_client, create_user):
    user = create_user()
    api_client.force_authenticate(user=user)
    return api_client

@patch('pricing_v2.pricing_service_v2.compute_quote_v2')
def test_quote_missing_buy_sets_incomplete(mock_compute_quote_v2, authenticated_client):
    # Mock compute_quote_v2 to return an incomplete quote with missing BUY
    mock_compute_quote_v2.return_value = {
        "invoice_ccy": "PGK",
        "is_incomplete": True,
        "reasons": ["BUY rate bundle missing (placeholder)"],
        "sell_subtotal": 100.0,
        "sell_total": 100.0,
        "sell_lines": [],
        "buy_subtotal": 0.0,
        "buy_total": 0.0,
        "buy_lines": []
    }

    # Assuming a URL for the pricing_v2 quote computation endpoint
    # This might need to be adjusted based on the actual URL configuration
    url = reverse('pricing_v2:compute-quote') # Placeholder URL name

    # Example request payload (adjust as needed)
    payload = {
        "origin_iata": "SYD",
        "dest_iata": "LAX",
        "service_scope": "AIRPORT_AIRPORT",
        "payment_term": "PREPAID",
        "org_id": 1, # Assuming organization with ID 1 exists
        "pieces": [{"weight_kg": 10}]
    }

    response = authenticated_client.post(url, payload, format='json')

    assert response.status_code == status.HTTP_200_OK
    assert response.data['is_incomplete'] is True
    assert "BUY rate bundle missing (placeholder)" in response.data['reasons']
    assert mock_compute_quote_v2.called