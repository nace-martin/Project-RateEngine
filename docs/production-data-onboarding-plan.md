# Production Data Onboarding Plan

Last updated: 2026-03-29

This plan assumes:

- production is a clean-start database
- production data should be curated, not cloned wholesale from dev
- media storage uses the production Render persistent disk

## Source Rules

Use the dev environment only as a source of approved master data.

Allowed to migrate from dev after review:

- customer companies
- customer contacts
- customer discount rules
- rate cards that are current and approved for launch
- reference values needed by those imports

Do not migrate from dev:

- users, tokens, passwords, sessions
- quotes, shipments, events, audit history
- uploaded media files from old local/dev storage
- stale, duplicate, or test/demo accounts

Current dev exclusions confirmed on 2026-03-29:

- do not import the 160 existing dev quotes
- do not import the 4 existing dev shipments
- do not import the 3 existing dev shipment address-book entries
- treat those records as test-only operational data

## Recommended Order

1. Confirm persistent media disk is attached in production.
2. Verify production admin login and health endpoint.
3. Export and validate customers from dev.
4. Export and validate contacts from dev.
5. Export and validate customer discounts from dev.
6. Load approved rate cards into production.
7. Verify FX snapshot and finance controls.
8. Smoke-test one quote flow end to end.

## Customers

Use these repo-supported import commands in production:

```bash
python manage.py import_customers --file customers.csv --dry-run
python manage.py import_customers --file customers.csv
```

Use this CSV shape:

- `company_uuid` optional
- `company_name` required
- `tax_id` optional
- `is_agent` optional
- `is_carrier` optional
- `company_type` optional
- `preferred_quote_currency` optional
- `payment_term_default` optional
- `default_margin_percent` optional
- `min_margin_percent` optional

Production rule:

- remove test customers
- remove obsolete customers
- keep only launch-approved commercial profiles

## Contacts

Use these repo-supported import commands in production:

```bash
python manage.py import_contacts --file contacts.csv --dry-run
python manage.py import_contacts --file contacts.csv
```

For a full sync of approved contacts for imported companies:

```bash
python manage.py import_contacts --file contacts.csv --dry-run --strict-sync
python manage.py import_contacts --file contacts.csv --strict-sync
```

Use this CSV shape:

- `company_uuid` optional
- `company_name` required when `company_uuid` absent
- `email` required
- `first_name` or `full_name` required
- `last_name` optional
- `phone` optional
- `is_primary` optional

Production rule:

- only operational contacts used for quoting and customer communication

## Customer Discounts

Use these repo-supported import commands in production:

```bash
python manage.py import_customer_discounts --file discounts.csv --dry-run
python manage.py import_customer_discounts --file discounts.csv
```

Use this CSV shape:

- `customer_uuid` or `customer_name`
- `product_code_id` or `product_code`
- `discount_type`
- `discount_value`
- `currency` optional, defaults to `PGK`
- `min_charge` optional
- `max_charge` optional
- `valid_from` optional
- `valid_until` optional
- `notes` optional

Production rule:

- import only active commercial discounts that finance has approved

## Rate Cards

Current safest production path is the existing upload workflow rather than a raw DB copy.

Preferred path:

1. Export approved source rate sheets from dev or the original commercial source files.
2. Remove test lanes, superseded versions, and duplicate uploads.
3. Import through the production rate-card upload UI at `Pricing -> Rate Management`.
4. Validate the resulting logical cards in the production UI.

If you use API-level upload automation, the current backend upload endpoint is:

- `/api/v4/rates/upload/`

Production rule:

- treat rate cards as controlled commercial inputs, not as a DB table copy

## FX And Pricing Controls

For production launch:

- load or refresh the current FX snapshot first
- verify finance/admin access to pricing controls
- verify no stale FX warning before first live quote

Current recurring refresh command:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

## Verification Checklist

After each import set:

- customer count matches the approved source list
- spot-check 3 customers for tax ID, default currency, and payment terms
- spot-check 3 contacts for primary designation and active status
- spot-check 3 discount rows for product code and value correctness
- verify at least one uploaded rate card appears in Rate Management
- generate one internal quote using imported data

## Operational Recommendation

Do not point production directly at the dev database.

Instead:

- export curated CSV/source files from dev
- review them outside the app
- import them into production through commands or upload flows
- sign off each dataset before moving to the next one
