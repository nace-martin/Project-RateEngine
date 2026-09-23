# Generated manually for Wave 3B1: Clean Database Architecture v2.1

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0040_delete_componentmargin'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS pricing_v3_quotespotcharge;
            DROP TABLE IF EXISTS pricing_v3_quotespotrate;
            DROP TABLE IF EXISTS pricing_v3_componentmargin;
            DROP TABLE IF EXISTS pricing_v3_localfeerule;
            DROP TABLE IF EXISTS pricing_v3_ratebreak;
            DROP TABLE IF EXISTS pricing_v3_rateline;
            DROP TABLE IF EXISTS pricing_v3_ratecard;
            DROP TABLE IF EXISTS pricing_v3_zonemember;
            DROP TABLE IF EXISTS pricing_v3_zone;
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
