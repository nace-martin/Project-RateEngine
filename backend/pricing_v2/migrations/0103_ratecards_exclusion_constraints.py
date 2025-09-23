from django.db import migrations

DDL = r"""
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Block overlapping effective windows for same (provider,audience,name)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname='ratecards_no_overlap'
    ) THEN
        ALTER TABLE ratecards ADD CONSTRAINT ratecards_no_overlap EXCLUDE USING gist (
            provider_id WITH =,
            audience_id WITH =,
            name WITH =,
            daterange(effective_date, COALESCE(expiry_date,'9999-12-31')) WITH &&
        );
    END IF;
END
$$;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0102_audience_fk_backfill")]
    operations = [migrations.RunSQL(DDL)]