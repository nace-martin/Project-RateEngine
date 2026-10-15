# Audit Report — Quote and SPOT Object Access

This document details the security audit of object-level access controls for `Quote` and `SpotPricingEnvelopeDB` (SPOT) models to identify potential IDOR (Insecure Direct Object Reference) vulnerabilities.

---

## Files Reviewed

We audited all core view modules, reporting views, and helper utilities handling quote and SPOT persistence:
1. **[lifecycle.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/lifecycle.py)** — CRUD ViewSet and transition/cloning lifecycle views.
2. **[calculation.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/calculation.py)** — V3 compute and calculation endpoints.
3. **[services.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/services.py)** — Customer profile lookup, ratecard upload, and PDF download views.
4. **[public.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/public.py)** — Public quote sharing views.
5. **[spot_views.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/spot_views.py)** — Spot pricing envelope CRUD, resolution, and acknowledgment views.
6. **[reporting_views.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/reporting_views.py)** — Funnel, revenue, and performance analytics.
7. **[selectors.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/selectors.py)** — Central authorization selector logic.

---

## Findings

### Central Authorization Selectors (Reference)
The system leverages two robust selector functions in `selectors.py` to enforce visibility boundaries:
* `get_quotes_for_user(user, queryset)`: Restricts non-admin users to their own department (for Managers) or strictly their own created quotes (for Sales).
* `get_spes_for_user(user, queryset)`: Restricts non-admin users to departmental SPEs (for Managers) or strictly their own created SPEs (for Sales).

Both selectors correctly return an empty queryset `queryset.none()` for unauthenticated users, and return full global querysets only to admin/finance users.

---

### Safe Endpoints

Every audited endpoint was found to be **SAFE** from IDOR risks due to strict enforcement of central authorization selectors or token-based signatures:

| Endpoint / Action | View Class / Method | Authorization Enforcement Method | Status |
| :--- | :--- | :--- | :--- |
| **Quote List & Detail** | `QuoteV3ViewSet` | Overrides `get_queryset()` to filter through `get_quotes_for_user`. Detail actions like `retrieve` and `destroy` use `get_object()` and automatically inherit this restriction. | **SAFE** |
| **Quote Compute / Recalculate** | `QuoteComputeV3APIView` | If a `quote_id` is supplied, it is resolved via `get_quote_for_user(request.user, quote_id)`. | **SAFE** |
| **Quote Transition / Finalize** | `QuoteTransitionAPIView` | `get` and `post` both retrieve the quote using `get_quote_for_user(request.user, quote_id)`. | **SAFE** |
| **Quote Clone** | `QuoteCloneAPIView` | Resolves source quote via `get_quote_for_user(request.user, quote_id)`. | **SAFE** |
| **Quote Version Create** | `QuoteVersionCreateAPIView` | Resolves source quote via `get_quote_for_user(request.user, quote_id)`. | **SAFE** |
| **Quote PDF Download** | `QuotePDFAPIView` | Validates access by resolving quote via `get_quote_for_user(request.user, quote_id)` before calling PDF generation. | **SAFE** |
| **Public Quote Detail** | `QuotePublicDetailAPIView` | Uses `signing.TimestampSigner` (with salt and max age) to decrypt/validate the sharing token. Access is only allowed if token is valid and quote status is `FINALIZED` or `SENT`. | **SAFE** |
| **SPOT Listing** | `SpotEnvelopeListCreateAPIView` | Resolves listing query using `get_spes_for_user(user, base_qs)`. | **SAFE** |
| **SPOT Detail / Update** | `SpotEnvelopeDetailAPIView` | Queries the envelope using `_get_spe_or_404(request.user, envelope_id)`, which internally relies on `get_spes_for_user`. | **SAFE** |
| **SPOT Resolve Charge Line** | `SpotChargeLineManualResolutionAPIView`, `SpotChargeLineConditionalResolutionAPIView` | Resolves envelope via `_get_spe_or_404(request.user, envelope_id)`. | **SAFE** |
| **SPOT Acknowledge** | `SpotEnvelopeAcknowledgeAPIView` | Resolves envelope via `_get_spe_or_404(request.user, envelope_id)`. | **SAFE** |
| **SPOT Compute** | `SpotEnvelopeComputeAPIView` | Resolves envelope via `_get_spe_or_404(request.user, envelope_id)`. | **SAFE** |
| **SPOT Create Quote** | `SpotEnvelopeCreateQuoteAPIView` | Resolves envelope via `_get_spe_or_404(request.user, envelope_id)`. | **SAFE** |
| **SPOT Batch Review** | `SpotSourceBatchReviewAPIView` | Resolves envelope via `_get_spe_or_404(request.user, envelope_id)`. | **SAFE** |
| **SPOT Reply Analyze** | `SpotReplyAnalysisAPIView` | Resolves envelope via `_get_spe_or_404(request.user, spe_id)`. Failure to match bubbles up as a secure DRF 404 response. | **SAFE** |
| **Financial & Funnel Reports** | `ReportsViewSet` | All aggregation and listing methods filter the base `Quote` querysets through `get_quotes_for_user(request.user)`. | **SAFE** |

