from django.db import migrations

SQL = r"""
ALTER TABLE organizations DROP COLUMN IF EXISTS audience;
ALTER TABLE pricing_policy DROP COLUMN IF EXISTS audience;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0110_stations_iata_check")] # Depends on the last migration in Pack A
    operations = [migrations.RunSQL(SQL)]