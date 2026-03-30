# Production Go-Live Checklist

Last updated: 2026-03-29

Use this checklist for the clean production launch.

## 1. Platform Checks

- Confirm the Render persistent disk is attached at `/opt/render/project/src/backend/media`.
- Confirm the backend is up and the frontend can log in.
- Run:

```bash
python manage.py check_media_storage --write-test
```

Pass condition:

- storage write/delete test succeeds

## 2. Access Setup

- Confirm these real users exist and can log in:
  - `julie-anne.hasing@efmpng.com`
  - `evgenii.tsoi@efmpng.com`
  - `joseph.kaima@efmpng.com`
  - `nason.martin@efmpng.com`
- Change all temporary passwords immediately after first login.
- Confirm the placeholder `admin@example.com` account is not usable in production.

Pass condition:

- each real user can access the correct role area
- only Nason has admin access

## 3. Organization Setup

- Open branding settings for `EFM Express Air Cargo`.
- Re-upload the primary logo.
- Confirm branding values are correct:
  - display name
  - legal name
  - support email
  - support phone
  - website
  - colors
  - quote footer text
  - public tagline
- Update the shipment disclaimer from the current placeholder text.

Pass condition:

- logo renders in app chrome and quote output
- no broken image links
- shipment disclaimer matches live operations wording

## 4. Master Data Import

Run in this order:

```bash
python manage.py import_customers --file /path/to/customers.csv --dry-run
python manage.py import_customers --file /path/to/customers.csv
```

```bash
python manage.py import_contacts --file /path/to/contacts.csv --dry-run --strict-sync
python manage.py import_contacts --file /path/to/contacts.csv --strict-sync
```

```bash
python manage.py import_customer_discounts --file /path/to/discounts.csv --dry-run
python manage.py import_customer_discounts --file /path/to/discounts.csv
```

Use only:

- `seed_output/production_export_20260329_clean/customers.csv`
- `seed_output/production_export_20260329_clean/contacts.csv`
- `seed_output/production_export_20260329_clean/discounts.csv`

Expected counts:

- customers `223`
- contacts `292`
- discounts `3`

## 5. Rate And FX Setup

- Upload approved rate cards in `Pricing -> Rate Management`.
- Load or refresh the current FX snapshot.
- Verify finance/admin users can access pricing controls.

Pass condition:

- rate cards appear in the UI
- no stale FX warning before quoting

## 6. Smoke Test

- Open an imported customer.
- Confirm contacts are attached.
- Confirm `Paradise Foods Limited` discount rows exist.
- Create one internal quote.
- Generate/export the quote PDF.
- Confirm branding, totals, and output look correct.

Pass condition:

- one full quote flow works end to end without errors

## 7. Hard Exclusions

Never import from dev:

- `160` dev quotes
- `4` dev shipments
- `3` dev shipment address-book entries
- placeholder/demo users
- old dev media files
