from django.db import migrations

SQL = r"""
ALTER TABLE quotes ADD COLUMN IF NOT EXISTS is_incomplete BOOLEAN NOT NULL DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS incomplete_reason TEXT;
"""

class Migration(migrations.Migration):
    dependencies = [("pricing_v2","0105_quote_lines_side_precision")]
    operations = [migrations.RunSQL(SQL)]