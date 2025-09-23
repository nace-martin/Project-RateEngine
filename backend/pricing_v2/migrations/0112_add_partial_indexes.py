from django.db import migrations

SQL = r"""
CREATE INDEX IF NOT EXISTS ratecards_active_idx ON ratecards (status) WHERE status = 'ACTIVE';
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0111_drop_legacy_audience_columns")]
    operations = [migrations.RunSQL(SQL)]