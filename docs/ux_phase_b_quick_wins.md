# UX Phase B: Quick Wins & Navigation Cleanup

## Overview
Phase B focused on low-risk, high-impact UX improvements to address immediate friction points identified in Phase A audit. These changes enhance data integrity, navigation clarity, and cross-module continuity.

## Implemented Changes

### 1. Branch Field Standardization
- **Component**: Created `BranchSelect` component in `frontend/src/components/BranchSelect.tsx`.
- **Shipment Wizard**: Replaced free-text "Branch" input with `BranchSelect` in `ShipmentTypeStep.tsx`.
- **Shipment Templates**: Replaced free-text "Branch" input with `BranchSelect` in `shipments/templates/page.tsx`.
- **Branches Supported**: POM, LAE, BNE, FIJ, SOL.

### 2. Navigation & Sidebar Cleanup
- **Sidebar Badges**: Added `badge` support to `AppSidebar`.
- **Opportunities**: Added "CRM" badge to Opportunities in sidebar.
- **Role Visibility**: Updated "Settings" visibility to include `admin` role and restricted `finance` as appropriate.
- **Incomplete Features**: Labeled "Shipment Address Book" with a "COMING SOON" badge in the page header to manage user expectations.

### 3. CRM ↔ Quote Continuity
- **CRM Dashboard**: Added a "Create Quote" action button (PlusCircle) directly to the Opportunities table.
- **CRM Dashboard**: Added an "Actions" column for clearer navigation.
- **Opportunity Detail**: Added "Create Quote" and "Back to CRM" buttons in the header.
- **Quote Detail**: Added a link to the related CRM Opportunity in the "Internal Use Only" section.
- **Deep Linking**: Enhanced `quotes/new` to accept `opportunity`, `service_type`, `origin`, and `destination` parameters for smoother flow from CRM.

### 4. General UX Enhancements
- **Breadcrumbs**: Standardized breadcrumb usage in Quote Detail page.
- **Consistency**: Improved header actions across CRM and Quote views.

## UX Backlog (Remaining from Phase A)
- **Quote Flow Flexibility (UX-C)**: Decouple the rigid 5-step wizard.
- **Unified Rate Administration (UX-D)**: Consolidate the fragmented rate management pages.
- **CRM Dashboard Simplification (UX-E)**: Transition CRM to a task-focused layout.
- **Persistent Location Context**: Global branch selector in the sidebar/header.

## Validation Results
- **Lint**: Frontend lint passed.
- **Typecheck**: Frontend typecheck passed.
- **Manual Check**: Verified branch dropdowns, CRM links, and sidebar badges.
- **Logic Integrity**: No changes made to pricing or SPOT business logic.
