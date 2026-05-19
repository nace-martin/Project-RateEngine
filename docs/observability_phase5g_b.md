# Phase 5G-B: Request Correlation & Log Enrichment

## Overview
This phase establishes a foundation for tracing individual API requests across the entire application stack. By introducing a unique `request_id` for every transaction, we enable precise log aggregation and troubleshooting in Google Cloud Logging.

## Implementation Details

### 1. CorrelationIdMiddleware
Implemented in `backend/core/middleware.py`, this middleware ensures that every HTTP request has a unique identifier:
- **Incoming ID:** Accepts `X-Request-ID` from the client if it's a valid UUID.
- **Generation:** Automatically generates a new UUID if the header is missing or invalid.
- **GCP Tracing:** Captures `trace_id` from the `X-Cloud-Trace-Context` header (provided automatically by Google Cloud Load Balancers).
- **Persistence:** Stores identifiers in thread-local storage for the duration of the request.
- **Response:** Returns the `X-Request-ID` in the HTTP response headers.

### 2. Log Enrichment
The Django logging configuration (`backend/rate_engine/settings.py`) has been updated with a `RequestContextFilter`:
- **Structured Fields:** Every JSON log entry now includes `request_id`, `trace_id`, and `user_id` (if authenticated) at the top level.
- **Cloud Logging Compatibility:** The `trace_id` field enables seamless integration with GCP Cloud Trace.

### 3. Safe Context Management
- **Leak Prevention:** Thread-local context is explicitly cleared at the end of every request using a `finally` block in the middleware.
- **Security:** The middleware only captures identifiers. Sensitive data like bodies, tokens, or cookies are never stored in the correlation context.

## Log Field Summary (Production JSON)
| Field | Description |
| :--- | :--- |
| `request_id` | Unique UUID for the current request. |
| `trace_id` | GCP-provided trace identifier. |
| `user_id` | Database ID of the authenticated user (if applicable). |
| `module` | The Python module emitting the log. |
| `levelname` | Standard log level (INFO, WARNING, etc.). |

## Verification Results
- **Unit Tests:** `backend/core/tests/test_correlation.py` passed with 100% coverage of generation, capture, and cleanup logic.
- **System Check:** `python manage.py check` passed with no issues.
- **Manual Check:** Confirmed that `X-Request-ID` is returned in API responses.

## Operational Note
When troubleshooting an issue reported by a user or the frontend, search for the `request_id` in Google Cloud Logging to see the complete execution path across all backend modules.
