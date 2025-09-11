from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0007_add_rate_type_to_currency_rates"),
    ]

    def create_unique_idx(apps, schema_editor):
        tables = set(schema_editor.connection.introspection.table_names())
        if 'currency_rates' in tables:
            try:
                schema_editor.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS currency_rates_unique_idx ON currency_rates (as_of_ts, base_ccy, quote_ccy, rate_type);"
                )
            except Exception:
                # If IF NOT EXISTS unsupported, try to create and ignore errors on duplicates
                try:
                    schema_editor.execute(
                        "CREATE UNIQUE INDEX currency_rates_unique_idx ON currency_rates (as_of_ts, base_ccy, quote_ccy, rate_type);"
                    )
                except Exception:
                    pass

    operations = [
        migrations.RunPython(create_unique_idx, reverse_code=migrations.RunPython.noop),
    ]
