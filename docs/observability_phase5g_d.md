# Phase 5G-D: GCP Ops Integration & Error Reporting

## Overview
This phase integrates RateEngine's structured logging with Google Cloud Operations (formerly Stackdriver). It enables automated **Error Reporting**, improves log correlation via **Cloud Trace**, and introduces a **SIGNAL** standard for commercial and operational metrics.

## Logging Enhancements

### 1. GCP Structured Logging
The `GCPJSONFormatter` (implemented in `backend/core/logging_utils.py`) extends the standard JSON formatter to satisfy GCP-specific requirements:
- **Severity Mapping:** Maps standard Python log levels (INFO, ERROR, etc.) to the `severity` field required by Cloud Logging.
- **Trace Context:** Injects `logging.googleapis.com/trace` using the `GCP_PROJECT_ID` and the request's `trace_id`, enabling "Trace-to-Logs" correlation in the GCP Console.
- **Request Metadata:** Includes `request_id` and `user_id` as top-level searchable fields.

### 2. Cloud Error Reporting
To support automated grouping and alerting in **Google Cloud Error Reporting**, all logs with level `ERROR` or higher now include:
- **`serviceContext`:** Identifies the service as `rateengine-backend` and includes the `APP_VERSION`.
- **`stack_trace`:** Emits a formatted string of the exception stack trace. GCP uses this field to trigger the Error Reporting dashboard.

### 3. Secret Masking
The logging formatter includes a recursive masking filter. Any key containing `password`, `token`, `secret`, or `key` is masked with `********`. Additionally, any value starting with `sm://` (Secret Manager references) is automatically masked to prevent accidental credential leakage in logs.

## SIGNAL Logging Standard
We have established a `SIGNAL:` logging pattern for high-value business events. These logs are intended to drive **Log-based Metrics** in GCP for dashboards and alerting.

### Supported Signals
| Prefix | Description | Key Fields |
| :--- | :--- | :--- |
| `SIGNAL:QUOTE_CREATED` | A new quote was successfully saved. | `quote_id`, `customer_id`, `total_amount` |
| `SIGNAL:SPOT_TRIGGERED` | A shipment requires manual SPOT intervention. | `reason_code`, `origin`, `destination` |
| `SIGNAL:AI_EXTRACTION_FAILED` | AI intake failed to parse a document. | `source_type`, `error_type` |
| `SIGNAL:MISSING_RATE` | Pricing failed due to a missing rate card. | `route_code`, `bucket` |
| `SIGNAL:LOGIN_SUCCESS` | Successful user authentication. | `user_id`, `username` |
| `SIGNAL:LOGIN_FAILED` | Failed authentication attempt. | `username`, `reason` |

### Usage
Use the `log_signal` helper from `core.logging_utils`:
```python
from core.logging_utils import log_signal, SIGNAL_QUOTE_CREATED

log_signal(SIGNAL_QUOTE_CREATED, "Quote QT-123 created", quote_id="QT-123", customer_id=45)
```

## Recommended Alerts (GCP)
Based on these signals, we recommend configuring the following alerts in the Google Cloud Console:
1. **High Error Rate:** `severity >= ERROR` count > X over 5 minutes.
2. **AI Extraction Failure Spike:** `jsonPayload.signal_type = "SIGNAL:AI_EXTRACTION_FAILED"` count > Y.
3. **Missing Rate Alert:** `jsonPayload.signal_type = "SIGNAL:MISSING_RATE"` for identifying pricing coverage gaps.
4. **Brute Force Detection:** `jsonPayload.signal_type = "SIGNAL:LOGIN_FAILED"` count from a single IP/User.

## Security Rules
- **No Payloads:** Never log raw request bodies or large document payloads.
- **No Secrets:** The `GCPJSONFormatter` provides a safety net, but developers must still avoid explicitly logging sensitive variables.
- **User IDs:** Log database `user_id` only; avoid logging PII like full names or email addresses where possible.
