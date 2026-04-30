# CRM Module V1

## Purpose

Phase 1 adds the backend foundation for RateEngine CRM tracking. It records customer opportunities, interactions, and follow-up tasks while keeping deterministic freight pricing, quote calculation, and operational shipment creation in their existing modules.

## Lifecycle

Opportunities move through `NEW`, `QUALIFIED`, `QUOTED`, `WON`, and `LOST`.

The supported lifecycle helpers live in `crm/services.py`:

- `mark_opportunity_quoted(opportunity, quote=None, actor=None)` moves only `NEW` or `QUALIFIED` opportunities to `QUOTED` and leaves `WON` or `LOST` untouched.
- `mark_opportunity_won(opportunity, actor=None, reason="", source_type="", source_id="")` records `won_at`, `won_by`, and `won_reason`.
- `mark_opportunity_lost(opportunity, actor=None, reason="")` records `lost_reason` and clears won fields.

Each helper creates a system-generated interaction for auditability.

Allowed won source types are `QUOTE_ACCEPTED`, `SHIPMENT_CREATED`, `IMPORT_JOB_CREATED`, `CLEARANCE_FILE_CREATED`, `AGENT_PREALERT_RECEIVED`, and `MANUAL`.

## Conversion Rule

A won opportunity does not always create a shipment.

Export and Domestic opportunities may convert through RateEngine shipment creation when the operational file is owned locally. Import opportunities often become won through quote acceptance, import job/file opening, clearance file creation, agent pre-alert receipt, or manual sales action because overseas agents typically create the origin shipment, AWB, or booking in their own systems.

Phase 1 therefore does not wire a universal shipment-created equals won rule.

## Models

- `Opportunity`: customer opportunity with company, service type, import/export/domestic direction, scope, route text, estimates, status, priority, owner, next action, activity, won/lost fields, and active flag.
- `Interaction`: call, meeting, email, site visit, or system event linked to a company and optionally a contact and opportunity.
- `Task`: follow-up item linked to at least a company or an opportunity, with owner, due date, status, and completion fields.

Existing model extensions:

- `Company`: `account_owner`, `last_interaction_at`, `industry`, and JSON `tags`.
- `Quote`: nullable `opportunity` link to `crm.Opportunity`.

## Endpoints

All Phase 1 CRM endpoints use the existing authenticated DRF API conventions.

- `GET/POST /api/v3/crm/opportunities/`
- `GET/PATCH/PUT /api/v3/crm/opportunities/<id>/`
- `GET/POST /api/v3/crm/interactions/`
- `GET/PATCH/PUT /api/v3/crm/interactions/<id>/`
- `GET/POST /api/v3/crm/tasks/`
- `GET/PATCH/PUT /api/v3/crm/tasks/<id>/`

Filters:

- Opportunities: `company`, `status`, `owner`, `service_type`, `priority`
- Interactions: `company`, `opportunity`
- Tasks: `owner`, `status`, `due_date`, `company`, `opportunity`

## Phase 1 Non-Goals

Phase 1 does not include frontend UI, dashboard, Kanban boards, reporting, AI CRM features, sales automation, universal shipment conversion, or import shipment requirements.
