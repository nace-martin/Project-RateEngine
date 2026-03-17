# Pre-Production Runbook

This runbook is the operator checklist for launching Project-RateEngine in production.

It is intentionally pragmatic:
- It focuses on what must exist for the app to work on day one.
- It calls out repo gaps where production setup is still manual.
- It uses commands that actually exist in this repository.

## Stop-Ship Criteria

Do not launch if any of these are false:

- A real `admin` user can log in and obtain an API token.
- Real `manager`, `finance`, and `sales` users exist.
- Launch customers and contacts are seeded.
- Launch stations exist as active `Location` records.
- A current FX snapshot exists.
- An active `Policy` exists.
- Required V4 product codes and rates exist for at least one real export lane and one real import lane.
- A quote can be created, finalized, and exported to PDF.

## Roles and Owners

- Platform/DevOps: environment, deploy, DB, static assets, schedulers
- Admin/Security: users, tokens, permissions
- Pricing Owner: product codes, policies, rate seeds, corridor coverage
- Finance: FX readiness and monitoring
- Customer Ops: customers, contacts, discounts
- QA/Business: end-to-end smoke tests

## Day Before Launch

### 1. Environment and Boot

Owner: Platform/DevOps

Required environment variables:

- `DATABASE_URL`
- `DJANGO_SECRET_KEY`
- `ALLOWED_HOSTS`
- `CORS_ALLOWED_ORIGINS`
- `CSRF_TRUSTED_ORIGINS`
- `FRONTEND_BASE_URL`
- `USE_X_FORWARDED_PROTO=true` if TLS terminates upstream

Commands:

```bash
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
```

Pass criteria:

- Django boots in production mode without configuration errors.
- Migrations complete successfully.
- Static files collect successfully.

### 2. Admin Access and Roles

Owner: Admin/Security

Commands:

```bash
python manage.py createsuperuser
python manage.py drf_create_token <admin_username>
```

After that:

- Create at least one named `manager` user.
- Create at least one named `finance` user.
- Create at least one named `sales` user.

Pass criteria:

- Admin can log in to UI and API.
- Each role can authenticate and sees expected access.

Do not use these in production:

- `python manage.py bootstrap_dev`
- `python manage.py create_test_users`
- `python manage.py seed_test_users`
- `python manage.py seed_v3_compute_data`

### 3. Core Geography and Lookup Data

Owner: Customer Ops with Pricing Owner

Use the built-in geography importer with your own launch dataset for:

- `Currency`
- `Country`
- `City`
- `Airport`
- `Location`

Recommended launch templates live under `docs/templates/reference-data-hub/`.
If you want to rebuild them, run `python scripts/build_reference_data_csvs.py --profile hub` from the repo root.

Dry-run first:

```bash
python manage.py import_reference_data \
  --currencies docs/templates/reference-data-hub/currencies.csv \
  --countries docs/templates/reference-data-hub/countries.csv \
  --cities docs/templates/reference-data-hub/cities.csv \
  --airports docs/templates/reference-data-hub/airports.csv \
  --locations docs/templates/reference-data-hub/locations.csv \
  --dry-run
```

Then apply:

```bash
python manage.py import_reference_data \
  --currencies docs/templates/reference-data-hub/currencies.csv \
  --countries docs/templates/reference-data-hub/countries.csv \
  --cities docs/templates/reference-data-hub/cities.csv \
  --airports docs/templates/reference-data-hub/airports.csv \
  --locations docs/templates/reference-data-hub/locations.csv
```

See `docs/reference-data-seeding.md` for the CSV field definitions and import notes.

Minimum launch scope:

- All currencies you will quote in: usually `PGK`, `AUD`, `USD`
- All countries used by launch lanes and customer addresses
- All cities needed for customer address forms
- All airports/stations needed for launch lanes
- Active `Location` rows for each quoted origin and destination

After loading location-related data:

```bash
python manage.py normalize_locations
```

Pass criteria:

- Customer address country/city selectors return expected values.
- Quote origin/destination search returns launch stations.
- Stations used by rate imports exist as active `Location` records.

### 4. Pricing Masters and Rate Seeds

Owner: Pricing Owner

Seed in this order.

Base product code registries:

```bash
python manage.py seed_import_product_codes
python manage.py seed_domestic_product_codes
```

Export corridor seeds:

```bash
python manage.py seed_export_pom_bne --year 2026
python manage.py seed_export_pom_syd --year 2026
python manage.py seed_pom_export_pgk
python manage.py seed_export_sell_fcy --year 2026
```

Import corridor seeds:

```bash
python manage.py seed_import_aus_pom
python manage.py seed_import_dest_cogs
python manage.py seed_import_dest_sell
python manage.py seed_import_dest_sell_aud
python manage.py seed_import_dest_sell_usd
```

Domestic seeds, only if domestic is live:

