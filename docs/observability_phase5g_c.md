# Phase 5G-C: Health & Readiness Optimization

## Overview
This phase optimizes how RateEngine reports its health to Google Cloud Run. By splitting a single health check into distinct **Liveness** and **Readiness** probes, we improve system stability and prevent unnecessary container restarts during transient dependency failures.

## Health Endpoints

### 1. Liveness Check (`/api/health/liveness/`)
- **Purpose:** Confirms the Django process is running and responding to requests.
- **Dependency:** None (Process-only).
- **Cloud Run Probe:** `liveness`
- **Behavior:** Returns `200 OK` as long as the web server is alive.
- **Why no DB?** If the database is temporarily unreachable, the container should **not** be restarted. Restarting a container doesn't fix a database issue and can lead to a "thundering herd" effect where many containers restart and hammer the DB simultaneously once it recovers.

### 2. Readiness Check (`/api/health/readiness/`)
- **Purpose:** Confirms the application is ready to serve traffic, including dependencies.
- **Dependency:** Database (Cloud SQL).
- **Cloud Run Probe:** `startup`
- **Behavior:** Returns `200 OK` only if database connectivity is verified. Returns `503 Service Unavailable` otherwise.
- **Why DB?** Traffic should not be routed to a container that cannot fulfill requests requiring database access (which is almost all RateEngine requests).

### 3. Combined Check (`/api/health/`)
- **Purpose:** Backward compatibility for external monitoring or legacy probes.
- **Behavior:** Performs a full dependency check (same as readiness).

## Cloud Run Configuration
The deployment workflow (`.github/workflows/deploy-production.yml`) has been updated with the following flags:

```yaml
--liveness-probe-path=/api/health/liveness/
--startup-probe-path=/api/health/readiness/
```

## Response Schema
All health endpoints return a consistent structured JSON format:

```json
{
  "status": "ok",
  "service": "rateengine-backend",
  "check_type": "liveness|readiness|combined",
  "timestamp": "2026-05-19T12:00:00.000Z",
  "dependencies": {
    "database": "ok"
  }
}
```

## Security
- **No Connection Leaks:** The endpoints confirm connectivity but never return connection strings, IP addresses, or internal error messages.
- **Unauthenticated:** These endpoints do not require authentication to allow Cloud Run's infrastructure to probe them without managing application-level credentials.
