# Phase 5G: Observability & Runtime Operations Audit

## Current State

### 1. Runtime Health
- **Endpoint:** `/api/health/` (implemented in `backend/core/views.py`).
- **Logic:** Performs a database connectivity check (`SELECT 1`). Returns 200 OK or 503 Service Unavailable.
- **GCP Usage:** Cloud Run currently uses this endpoint for both `liveness` and `startup` probes.
- **Risk:** Liveness probes that depend on the database can trigger unnecessary container restarts during transient database outages or network latency, potentially worsening a "thundering herd" problem.

### 2. Logging
- **Format:** Structured JSON logging is enabled in production (via `pythonjsonlogger.json.JsonFormatter`).
- **Storage:** Logs are emitted to `stdout` and collected by Google Cloud Logging.
- **Missing Data:** Current logs lack critical correlation and context fields:
    - `request_id`: No unique identifier for tracing a single request's execution path.
    - `user_id`: Not included in standard request logs.
    - `entity_ids`: `quote_id`, `spe_id`, and `customer_id` are not consistently logged in a structured format.
    - `severity`: Standard level names are mapped, but not always optimized for Cloud Logging dashboards.

### 3. Request Correlation
- **Status:** Not implemented.
- **Impact:** Difficult to cross-reference logs across different modules (e.g., matching a Quote calculation error to the original API request).

### 4. Error Reporting
- **Status:** Relies on standard `logger.exception` which Cloud Logging captures as text.
- **GCP Integration:** Not explicitly formatted for Google Cloud Error Reporting (requires specific JSON structure for stack traces).

---

## Gaps and Risks

| Area | Gap | Risk |
| :--- | :--- | :--- |
| **Health** | Liveness depends on Database. | Unnecessary container restarts during DB downtime. |
| **Tracing** | No `request_id` or `trace_id` correlation. | High "Time to Resolve" for production incidents. |
| **Context** | Missing user/tenant/quote context in logs. | Auditing and troubleshooting commercial issues is manual. |
| **Metrics** | No structured log-based metrics for commercial events. | Visibility into "Quote Success Rate" or "AI Extraction Failures" is low. |
| **Alerting** | No formal threshold-based alerts. | Incidents are discovered by users rather than operators. |

---

## Architecture Plan: "Observability Foundation"

### 5G-B: Request Correlation & Log Enrichment (Implemented)
- **Middleware:** Implement a `CorrelationMiddleware` that:
    - Generates a unique `request_id`.
    - Supports incoming `X-Request-ID` or `X-Cloud-Trace-Context`.
    - Injects the ID into a thread-local or context-variable for the logger.
- **Logger Context:** Add a filter to the Django logging configuration that automatically injects `request_id`, `user_id`, and `trace_id` into all log records.
- **API Response:** Include `X-Request-ID` in headers to allow frontend/support to report specific IDs.

### 5G-C: Health & Readiness Optimization (Implemented)
- **New Pattern:** Split health checks into two endpoints:
    - `/api/health/liveness/`: Returns 200 OK immediately if the process is running (no DB check).
    - `/api/health/readiness/`: Performs the DB check (current logic).
- **GCP Config:** Update Cloud Run probes to use the appropriate paths.

### 5G-D: Error Reporting & Structured Context
- **Cloud Error Reporting:** Update the JSON formatter to include `serviceContext` and structured `exception` data compatible with GCP's Error Reporting service.
- **Sensitive Data Filter:** Ensure the `SecretResolver` and logger explicitly block any accidental logging of values containing `sm://` or resolved secrets.

### 5G-E: Log-Based Metrics & Operational Signals
- **Log Signatures:** Define a "Signal" logging pattern for key commercial events:
    - `SIGNAL:QUOTE_CREATED` {quote_id, user_id, value}
    - `SIGNAL:AI_EXTRACTION_FAILED` {reason, source_type}
    - `SIGNAL:PRICING_MISSING_RATE` {route, bucket}
- **Cloud Logging:** Use these structured patterns to create "Log-based Metrics" in GCP for alerting and dashboards.

---

## Implementation Roadmap

1. **Phase 5G-B (Request Tracing):** Implement correlation middleware and basic log enrichment.
2. **Phase 5G-C (Health Hardening):** Split liveness/readiness and update deployment workflows.
3. **Phase 5G-D (GCP Ops Integration):** Format logs for Cloud Error Reporting and define alert-ready log signatures.
4. **Phase 5G-E (Dashboards):** Document the strategy for building GCP Monitoring dashboards using the new signals.