```bash
python manage.py seed_domestic_ex_pom
python manage.py seed_domestic_sell_freight
python manage.py seed_domestic_surcharges
python manage.py seed_domestic_sell_surcharges
```

Sync V4 product codes into service components used by quote line rendering/reporting:

```bash
python manage.py sync_v4_components
```

Optional, only if you use routing constraints or special lane tooling:

```bash
python manage.py seed_aircraft_types
python manage.py seed_syd_pom_lanes
```

Pass criteria:

- Launch corridors have product codes, sell rows, COGS rows, and any required surcharges.
- Export and import quotes do not fail due to missing mandatory pricing data.

### 5. Customers, Contacts, Discounts

Owner: Customer Ops

Recommended import order:

```bash
python manage.py validate_customer_seed --customers customers.csv --contacts contacts.csv

python manage.py import_customers --file customers.csv --dry-run
python manage.py import_customers --file customers.csv

python manage.py import_contacts --file contacts.csv --dry-run
python manage.py import_contacts --file contacts.csv
```

Optional customer discounts:

```bash
python manage.py import_customer_discounts --file discounts.csv --dry-run
python manage.py import_customer_discounts --file discounts.csv
```

Pass criteria:

- Customer search returns real customers.
- Contact dropdown loads contacts for those customers.
- First launch customers have valid commercial profiles if needed.

### 6. Policy and FX

Owner: Pricing Owner and Finance

There is no dedicated production policy seed command in this repo.
Create one active policy before first quote, either in admin or with a shell one-liner:

```bash
python manage.py shell -c "from core.models import Policy; from django.utils import timezone; from decimal import Decimal; Policy.objects.update_or_create(name='Launch Default Policy', defaults={'caf_import_pct':Decimal('0.05'),'caf_export_pct':Decimal('0.05'),'margin_pct':Decimal('0.20'),'effective_from':timezone.now(),'is_active':True})"
```

Load FX before first quote:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
```

Pass criteria:

- A current FX snapshot exists.
- FX status is not stale.
- New quotes pick up an active policy and current FX state.

## Launch Day

### 7. End-to-End Smoke Test

Owner: QA/Business with Pricing Owner

Run these checks in production:

- Log in as admin.
- Log in as sales.
- Search for a seeded customer.
- Load contacts for that customer.
- Search for launch origin and destination locations.
- Create one export quote on a live lane.
- Create one import quote on a live lane.
- Finalize both quotes.
- Generate PDF for both quotes.

Pass criteria:

- No empty critical dropdowns.
- No `has_missing_rates` block on launch-lane scenarios.
- Finalize succeeds.
- PDF export succeeds.

### 8. Operational Readiness Check

Owner: Platform/DevOps and Finance

Check:

- App logs are clean after first real traffic.
- FX status endpoint returns current data.
- Admin can access system settings and management screens.
- Finance can access FX management.
- Manager can access pricing and discounts.

Pass criteria:

- No recurring 500s.
- No auth/token failures.
- No FX exceptions.

## First Week After Launch

### 9. Schedule Operational Jobs

Owner: Platform/DevOps

There is no built-in scheduler wired into production compose. Schedule these externally:

```bash
python manage.py fetch_fx --pairs USD:PGK,PGK:USD,AUD:PGK,PGK:AUD
python manage.py cleanup_stale_drafts
python manage.py archive_quotes
```

Use this as a one-off repair or post-migration safety command:

```bash
python manage.py repair_quote_validity_windows --dry-run
```

Pass criteria:

- FX snapshots refresh daily.
- Stale draft cleanup runs without errors.
- Quote archiving runs without errors.

### 10. Post-Launch Monitoring

Owner: Pricing Owner and Customer Ops

Track:

- incomplete quotes by lane
- missing-rate incidents
- newly requested lanes with no seeded coverage
- customer import issues
- FX staleness incidents

Pass criteria:

- No repeated incomplete quotes on launch corridors.
- New customer/contact imports remain clean.
- Rate coverage gaps are identified before sales hits them in production.

## Repo Gaps You Must Handle Manually

- You still need to prepare the actual launch CSV datasets; the repo now provides the importer and templates, not the real geography source data
- No production bootstrap command for named non-admin users
- No dedicated production policy seed command
- No scheduler/cron wiring in `docker-compose.prod.yml`
- FX documentation references a refresh path that is not currently exposed by backend URL config

## Recommended Launch Minimum

If time is tight, the minimum viable launch state is:

- valid prod env vars
- successful migrate and collectstatic
- one real admin, manager, finance, and sales user
- currencies `PGK`, `AUD`, `USD`
- launch countries, airports, and active locations
- launch customers and contacts
- one active policy
- current FX snapshot
- seeded export and import pricing for actual launch corridors
- successful create, finalize, and PDF export for one export and one import quote
