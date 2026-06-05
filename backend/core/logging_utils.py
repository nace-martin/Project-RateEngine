import logging
import traceback
from pythonjsonlogger import json as jsonlogger
from django.conf import settings

# --- SIGNAL DEFINITIONS ---
SIGNAL_QUOTE_CREATED = "SIGNAL:QUOTE_CREATED"
SIGNAL_SPOT_TRIGGERED = "SIGNAL:SPOT_TRIGGERED"
SIGNAL_AI_EXTRACTION_FAILED = "SIGNAL:AI_EXTRACTION_FAILED"
SIGNAL_MISSING_RATE = "SIGNAL:MISSING_RATE"
SIGNAL_LOGIN_SUCCESS = "SIGNAL:LOGIN_SUCCESS"
SIGNAL_LOGIN_FAILED = "SIGNAL:LOGIN_FAILED"

logger = logging.getLogger(__name__)

class GCPJSONFormatter(jsonlogger.JsonFormatter):
    """
    Custom JSON formatter for Google Cloud Operations.
    - Maps levelname to severity.
    - Injects serviceContext for Error Reporting.
    - Links request trace context.
    - Masks potential secrets.
    """
    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        
        # 1. GCP Severity mapping
        # https://cloud.google.com/logging/docs/reference/v2/rest/v2/LogEntry#logseverity
        severity_map = {
            'DEBUG': 'DEBUG',
            'INFO': 'INFO',
            'WARNING': 'WARNING',
            'ERROR': 'ERROR',
            'CRITICAL': 'CRITICAL',
        }
        log_record['severity'] = severity_map.get(record.levelname, 'INFO')

        # 2. Trace correlation
        # Cloud Logging uses logging.googleapis.com/trace for correlation
        project_id = getattr(settings, 'GCP_PROJECT_ID', None)
        trace_id = getattr(record, 'trace_id', None)
        if project_id and trace_id:
            log_record['logging.googleapis.com/trace'] = f"projects/{project_id}/traces/{trace_id}"
        
        # 3. Request correlation
        log_record['request_id'] = getattr(record, 'request_id', None)
        log_record['user_id'] = getattr(record, 'user_id', None)

        # 4. Error Reporting metadata
        # Only include for ERROR or higher
        if record.levelno >= logging.ERROR:
            # Service context is required for grouping in GCP Error Reporting
            log_record['serviceContext'] = {
                'service': 'rateengine-backend',
                'version': getattr(settings, 'APP_VERSION', 'unknown'),
            }
            
            # GCP looks for 'stack_trace' or '@type' to trigger Error Reporting
            if record.exc_info:
                log_record['stack_trace'] = "".join(traceback.format_exception(*record.exc_info))
            elif not log_record.get('stack_trace') and record.levelname in ['ERROR', 'CRITICAL']:
                # If no exception info but it's an error, provide a basic stack
                log_record['stack_trace'] = "".join(traceback.format_stack())

        # 5. Masking
        # Simple recursive masking for keys that look like secrets or contain sm://
        self._mask_record(log_record)

    def _mask_record(self, data):
        """Recursively mask potential secrets in the log record."""
        if not isinstance(data, dict):
            return

        sensitive_keys = {'password', 'token', 'secret', 'key', 'authorization'}
        for key, value in data.items():
            if any(s in key.lower() for s in sensitive_keys):
                data[key] = "********"
            elif isinstance(value, str) and value.startswith("sm://"):
                data[key] = "sm://********"
            elif isinstance(value, dict):
                self._mask_record(value)


def log_signal(signal_type: str, message: str, **kwargs):
    """
    Emits a structured SIGNAL log for commercial/operational events.
    """
    log_data = {
        'signal_type': signal_type,
        'commercial_event': True,
        **kwargs
    }
    # We log at INFO level so these aren't treated as errors, 
    # but the prefix allows Log-based Metrics to find them.
    logger.info(f"{signal_type}: {message}", extra=log_data)


def log_exception(message: str, **kwargs):
    """
    Helper to log an exception with extra context for Error Reporting.
    """
    logger.exception(message, extra=kwargs)
