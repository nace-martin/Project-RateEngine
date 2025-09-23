from django.db import migrations

DDL = r"""
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Weight-band overlap shield per ratecard
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname='cartage_ladders_no_overlap'
    ) THEN
        ALTER TABLE cartage_ladders ADD CONSTRAINT cartage_ladders_no_overlap EXCLUDE USING gist (
            ratecard_id WITH =,
            numrange(min_weight_kg, max_weight_kg, '[]') WITH &&
        );
    END IF;
END
$$;

-- Storage tiers no-overlap per ratecard/group_code
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname='storage_tiers_no_overlap'
    ) THEN
        ALTER TABLE storage_tiers ADD CONSTRAINT storage_tiers_no_overlap EXCLUDE USING gist (
            ratecard_id WITH =,
            group_code WITH =,
            int4range(week_from, week_to, '[]') WITH &&
        );
    END IF;
END
$$;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0103_ratecards_exclusion_constraints")]
    operations = [migrations.RunSQL(DDL)]