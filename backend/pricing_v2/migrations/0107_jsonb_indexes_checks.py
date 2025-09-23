from django.db import migrations

SQL = r"""
-- Speed up JSON filters
CREATE INDEX IF NOT EXISTS quotes_req_snapshot_gin ON quotes USING gin (request_snapshot jsonb_path_ops);
CREATE INDEX IF NOT EXISTS ratecard_fees_applies_if_gin ON ratecard_fees USING gin (applies_if jsonb_path_ops);
CREATE INDEX IF NOT EXISTS service_items_conditions_gin ON service_items USING gin (conditions_json jsonb_path_ops);

-- Minimal JSON presence checks
ALTER TABLE ratecard_fees ADD CONSTRAINT chk_applies_if_has_kind CHECK (applies_if ? 'kind') NOT VALID;
ALTER TABLE service_items ADD CONSTRAINT chk_conditions_has_kind CHECK (conditions_json ? 'kind') NOT VALID;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0106_quotes_incomplete_flags")]
    operations = [migrations.RunSQL(SQL)]