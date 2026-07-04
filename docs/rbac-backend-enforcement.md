# RBAC Backend Enforcement

## Overview
This document outlines the backend API scope enforcement implementation for RateEngine, focusing on preventing Insecure Direct Object Reference (IDOR) vulnerabilities and ensuring users can only access records within their authorized scope.

## Enforced Endpoint Categories

### CRM Endpoints
- Companies (Customers/Agents/Carriers)
- Contacts
- Opportunities  
- Interactions
- Tasks

### Quote Endpoints
- Quote creation, retrieval, update, and deletion
- Quote versions and calculations
- Quote transitions (finalize, send, accept, etc.)

### SPOT Envelopes
- SPOT pricing envelope creation and management
- Charge line management within envelopes
- Acknowledgment and resolution flows

### ProductCode Endpoints
- Product code request and review workflows
- Product code management with role-based access

## Access Policy

### Hierarchical Structure
```
Organization
→ OperatingEntity
→ Branch  
→ Department
→ UserMembership
```

### Scope Resolution
The system resolves user scope in the following order:
1. Active UserMembership records
2. Legacy user organization field (fallback)
3. Explicit role-based overrides for admins/managers

### Permission Checks
- **Admin**: Full system access across all scopes
- **Manager**: Access limited to assigned organization/operating_entity/branch/department
- **Finance**: Access limited to assigned scope, with specific financial data permissions
- **Sales**: Access limited to assigned scope, with quote-specific permissions

## Role/Override Rules

### Standard User Access
- Users can only access records within their assigned scope
- Cross-scope access attempts return 404 (not 403) to prevent object existence disclosure
- Direct ID guessing fails with appropriate HTTP status codes

### Manager/Admin Overrides
- Managers can access broader scopes based on their membership assignments
- Admins have global access across all organizations and scopes
- Override permissions are explicitly checked and logged

## IDOR Test Coverage

### Test Scenarios Implemented
- POM Air Freight user cannot list/read/update Lae record
- POM user cannot access AU/Fiji/SI record  
- Air Freight user cannot access/modify Sea Freight or Customs record unless role allows
- Branch manager can access only intended branch scope
- Admin can access cross-scope where intended
- Direct ID guessing for quote/SPOT envelope returns 404
- Draft Quote read API blocks inaccessible envelope
- Draft Quote resolve API blocks inaccessible envelope
- ProductCode request/review APIs respect role/scope
- Existing valid user workflows still pass

## Known Limitations

### Historical Data
- Legacy Quote/SPOT records may not have complete scope information
- Historical data is protected but not backfilled to new scope model
- Test data remains isolated and will be cleaned separately

### Performance Considerations
- Scoped queries may have slight performance impact compared to unscoped queries
- Proper indexing implemented to minimize performance degradation

## Manual Test Checklist

### Pre-Production Verification
- [ ] Verify normal users can access their own scoped data
- [ ] Verify normal users cannot access cross-scope data
- [ ] Verify manager/admin override functionality works as expected
- [ ] Verify all sensitive endpoints enforce proper scope validation
- [ ] Verify error responses don't leak object existence
- [ ] Verify existing workflows continue to function normally

## Remaining Risks

### Potential Gaps
- Third-party integrations may bypass scope checks if not properly configured
- Future endpoints may be added without proper scope enforcement
- Complex multi-scope queries may have edge cases not covered by current implementation

### Mitigation Strategies
- Regular RBAC audits scheduled post-deployment
- Automated testing for new endpoints requiring scope validation
- Comprehensive logging for access attempts to sensitive data