---

### Risky Endpoints

* **No risky endpoints identified.** Both the V3 Quote lifecycle and the V3 SPOT envelope API surfaces have successfully integrated robust object-level access boundaries.

---

## Root Cause Analysis & Security Posture

The codebase demonstrates strong adherence to the **Principle of Least Privilege** and secure API design patterns:
1. **Centralized Authority**: Selection and visibility criteria are managed in a single module (`selectors.py`). Rather than writing ad-hoc `.filter(created_by=request.user)` calls across various views, views invoke `get_quote_for_user` or `get_quotes_for_user`, preventing drift in authorization logic.
2. **Fail-Closed Queries**: Both `get_quote_for_user` and `_get_spe_or_404` raise `Http404` when access is unauthorized, preventing attackers from checking the existence of resource UUIDs (no resource enumeration leakage).
3. **Cryptographically Protected Sharing Links**: The public quote detail view uses timestamped signature tokens (`TimestampSigner`) instead of raw database UUIDs in the URL, preventing external unauthorized enumeration.

---

## Recommended Maintenance

To maintain this secure architecture as the codebase evolves:
1. **Lint Rules / Code Review Guidelines**: Ensure any new view or service added to the `quotes` application queries the database via the centralized selectors in `selectors.py` rather than directly using `Quote.objects` or `SpotPricingEnvelopeDB.objects`.
2. **Prevent Selector Bypass**: Avoid adding generic helper functions in views that query model IDs without verifying user credentials.

---

## Test Scenarios & Verification Matrix

The following verification matrix ensures that IDOR protections remain stable. The existing test suite in `backend/quotes/tests/test_departmental_access.py` and `backend/quotes/tests/test_api_v3.py` already implements many of these controls.

### 1. Quote Isolation Tests
* **Scenario 1**: Sales User A attempts to GET/PATCH/DELETE a quote created by Sales User B.
  * *Expected Outcome*: Returns `404 Not Found`.
* **Scenario 2**: Manager User A (Air Department) attempts to GET/PATCH/DELETE a quote created by Sales User B (Sea Department).
  * *Expected Outcome*: Returns `404 Not Found`.
* **Scenario 3**: Manager User A (Air Department) attempts to GET/PATCH/DELETE a quote created by Sales User C (Air Department).
  * *Expected Outcome*: Returns `200 OK` (read/update) or `204 No Content` (delete).
* **Scenario 4**: Admin User attempts to GET/PATCH/DELETE any quote.
  * *Expected Outcome*: Returns successful response.

### 2. SPOT Envelope Isolation Tests
* **Scenario 1**: Sales User A attempts to GET/POST/PATCH details or acknowledge a SPOT envelope created by Sales User B.
  * *Expected Outcome*: Returns `404 Not Found`.
* **Scenario 2**: Sales User A attempts to upload/analyze an agent reply against a SPOT envelope owned by Sales User B.
  * *Expected Outcome*: Returns `404 Not Found` (Bubbled up via `_get_spe_or_404`).

### 3. Public Share Link Security Tests
* **Scenario 1**: Unauthenticated request to public view with an expired token.
  * *Expected Outcome*: Returns `403 Forbidden`.
* **Scenario 2**: Unauthenticated request to public view with a valid token for a `DRAFT` quote.
  * *Expected Outcome*: Returns `403 Forbidden` (only finalized/sent quotes can be shared).
* **Scenario 3**: Unauthenticated request to public view with a valid token for a `FINALIZED` quote.
  * *Expected Outcome*: Returns `200 OK` with serialized public-safe details.
