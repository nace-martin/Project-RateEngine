# Quote Selector Input Requirements

This document is retained for compatibility, but the standard quote contract has
changed.

## Standard quote flow

The standard quote UI does not send:

- `agent_id`
- `carrier_id`
- `buy_currency`

Those values are now resolved by the backend before pricing runs. See
[quote_auto_resolution_rules.md](./quote_auto_resolution_rules.md).

## Internal/admin override flow

The API still accepts optional override inputs for controlled internal use:

- `agent_id`
- `carrier_id`
- `buy_currency`

These are override filters, not free-form user inputs.
They are valid only if they narrow the active V4 buy-side data to one
deterministic path.

The runtime never guesses:

- If one valid path remains, pricing continues.
- If multiple valid paths remain, the API returns ambiguity.
- If no valid path remains, the API returns missing coverage.
