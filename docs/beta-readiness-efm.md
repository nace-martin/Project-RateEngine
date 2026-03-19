# EFM Beta Readiness Checklist

Last updated: 2026-03-20

This is the practical checklist for starting the first EFM beta with:

- `Nace Martin`
- `Evgenii Tsoi`
- `Julie-Anne Hasing`

Use this with:

- [tenant-model-beta.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/tenant-model-beta.md)
- [go-live-status-tracker.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/go-live-status-tracker.md)
- [production-cutover-checklist.md](/C:/Users/commercial.manager/dev/Project-RateEngine/docs/production-cutover-checklist.md)

## Beta Goal

The goal of this beta is not full multi-tenant rollout.

The goal is:

- one active organization
- one branded EFM workspace
- 1 to 2 real users
- stable quoting for real lanes
- branded PDFs and public quote outputs

## Beta Workspace

Active organization for beta:

- `EFM Express Air Cargo`

Expected tenant behavior:

- all launch users belong to this organization
- new quotes inherit this organization automatically
- PDFs, public quote pages, and quote previews use EFM branding
- internal header/sidebar reflect the signed-in organization branding

## Required Beta Users

### System Admin

- `Nace Martin`
- `nason.s.martin@gmail.com`

### Manager

- `Evgenii Tsoi`
- `evgenii.tsoi@efmpng.com`

### Sales

- `Julie-Anne Hasing`
- `julie-anne.hasing@efmpng.com`

### Finance

- not required for this beta phase

## Admin Setup Steps

### 1. Verify the organization exists

Check:

- name = `EFM Express Air Cargo`
- slug = `efm-express-air-cargo`
- active = true

Pass:

- the EFM organization exists and is active

### 2. Upload EFM branding

Use:

- `Settings -> Branding`

Upload and set:

- primary logo
- small logo
- display name
- legal name if needed
- support email
- support phone
- website
- address lines
- quote footer text
- public quote tagline
- email signature text
- primary color
- accent color

Pass:

- logo previews appear in settings
- saved branding reloads correctly

### 3. Create and assign users

Use:

- `Settings -> Users`

For each launch user, verify:

- role
- department
- organization = `EFM Express Air Cargo`
- active = true

Recommended setup:

- `Nace Martin`
  - role: `admin`
  - department: `AIR`
  - organization: `EFM Express Air Cargo`
- `Evgenii Tsoi`
  - role: `manager`
  - department: `AIR`
  - organization: `EFM Express Air Cargo`
- `Julie-Anne Hasing`
  - role: `sales`
  - department: `AIR`
  - organization: `EFM Express Air Cargo`

Pass:

- all three users exist
- all three are assigned to EFM

### 4. Verify internal branding

Log in as at least one beta user and confirm:

- app header shows EFM branding
- app sidebar shows EFM branding
- quote creation page shows the workspace context card
- customer create/edit pages show the workspace context card

Pass:

- signed-in workspace clearly shows `EFM Express Air Cargo`

## Quote Output Checks

### 5. Standard quote branding check

Create one standard quote and verify:

- quote saves successfully
- quote belongs to EFM organization
- quote preview uses EFM branding

Pass:

- quote output is branded for EFM, not generic hardcoded product branding

### 6. PDF quote branding check

Generate one PDF and verify:

- EFM logo appears if uploaded
- EFM contact details appear
- EFM footer appears
- document still shows RateEngine only as product attribution where intended

Pass:

- customer-facing PDF looks like an EFM document

### 7. Public quote branding check

Open one public quote link and verify:

- EFM logo appears if uploaded
- EFM colors are applied
- EFM contact details are correct
- `Powered by RateEngine` remains acceptable and low-key

Pass:

- public quote page is clearly branded for EFM

### 8. SPOT branding check

Create one SPOT case and verify:

- SPOT quote inherits EFM organization
- branded email draft content uses EFM signature/contact data

Pass:

- SPOT output is consistent with standard quote branding

## Beta Operational Checks

### 9. User login check

Verify:

- admin login works
- manager login works
- sales login works

Pass:

- each user can log in successfully

### 10. Launch-lane smoke checks

Run at least:

- one export standard quote
- one import standard quote
- one domestic quote if domestic is in beta scope
- one SPOT-required case

Pass:

- expected path is followed
- no unwanted SPOT trigger
- PDFs still generate

## Stop-Ship For Beta

Do not invite beta users if any of these are still open:

- EFM organization missing
- launch users not assigned to EFM
- branding not uploaded or not saving correctly
- header/sidebar still showing wrong workspace branding
- standard quote PDF not branded correctly
- public quote page not branded correctly
- login not verified for the three launch users

## Beta Exit Criteria

The EFM beta is ready to begin when:

- all launch users exist and are assigned to EFM
- EFM logo and branding are configured
- one real standard quote is branded correctly
- one SPOT case is branded correctly
- one public quote link is branded correctly
- one PDF is branded correctly
- first-user login verification is complete

## Quick Admin Summary

Before inviting users:

1. set EFM branding in `Settings -> Branding`
2. assign all beta users to `EFM Express Air Cargo` in `Settings -> Users`
3. verify header/sidebar branding
4. verify one standard quote, one PDF, one public quote, one SPOT case
5. only then invite the first users
