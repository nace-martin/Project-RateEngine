# Release Notes v0.4.0

**Date**: 2025-10-02

## Summary

This release introduces the new RateEngine V2, a completely redesigned quoting engine that is more deterministic, auditable, and resilient. The new engine is powered by a system of "BUY Source Adapters" that normalize pricing from various external sources into a standardized format. This allows the V2 engine to compare and select the best offer in a deterministic way.

## New Features

*   **RateEngine V2**: A new quoting engine that is more deterministic, auditable, and resilient. The V2 engine is powered by a system of "BUY Source Adapters" that normalize pricing from various external sources into a standardized format.
*   **BUY Source Adapters**: A new system for normalizing pricing from various external sources. The initial implementation includes two adapters:
    *   **`RateCardAdapter`**: This adapter is responsible for parsing HTML rate cards from partners.
    *   **`SpotAdapter`**: This adapter handles manually entered spot quotes from the UI.
*   **New API Endpoint**: A new API endpoint `/api/quote/compute2` has been added to expose the V2 rating engine.

## Improvements

*   **Improved Quoting Accuracy**: The new V2 engine provides more accurate and consistent quotes.
*   **Improved Resilience**: The new V2 engine is more resilient to failures in external systems.
*   **Improved Auditability**: The new V2 engine provides a detailed snapshot of the quoting process, making it easier to audit and debug quotes.

## Bug Fixes

*   This release does not include any bug fixes.

## Known Issues

*   This release has no known issues.
