from django.db import migrations

SQL = r"""
DO $$
BEGIN
  -- ratecard_fees.currency → currencies
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_ratecard_fees_currency'
  ) THEN
    ALTER TABLE ratecard_fees
      ADD CONSTRAINT fk_ratecard_fees_currency
      FOREIGN KEY (currency) REFERENCES currencies(code) NOT VALID;
  END IF;

  -- service_items.currency → currencies
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'fk_service_items_currency'
  ) THEN
    ALTER TABLE service_items
      ADD CONSTRAINT fk_service_items_currency
      FOREIGN KEY (currency) REFERENCES currencies(code) NOT VALID;
  END IF;
END $$;

-- Validate after seeds exist
ALTER TABLE ratecard_fees  VALIDATE CONSTRAINT fk_ratecard_fees_currency;
ALTER TABLE service_items VALIDATE CONSTRAINT fk_service_items_currency;
"""

class Migration(migrations.Migration):
    dependencies = [
        ("pricing_v2", "0101_currencies_units_and_fks"),   # ensure currencies exists
        ("pricing_v2", "0108_route_legs_unique_seq"),      # keep your existing ordering
    ]
    operations = [migrations.RunSQL(SQL)]
