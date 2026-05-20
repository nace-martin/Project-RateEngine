# Quote-Led CRM Automation

## Overview
RateEngine CRM is designed to minimize manual administrative overhead by automatically capturing commercial opportunities and activities directly from the quoting lifecycle. The `OpportunityAutoBuilderService` is the central engine for this automation.

## Core Principles
- **Quotes Drive Opportunities**: Users should rarely need to create opportunities manually. A quote contains all the necessary signals (customer, route, service, value) to build a CRM entry.
- **Deduplication First**: Multiple quotes or revisions for the same lane/customer are automatically grouped under a single "active pursuit" (Opportunity).
- **Automated Discipline**: System-generated tasks ensure that every sent quote is followed up without manual tracking.

## Lifecycle Mapping

| Quote Status | Opportunity Status | Actions Triggered |
| :--- | :--- | :--- |
| **DRAFT** | **NEW** | Create/Resolve Opportunity, Log Interaction |
| **FINALIZED** | **QUALIFIED** | Progress Opportunity, Log Interaction |
| **SENT** | **QUOTED** | Create Follow-Up Task (+3 business days), Log Interaction |
| **ACCEPTED** | **WON** | Close Opportunity, Complete pending tasks, Log Interaction |
| **LOST / EXPIRED**| **LOST*** | Close Opportunity (if no other active quotes), Complete tasks |

*\* Opportunity only marks as LOST if no other active quotes (Draft, Finalized, Sent) are linked to it.*

## Opportunity Resolution (Deduplication)
The system prevents CRM clutter by searching for existing active opportunities before creating new ones.
- **Match Criteria**: Company, Service Type (Air/Sea/Transport), Origin, Destination, and Direction (Import/Export/Domestic).
- **Time Window**: 14 days.
- **Active Statuses**: NEW, QUALIFIED, QUOTED.

## Naming Convention
Opportunities are automatically named for maximum scannability:
`[Mode] [Direction] [Origin] \u2192 [Destination] - [CustomerName]`
*Example: Air Export POM \u2192 BNE - Daikin PNG*

## Automated Tasks
- **On Quote Sent**: A task is assigned to the quote owner: *"Follow up on Quote [Number]"*.
- **Due Date**: 3 business days from the sent date (skipping weekends).
- **Cleanup**: When an opportunity is marked WON or LOST, all related pending tasks are automatically marked as COMPLETED.

## Technical Details
The implementation resides in `backend/crm/opportunity_auto_builder.py`.

### Service Entry Point
`OpportunityAutoBuilderService.sync_from_quote(quote, event=None, actor=None)`

### Integration (Phase CRM-C)
- Currently, the service is a standalone foundation.
- Full integration into the `Quote` model signals and state machine will occur in Phase CRM-C.
- Bi-directional linking is maintained via `Quote.opportunity`.
