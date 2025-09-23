from django.db import migrations

CREATE_AND_SEED_DDL = r"""
-- 1) Create lookup tables (idempotent)
CREATE TABLE IF NOT EXISTS currencies(
  code CHAR(3) PRIMARY KEY,
  name TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS units(
  code TEXT PRIMARY KEY,
  label TEXT
);

-- 2) Seed BEFORE constraints (covers existing/default rows)
INSERT INTO currencies(code,name) VALUES
  ('PGK','Papua New Guinean Kina'),
  ('AUD','Australian Dollar'),
  ('USD','US Dollar')
ON CONFLICT (code) DO NOTHING;

INSERT INTO units(code,label) VALUES
  ('KG','Kilogram'),
  ('CBM','Cubic Meter'),
  ('WM','Weight/M3'),
  ('EA','Each')
ON CONFLICT (code) DO NOTHING;
"""

ADD_FK_DDL = r"""
-- 3) Add FKs as NOT VALID (do not scan tables yet)
ALTER TABLE quotes
  ADD CONSTRAINT fk_quotes_currency
  FOREIGN KEY (currency) REFERENCES currencies(code) NOT VALID;

ALTER TABLE quote_lines
  ADD CONSTRAINT fk_quote_lines_currency
  FOREIGN KEY (currency) REFERENCES currencies(code) NOT VALID;

ALTER TABLE quote_lines
  ADD CONSTRAINT fk_quote_lines_unit
  FOREIGN KEY (unit) REFERENCES units(code) NOT VALID;
"""

FIX_DATA_DDL = r"""
-- Clean up orphaned data before validation
UPDATE quotes SET currency = 'USD' WHERE currency IS NULL OR currency = '';
UPDATE quote_lines SET currency = 'USD' WHERE currency IS NULL OR currency = '';
UPDATE quote_lines SET unit = 'EA' WHERE unit IS NULL OR unit = '';
"""

VALIDATE_FK_DDL = r"""
-- 4) Validate after seeds exist
ALTER TABLE quotes       VALIDATE CONSTRAINT fk_quotes_currency;
ALTER TABLE quote_lines  VALIDATE CONSTRAINT fk_quote_lines_currency;
ALTER TABLE quote_lines  VALIDATE CONSTRAINT fk_quote_lines_unit;
"""

class Migration(migrations.Migration):
    dependencies = []
    operations = [
        migrations.RunSQL(CREATE_AND_SEED_DDL),
        migrations.RunSQL(ADD_FK_DDL),
        migrations.RunSQL(FIX_DATA_DDL),
        migrations.RunSQL(VALIDATE_FK_DDL),
    ]