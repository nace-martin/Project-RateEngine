from django.db import migrations

SQL = r"""
-- One position per route
ALTER TABLE route_legs ADD CONSTRAINT route_legs_route_id_sequence_uniq UNIQUE (route_id, sequence);
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0107_jsonb_indexes_checks")]
    operations = [migrations.RunSQL(SQL)]