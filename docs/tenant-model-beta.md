# Tenant Model And Beta Admin Guide

## Purpose

This document explains how tenant/company branding works in the current beta and how admins should operate it safely.

## Core Model

RateEngine now separates:

- `RateEngine`
  - the product identity
- `Organization`
  - the tenant/workspace using the app
- `OrganizationBranding`
  - the customer-facing logo, colors, contact details, and footer content for that workspace

Important distinction:

- `Company`
  - customer / agent / carrier master data
- `Organization`
  - the account/workspace that owns the quote output branding

These are not the same thing.

## What Is Tenant-Aware Now

The following now resolve from the quote or signed-in user organization:

- PDF quotes
- public quote pages
- quote document preview
- SPOT email draft branding
- internal header/sidebar branding
- branding settings page
- quote creation
- SPOT quote creation
- cloned quotes
- user management

## What Still Is Not Tenant-Isolated

For this beta, these areas are still effectively shared operational data:

- customer master records
- contacts
- general reference data
- pricing master tables

That means:

- the app is organization-aware for branding and ownership context
- it is not yet a fully isolated multi-tenant data model

## Current Beta Rule

Use one primary organization for the beta unless you are intentionally testing multi-company behavior.

Recommended initial setup:

- `EFM Express Air Cargo`

If you add another organization later, be explicit about which users belong to it.

## How User Scoping Works

Each `CustomUser` now belongs to an `Organization`.

Effects:

- internal UI branding follows the signed-in user organization
- branding settings resolve from the signed-in user organization
- new quotes inherit the signed-in user organization
- cloned quotes inherit the signed-in user organization, falling back to the source quote organization if needed
- SPOT-created quotes inherit the signed-in user organization

## Admin Operating Steps For Beta

### 1. Create or verify the organization

In admin or the existing backfill migration, confirm:

- organization name
- slug
- active status
- default currency

For the beta, this should be:

- `EFM Express Air Cargo`

### 2. Configure branding

Use the in-app settings page:

- `Settings -> Branding`

Set:

- display name
- legal name
- support email
- support phone
- website
- address lines
- quote footer text
- public quote tagline
- email signature text
- primary color
- accent color
- primary logo
- small logo

These values drive customer-facing outputs.

### 3. Assign every launch user to the correct organization

Use:

- `Settings -> Users`

For each user, confirm:

- role
- department
- organization

For the current beta, all initial EFM users should belong to:

- `EFM Express Air Cargo`

### 4. Verify quote ownership

Create a new quote and confirm:

- the internal header shows the correct organization branding
- the generated PDF uses the correct organization branding
- the public quote page uses the correct organization branding

### 5. Verify SPOT ownership

Create a SPOT quote and confirm:

- the SPOT-created quote inherits the same organization
- branded email draft content matches the same organization

## Recommended Beta Admin Checklist

- one active organization configured
- branding fields completed
- launch users assigned to that organization
- one standard quote verified
- one SPOT quote verified
- one public quote link verified
- one PDF verified

## Safe Beta Operating Assumptions

For this beta, assume:

- one company workspace is the default operating model
- branding is organization-specific
- customers are shared master data
- pricing is shared master data

That is acceptable for the EFM beta.

## Future Multi-Company Expansion

To support more companies later, the next likely steps are:

1. tenant-scope customer data
2. tenant-scope pricing/rate-card ownership where needed
3. tenant-aware filters in operational lists
4. stronger admin controls around cross-organization access

Those are future expansion steps, not beta blockers.

## Practical Summary

For beta:

- use `Organization` for workspace identity
- use `OrganizationBranding` for logos and customer-facing appearance
- assign each user to the right organization
- let quotes inherit organization automatically

This gives EFM the right branding now without hardcoding EFM into the product, while still leaving a clean path for future multi-company rollout.
