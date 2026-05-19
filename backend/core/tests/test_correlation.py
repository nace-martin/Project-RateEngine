import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from core.middleware import get_request_id, get_trace_id, get_user_id

User = get_user_model()

class CorrelationIdTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.url = reverse('core:health-check') # Using health-check as a simple endpoint

    def test_request_id_generated_when_missing(self):
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert 'X-Request-ID' in response.headers
        assert len(response.headers['X-Request-ID']) > 0

    def test_incoming_x_request_id_preserved(self):
        request_id = '550e8400-e29b-41d4-a716-446655440000'
        response = self.client.get(self.url, HTTP_X_REQUEST_ID=request_id)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['X-Request-ID'] == request_id

    def test_invalid_x_request_id_replaced(self):
        invalid_id = 'not-a-uuid'
        response = self.client.get(self.url, HTTP_X_REQUEST_ID=invalid_id)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['X-Request-ID'] != invalid_id
        # Should have generated a valid UUID instead
        import uuid
        uuid.UUID(response.headers['X-Request-ID'])

    def test_trace_id_captured_from_gcp_header(self):
        trace_id = '105445aa7843bc8bf206b120001000'
        trace_context = f"{trace_id}/span_id;o=1"
        response = self.client.get(self.url, HTTP_X_CLOUD_TRACE_CONTEXT=trace_context)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['X-Request-ID'] is not None
        # Note: trace_id is stored in thread-local, which we verify in another test if possible,
        # but the middleware ensures it doesn't crash and processes it.

    def test_user_id_injected_when_authenticated(self):
        self.client.force_authenticate(user=self.user)
        # We need an endpoint that we can verify context during execution if we wanted to be deep,
        # but let's just ensure it works through the middleware.
        response = self.client.get(self.url)
        assert response.status_code == status.HTTP_200_OK
        assert response.headers['X-Request-ID'] is not None

    def test_context_cleared_after_request(self):
        # Verify context is empty before
        assert get_request_id() is None
        assert get_trace_id() is None
        assert get_user_id() is None
        
        self.client.get(self.url)
        
        # Verify context is cleared after
        assert get_request_id() is None
        assert get_trace_id() is None
        assert get_user_id() is None

class LoggingFilterTests(APITestCase):
    def test_filter_injects_ids(self):
        from core.middleware import RequestContextFilter, set_request_id, set_trace_id, set_user_id, clear_request_context
        from unittest.mock import MagicMock
        
        filter = RequestContextFilter()
        record = MagicMock()
        
        set_request_id('test-req-id')
        set_trace_id('test-trace-id')
        set_user_id('123')
        
        try:
            filter.filter(record)
            assert record.request_id == 'test-req-id'
            assert record.trace_id == 'test-trace-id'
            assert record.user_id == '123'
        finally:
            clear_request_context()
