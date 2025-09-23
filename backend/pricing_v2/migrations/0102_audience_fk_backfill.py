from django.db import migrations

FORWARD = r"""
-- Add FK columns
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS audience_id BIGINT;
ALTER TABLE pricing_policy ADD COLUMN IF NOT EXISTS audience_id BIGINT;

-- Backfill from text code via audiences.code
UPDATE organizations o SET audience_id = a.id FROM audiences a WHERE o.audience_id IS NULL AND o.audience = a.code;
UPDATE pricing_policy p SET audience_id = a.id FROM audiences a WHERE p.audience_id IS NULL AND p.audience = a.code;

-- Enforce FKs and (optionally) drop old text columns later
ALTER TABLE organizations ADD CONSTRAINT fk_orgs_audience FOREIGN KEY (audience_id) REFERENCES audiences(id);
ALTER TABLE pricing_policy ADD CONSTRAINT fk_policy_audience FOREIGN KEY (audience_id) REFERENCES audiences(id);

-- Keep originals for rollback; app code should start reading *_id
"""

BACKWARD = r"""
ALTER TABLE organizations DROP CONSTRAINT IF EXISTS fk_orgs_audience;
ALTER TABLE pricing_policy DROP CONSTRAINT IF EXISTS fk_policy_audience;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0101_currencies_units_and_fks")]
    operations = [migrations.RunSQL(FORWARD, BACKWARD)]