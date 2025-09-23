from django.db import migrations

SQL = r"""
ALTER TABLE quote_lines ADD COLUMN IF NOT EXISTS side TEXT CHECK (side IN ('BUY','SELL')) DEFAULT 'SELL';

-- Make money precision consistent
ALTER TABLE quote_lines ALTER COLUMN unit_price TYPE NUMERIC(18,4),
ALTER COLUMN extended_price TYPE NUMERIC(18,2);

-- (Optional) migrate legacy is_buy/is_sell into side if present
UPDATE quote_lines SET side='BUY' WHERE is_buy = TRUE AND is_sell = FALSE;
UPDATE quote_lines SET side='SELL' WHERE is_sell = TRUE AND is_buy = FALSE;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0104_cartage_storage_no_overlap")]
    operations = [migrations.RunSQL(SQL)]