# Phase UX-C: CRM Workflow Modernization Audit

## 1. CRM Workflow Map

- **Discovery & Lead Generation**: Accounts list (`/customers`) and Interaction logging (`Shift+L` or Dashboard).
- **Opportunity Creation**: Genesis from CRM Dashboard or Account detail. Captures basic lane, service, and estimated revenue.
- **Quoting Genesis**: Direct deep-linking from Opportunity to `quotes/new`, pre-filling company and route.
- **Engagement Loop**: Activity logging updates "Last Interaction" on Company and "Last Activity" on Opportunity. Dashboard flags "Dormant" accounts (90+ days).
- **Outcome Tracking**: Opportunities marked as WON/LOST. Won opportunities ideally correlate with finalized/sent quotes.

## 2. Top 10 CRM UX Friction Points Ranked by Severity

1. **Information Density (Cognitive Overload)**: The CRM Overview (`/crm`) tries to do too much at once, showing massive 10-column tables for Opportunities and Accounts simultaneously.
2. **Disconnected Location Data**: Opportunity forms use free-text `Origin` and `Destination` fields, while Quoting uses structured `Location` objects. This prevents accurate route-based opportunity reporting.
3. **Rigid Follow-Up Logic**: The 90-day "Dormant" threshold is hardcoded and doesn't account for different customer tiers or business types.
4. **Discoverability of Quick Actions**: Global hotkeys (like `Shift+L` for interaction logging) are not mentioned in the UI, forcing users to hunt for "Log Activity" buttons.
5. **Lack of CRM/Quote Outcome Correlation**: While linked technically, there's no visual dashboard indicating *which* quotes actually resolved a specific opportunity.
6. **Task/Activity Fragmentation**: Tasks and Interactions are distinct concepts but are displayed as simple lists, making it hard to see the "Story" of an account.
7. **Mobile Impracticality**: High-density tables make the current CRM nearly unusable on tablets or mobile phones during client visits.
8. **Fragmented Account Management**: "Accounts" links to `/customers` which feels like a separate module rather than a core part of the CRM sub-navigation.
9. **Dead-End Reporting**: The reports page is a collection of list views rather than actionable insights or trend visualizations for managers.
10. **Empty State Passive-Aggressiveness**: "No open opportunities" or "No accounts need follow-up" are simple text strings that don't encourage the next sales action.

## 3. Quick Wins

- **Structured Locations**: Convert Opportunity Origin/Destination to use the `LocationSearchCombobox`.
- **Primary Action Focus**: Reduce table columns on the Overview page to only the "Big 5" (Company, Title, Status, Value, Last Activity).
- **Deep Link Navigation**: Ensure every interaction log entry has a "Next Task" checkbox that opens the Task Dialog automatically.
- **Visual Hotkey Hint**: Add a small keyboard hint (e.g., `[L]`) next to Log Activity buttons.

## 4. Larger Redesign Candidates

- **Kanban Opportunity Board**: Replace the Opportunity table with a drag-and-drop board for visual pipeline management.
- **Account Health Dashboard**: A dedicated view for "Account Management" that prioritizes "At-Risk" or "Growth" accounts based on interaction frequency and quote volume.
- **Sales Rep "Daily Briefing"**: A simplified mobile-friendly view that just shows "Today's Tasks" and "3 Accounts to Call Today."

## 5. Recommended CRM UX Roadmap

- **UX-C1: Quick Wins & Data Integrity** (Structured locations, hotkey hints, column reduction).
- **UX-C2: CRM Overview Simplification** (Tabbed dashboard layout, mobile-responsive tables).
- **UX-C3: Opportunity Management** (Kanban view, Quote-linkage visualization).
- **UX-C4: Follow-Up & Task Discipline** (Smart follow-up alerts, automated task generation).
- **UX-C5: Manager Reporting** (Visual pipeline charts, department-specific activity summaries).

## 6. First Implementation Prompt for UX-C1

> **Execute Phase UX-C1:** Modernize CRM data entry and layout. 1) Replace free-text origin/destination inputs in the Opportunity Form with the `LocationSearchCombobox` component to ensure data alignment with quotes. 2) Streamline the CRM Overview tables by removing low-value columns (Industry, Tags, Service for Accounts list; Route, Priority for Opps list) to improve readability. 3) Add visual keyboard shortcuts hints (e.g., `Shift+L` for logging) to the UI.
