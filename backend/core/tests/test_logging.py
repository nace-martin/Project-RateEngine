import logging
import pytest
from unittest.mock import MagicMock, patch
from core.logging_utils import GCPJSONFormatter, log_signal, SIGNAL_QUOTE_CREATED

class TestGCPJSONFormatter:
    def test_severity_mapping(self):
        formatter = GCPJSONFormatter()
        
        # Test INFO mapping
        record_info = MagicMock(levelname='INFO', levelno=logging.INFO, exc_info=None)
        log_record_info = {}
        formatter.add_fields(log_record_info, record_info, {})
        assert log_record_info['severity'] == 'INFO'
        
        # Test ERROR mapping
        record_error = MagicMock(levelname='ERROR', levelno=logging.ERROR, exc_info=None)
        log_record_error = {}
        formatter.add_fields(log_record_error, record_error, {})
        assert log_record_info['severity'] == 'INFO' # Check original object wasn't mutated globally
        assert log_record_error['severity'] == 'ERROR'

    def test_trace_correlation(self):
        formatter = GCPJSONFormatter()
        record = MagicMock(levelname='INFO', levelno=logging.INFO, exc_info=None, trace_id='trace-123')
        log_record = {}
        
        with patch('django.conf.settings.GCP_PROJECT_ID', 'test-project'):
            formatter.add_fields(log_record, record, {})
            assert log_record['logging.googleapis.com/trace'] == 'projects/test-project/traces/trace-123'

    def test_error_reporting_metadata(self):
        formatter = GCPJSONFormatter()
        # Mock record with exception info
        try:
            raise ValueError("Test Error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
            
        record = MagicMock(levelname='ERROR', levelno=logging.ERROR, exc_info=exc_info)
        log_record = {}
        
        with patch('django.conf.settings.APP_VERSION', '2.0.0'):
            formatter.add_fields(log_record, record, {})
            assert log_record['serviceContext']['service'] == 'rateengine-backend'
            assert log_record['serviceContext']['version'] == '2.0.0'
            assert 'stack_trace' in log_record
            assert 'ValueError: Test Error' in log_record['stack_trace']

    def test_masking_secrets(self):
        formatter = GCPJSONFormatter()
        log_record = {
            'message': 'test',
            'password': 'secret-password',
            'deep': {'token': 'secret-token'},
            'sm_ref': 'sm://my-secret'
        }
        formatter._mask_record(log_record)
        
        assert log_record['password'] == '********'
        assert log_record['deep']['token'] == '********'
        assert log_record['sm_ref'] == 'sm://********'


class TestSignalLogging:
    @patch('core.logging_utils.logger.info')
    def test_log_signal_emits_correct_fields(self, mock_logger_info):
        log_signal(
            SIGNAL_QUOTE_CREATED, 
            "New quote for customer 5", 
            quote_id='q-123', 
            customer_id=5
        )
        
        args, kwargs = mock_logger_info.call_args
        assert f"{SIGNAL_QUOTE_CREATED}: New quote for customer 5" in args[0]
        assert kwargs['extra']['signal_type'] == SIGNAL_QUOTE_CREATED
        assert kwargs['extra']['commercial_event'] is True
        assert kwargs['extra']['quote_id'] == 'q-123'
        assert kwargs['extra']['customer_id'] == 5
