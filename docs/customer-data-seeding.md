# Customer Data Seeding

This project now includes safe, idempotent management commands for importing real customer data.

## Commands

- `python backend/manage.py prepare_customer_seed_csv --input <raw.csv> --customers-out <customers.csv> --contacts-out <contacts.csv>`
- `python backend/manage.py validate_customer_seed --customers <customers.csv> --contacts <contacts.csv>`
- `python backend/manage.py import_customers --file <customers.csv> --dry-run`
- `python backend/manage.py import_customers --file <customers.csv>`
- `python backend/manage.py import_contacts --file <contacts.csv> --dry-run`
- `python backend/manage.py import_contacts --file <contacts.csv>`
- `python backend/manage.py import_contacts --file <contacts.csv> --strict-sync`
- `python backend/manage.py import_customer_discounts --file <discounts.csv> --dry-run`
- `python backend/manage.py import_customer_discounts --file <discounts.csv>`

## Customers CSV

Required columns:
- `company_name`

Optional columns:
- `company_uuid`
- `tax_id`
- `is_agent`
- `is_carrier`
- `company_type`
- `preferred_quote_currency`
- `payment_term_default`
- `default_margin_percent`
- `min_margin_percent`

Notes:
- Upsert key is `company_uuid` when provided, otherwise `company_name` (case-insensitive).
- `is_customer` is always enforced to `true` by this command.
- `preferred_quote_currency` must exist in `core_currency.code`.
- `payment_term_default` must be `PREPAID` or `COLLECT`.

## Contacts CSV

Required columns:
- `company_name`
- `email`

Optional columns:
- `company_uuid`
- `full_name`
- `first_name`
- `last_name`
- `phone`
- `is_primary`

Notes:
- Upsert key is `email` (case-insensitive).
- Company is resolved by `company_uuid` first, then `company_name`.
- If `is_primary=true`, existing primary contacts for that company are demoted.
- Use `--allow-reassign` if a contact email must move to another company.
- Use `--strict-sync` to set `is_active=false` for existing active contacts missing from the import CSV (for companies included in that run).

## Recommended rollout

1. If your data is in raw sheet format, run `prepare_customer_seed_csv` first.
2. Run `validate_customer_seed`.
3. Run both imports with `--dry-run`.
4. Review the summary counts.
5. Run both imports without `--dry-run`.

## Discounts CSV

Required columns:
- `discount_type`
- `discount_value`
- one of `customer_uuid` or `customer_name`
- one of `product_code_id` or `product_code`

Optional columns:
- `currency` (defaults to `PGK`)
- `min_charge`
- `max_charge`
- `valid_from` (`YYYY-MM-DD`)
- `valid_until` (`YYYY-MM-DD`)
- `notes`
