# RBAC and Location Access Control Audit

This document presents a comprehensive security and functional audit of the Role-Based Access Control (RBAC), departmental visibility, and location/branch access controls in the RateEngine application.

---

## Executive Summary

The current authorization model in RateEngine is structured around a four-tier role system (**Admin, Manager, Finance, Sales**) and three departments (**Air, Sea, Land**). However, the implementation is incomplete:
* **No Branch/Location Concept**: The system has no database representation or mapping of users to specific branches or locations (e.g., Port Moresby (POM) vs. Lae (LAE)). 
* **Data Exposure Risks**: Because departmental access is evaluated globally, managers can see data from other locations within their department (e.g., an Air POM manager can view and edit Air LAE quotes).
* **IDOR in Customer Directory**: Any authenticated user can retrieve or modify details for any customer in the database.
* **Incomplete Department Definitions**: Critical operational units like "Customs" are completely missing from the schema.

---

## 1. Current Implementation Overview

### 1.1 User Roles & Fields
Defined in [CustomUser](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/accounts/models.py):
* **Roles**: `sales`, `manager`, `finance`, `admin`.
* **Departments**: `AIR` (Air Freight), `SEA` (Sea Freight), `LAND` (Land Freight). *Note: Missing Customs.*
* **Organization**: ForeignKey to `parties.Organization` (tenant workspace context).

### 1.2 Permission Classes
Defined in [permissions.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/accounts/permissions.py):
* `IsAdmin`: Exclusively admin access.
* `IsManagerOrAdmin`: Restricts rate cards and user management to managers/admins.
* `IsFinanceOrAdmin`: Restricts FX rate management.
* `CanViewCOGS` / `CanViewMargins`: Excludes sales users; allows managers, finance, and admins.
* `CanEditQuotes` / `CanFinalizeQuotes`: Allows sales, managers, and admins; excludes finance.
* `QuoteAccessPermission`: Smart permission allowing read-only access to all authenticated users, but write access only to users who can edit quotes.

### 1.3 Object-Level Visibility (Selectors)
Defined in [selectors.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/selectors.py):
* `get_quotes_for_user` & `get_spes_for_user`:
  * **Admin/Finance**: Global access to all records.
  * **Managers**: restricted to quotes/envelopes where the creator is in the same department (`created_by__department=user.department`) OR created by themselves.
  * **Sales**: Restricted strictly to quotes/envelopes created by themselves (`created_by=user`).

---

## 2. Audit Results by Area

| Audit Area | Backend Enforcement | Frontend UX Hiding | Key Gaps & Vulnerabilities |
| :--- | :--- | :--- | :--- |
| **Quote list/retrieve/update/delete** | Partial (via selectors/views) | Yes (via permissions utils) | Departmental filtering lacks branch segregation. No location checks. |
| **Quote compute/finalize** | Partial (via state machine / selectors) | Yes (conditional buttons) | Validation allows quoting any origin/destination, bypassing branch constraints. |
| **Customer/company access** | None (global list/retrieve) | None | **Critical IDOR Risk**: No tenant or owner validation in customer detail views. |
| **Rate cards** | Complete (Manager/Admin roles) | Yes (UI navigation hiding) | Finance is blocked from read-only rate card list views. No location/branch filtering. |
| **SPOT quotes (SPE)** | Complete (via `get_spes_for_user`) | Yes | Sharing logic is same as quotes; lacks location constraints. |
| **Dashboard/API summaries** | Partial (annotated via selectors) | Yes | Dashboard aggregates data globally by department without location filters. |

---

## 3. Detailed Gaps & Risks

### 3.1 Cross-Location Data Exposure (No Location/Branch Restraints)
Currently, `CustomUser` does not have a location/branch assignment (e.g., Port Moresby vs. Lae). 
* **The Risk**: A manager in the `AIR` department sees all `AIR` quotes globally. There is no filter checking if the quote's `origin_location` or `destination_location` matches the user's branch.
* **Impact**: An Air POM manager has full visibility into Air LAE quote data, volumes, and margins.

### 3.2 Missing Customs Department
Operational departments are hardcoded to `AIR`, `SEA`, and `LAND`.
* **The Risk**: There is no way to restrict a user to "Customs POM".
* **Impact**: Customs agents must be placed in one of the existing departments, resulting in over-privileged access to unrelated freight quotes, or they are restricted to Sales (cannot collaborate/review colleague quotes).

### 3.3 Customer Directory IDOR (Insecure Direct Object Reference)
The [CustomerDetailAPIView](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/views/services.py#L55-L189) fetches company profiles by querying the global table:
```python
queryset = Company.objects.filter(Q(is_customer=True) | Q(company_type='CUSTOMER'))
return get_object_or_404(queryset, pk=customer_id)
```
* **The Risk**: An authenticated user from one tenant/organization can view or update customer profiles (including margins and default currencies) of another tenant simply by guessing or brute-forcing the UUID.
* **Impact**: Exposure of commercial pricing agreements and customer databases.

---

## 4. Recommended Phased Implementation

### Phase 1: Database Schema Enhancements
1. **Extend `CustomUser`**:
   * Add a `branch` or `home_location` ForeignKey linking to `core.Location`.
   * Add `CUSTOMS` to `DEPARTMENT_CHOICES` in `accounts/models.py`.
2. **Add Ownership fields**:
   * Add `branch` or `location` field directly to `Quote` and `SpotPricingEnvelopeDB` to explicitly track which branch owns the transaction (rather than inferring from creator).

### Phase 2: Selector and QuerySet Hardening
1. Update `get_quotes_for_user` and `get_spes_for_user` in [selectors.py](file:///c:/Users/commercial.manager/dev/Project-RateEngine/backend/quotes/selectors.py):
   * Refine manager filters: Limit managers to quotes where the quote's branch matches the manager's assigned branch.
   * Restrict access for global roles (Finance) if location-based segregation applies to them.
2. Harden `CustomerDetailAPIView`:
   * Scope queries by tenant (`organization`) or only show customers associated with quotes they have access to.

### Phase 3: Frontend Validation & Dashboard Scoping
1. Update user context in the React frontend to capture `branch` and `department`.
2. Modify dashboard summary endpoints to pass branch parameters, ensuring summaries are filtered down by location.

---

## 5. Recommended Test Scenarios

To verify the enforcement of role, department, and location constraints, the following automated integration tests are required:

1. **Cross-Location Exposure (Manager)**:
   * **Setup**: Create Air Manager A assigned to POM and Air Manager B assigned to LAE.
   * **Action**: Manager A requests the Quote List endpoint.
   * **Verification**: Verify LAE quotes are excluded from Manager A's results.

2. **Cross-Location Exposure (Sales)**:
   * **Setup**: Create Sales user A assigned to POM.
   * **Action**: Sales A attempts to retrieve a quote created by Sales B (also in POM) via `/api/v3/quotes/<id>/`.
   * **Verification**: Endpoint must return `404 Not Found` to prevent IDOR disclosure.

3. **Customs Department Restrictions**:
   * **Setup**: Create Customs Manager A assigned to POM.
   * **Action**: Manager A queries the quote list.
   * **Verification**: Result contains only Customs quotes; Air/Sea freight quotes are excluded.

4. **Customer Profile Protection**:
   * **Setup**: Create two Users in different Organizations/Tenants.
   * **Action**: User from Org A queries `/api/v3/customers/<org_b_customer_id>/`.
   * **Verification**: Endpoint returns `404 Not Found` or `403 Forbidden`.
