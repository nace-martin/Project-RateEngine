import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from unittest.mock import patch
from django.db import connection
from django.db.utils import OperationalError

class HealthCheckTests(APITestCase):
    def test_liveness_endpoint(self):
        """Liveness should return 200 without checking DB."""
        url = reverse('core:health-liveness')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'ok'
        assert data['check_type'] == 'liveness'
        assert data['service'] == 'rateengine-backend'
        assert 'timestamp' in data

    def test_readiness_endpoint_success(self):
        """Readiness should return 200 when DB is up."""
        url = reverse('core:health-readiness')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['status'] == 'ok'
        assert data['check_type'] == 'readiness'
        assert data['dependencies']['database'] == 'ok'

    @patch('django.db.backends.utils.CursorWrapper.execute')
    def test_readiness_endpoint_db_failure(self, mock_execute):
        """Readiness should return 503 when DB is down."""
        mock_execute.side_effect = OperationalError("DB is down")
        
        url = reverse('core:health-readiness')
        # We need to ensure we are testing the actual view logic
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data['status'] == 'unavailable'
        assert data['dependencies']['database'] == 'unavailable'

    def test_legacy_health_endpoint_compatibility(self):
        """Legacy /api/health/ should still work and include DB status."""
        url = reverse('core:health-check')
        response = self.client.get(url)
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data['check_type'] == 'combined'
        assert 'database' in data
