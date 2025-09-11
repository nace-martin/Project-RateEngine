from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0007_add_rate_type_to_currency_rates"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS currency_rates_unique_idx
                ON currency_rates (as_of_ts, base_ccy, quote_ccy, rate_type);
                """
            ),
            reverse_sql=(
                """
                DROP INDEX IF EXISTS currency_rates_unique_idx;
                """
            ),
        ),
    ]

