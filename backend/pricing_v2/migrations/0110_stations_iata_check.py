from django.db import migrations

SQL = r"""
-- Enforce 3-letter uppercase IATA in stations (stored as text in current schema)
ALTER TABLE stations ADD CONSTRAINT chk_stations_iata_len CHECK (length(iata)=3) NOT VALID;
-- Optional: normalize to uppercase
UPDATE stations SET iata = upper(iata);
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0109_currency_fk_other_tables")]
    operations = [migrations.RunSQL(SQL)]