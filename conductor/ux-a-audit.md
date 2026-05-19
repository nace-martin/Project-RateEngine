# Phase UX-A: Product Workflow Audit

## 1. Current Workflow Map

- **Quote Creation (`quotes/new`)**: Operates on a rigid 5-step progressive flow (Customer -> Route -> Terms -> Shipment -> Review). It is deeply coupled with the SPOT workflow; if rates are missing, the system intercepts the process and redirects to the SPOT intake.
- **SPOT Workflow (`quotes/spot/[speId]`)**: A specialized, complex 3-step intake, review, and confirm flow primarily used for resolving external agent rates and missing standard rates.
- **CRM Workflow (`crm/page.tsx`)**: A dense, dashboard-centric view containing multiple tables for opportunities, tasks, and recent interactions. Opportunities serve as the genesis point for new quotes.
- **Rate Admin Workflow (`pricing/manage/*`)**: Highly fragmented. Managers must navigate across 8 separate pages to manage Export/Import/Domestic/Local and Sell/COGS rates independently.

## 2. Top 10 UX Friction Points Ranked by Severity

1. **Sequential Rigidity in Quoting**: Users are forced to enter customer and route details before they can input shipment dimensions to check pricing, preventing a "quick quote" check.
2. **Abrupt SPOT Transitions**: The hard redirect to the SPOT workflow when a standard rate is missing breaks the user's context and momentum.
3. **Fragmented Rate Management**: With 8 separate management routes, admins cannot easily view Sell and COGS rates side-by-side or perform cross-lane validation.
4. **Unstructured Branch Context**: In operational flows like Shipments, "Branch" is a manual text entry field rather than a persistent user context or structured dropdown, risking data integrity for non-POM locations.
5. **Overloaded CRM Dashboard**: The `crm/page.tsx` dashboard is visually dense with competing calls-to-action, making it hard to prioritize daily follow-ups.
6. **Buy-side Noise in SPOT**: The SPOT UI frequently flags buy-side data that might confuse users who only care about finalizing a sell quote.
7. **Missing Cross-Navigation**: Users cannot easily navigate back-and-forth between a CRM Opportunity and its generated Quotes without multiple clicks.
8. **Feature Teasing**: Placeholders for unused features (e.g., "Sea Freight", "Address Book") clutter the UI.
9. **Hidden Review Issues**: The SPOT "Issues" vs "All Charges" view toggles can cause users to miss reviewing valid charges.
10. **Lack of Persistent Location Context**: Users must manually specify locations instead of the system recognizing their active branch (POM, LAE, etc.) globally.

## 3. Quick Wins (Implementation-Safe)

- Convert the manual "Branch" text input in Shipment creation into a structured dropdown.
- Remove or visually hide non-functional placeholders ("Sea Freight", "Address Book").
- Add direct deep-links from CRM Opportunity Detail pages to their associated Quotes.
- Provide a warning/opt-in prompt for the SPOT workflow instead of auto-redirecting.

## 4. Larger Redesign Candidates

- **Unified Rate Grid**: Combine the fragmented 8 rate pages into a single, comprehensive data-grid component.
- **Decoupled Quoting Form**: Move away from the strict 5-step wizard to a flexible, single-page or tabbed layout that allows dimensional input first.
- **Task-Focused CRM**: Redesign the CRM dashboard to act as a Kanban board or prioritized task list for sales reps.

## 5. Screens / Routes / Components Involved

- `frontend/src/components/forms/QuoteForm.tsx`
- `frontend/src/app/quotes/spot/[speId]/page.tsx`
- `frontend/src/app/pricing/manage/page.tsx` (and sub-routes)
- `frontend/src/app/crm/page.tsx`
- `frontend/src/components/shipments/wizard/ShipmentTypeStep.tsx`

## 6. Recommended UX Implementation Roadmap

- **UX-B: Quick Wins & Navigation** (Fix branch input, remove placeholders, add cross-links).
- **UX-C: Quote Flow Flexibility** (Decouple the 5-step Quote process).
- **UX-D: Unified Rate Administration** (Consolidate the 8 rate management pages).
- **UX-E: CRM Dashboard Simplification** (Redesign the CRM dashboard for task focus).

## 7. First Implementation Prompt for UX-B

> **Execute Phase UX-B:** Implement the identified quick wins to improve basic navigation and data integrity without modifying underlying business logic. First, update the Shipment creation flow to use a structured select dropdown for the "Branch" field instead of manual text entry. Second, remove or disable UI placeholders for "Sea Freight" and "Address Book". Finally, add deep-linking from the CRM Opportunity detail view to its associated Quotes.