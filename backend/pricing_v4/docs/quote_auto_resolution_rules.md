# Quote Auto-Resolution Rules

## Purpose

Standard quote creation no longer asks the user to choose `agent_id`,
`carrier_id`, or `buy_currency`.
The backend must derive a deterministic buy-side path before pricing runs.

## Current precedence

1. Internal override inputs
   These remain available at the API layer for internal/admin use only.
   An override is accepted only if it narrows the active V4 buy-side data to one
   valid path. Overrides never permit guessing.

2. Safe shared-dimension resolution
   The resolver inspects the required buy-side components for the quote scope
   and shipment type, gathers the active V4 COGS rows for those components, and
   derives only dimensions that are safely shared across every buy-side
   component.

   Examples:
   - if every buy-side component can only use the same agent, `agent_id` is resolved
   - if every buy-side component can only use the same buy currency, `buy_currency` is resolved
   - if freight is in `AUD` but destination local is in `PGK`, no global
     `buy_currency` is resolved and component-level selection remains in control

3. Explicit failure
   If a component still cannot be selected deterministically after shared
   dimensions and any internal overrides are applied, the selector fails
   explicitly.

   The request fails only when runtime component selection is ambiguous or
   missing, not merely because different components use different currencies or
   counterparties.

## Non-negotiable runtime rule

After auto-resolution, the shared V4 selector still runs with the resolved
dimensions.
The selector is not weakened.

- If one exact row matches, pricing continues.
- If multiple rows still match, the API returns a selector ambiguity error.
- If no row matches, the API returns missing coverage.

The runtime must never guess, but it is allowed to resolve different components
independently when each component has exactly one valid row.

## Current data-model limitation

The current schema does not yet include durable buy-side default models for:

- customer default agent/carrier
- lane default agent/carrier
- product or service default agent/carrier
- buy-side currency defaults

Because those defaults are not modeled explicitly, the resolver does not invent
them in code.
Until such tables/config exist, any shared dimensions must come directly from
the active V4 rate data. Mixed per-component paths are valid as long as each
component still resolves to one deterministic row.

## Operational guidance

- Retire or revise overlapping active rows so one deterministic buy-side path
  remains for each quoteable context.
- Use internal overrides only for controlled admin workflows, not the standard
  quote UI.
- Treat ambiguity responses as data governance issues, not user-input issues.
