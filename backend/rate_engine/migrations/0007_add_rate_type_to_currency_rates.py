from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0006_alter_quotes_status"),
    ]

    def add_rate_type_column(apps, schema_editor):
        # Only attempt if table exists; helpful for test DBs (e.g., sqlite) without the seed schema
        tables = set(schema_editor.connection.introspection.table_names())
        if 'currency_rates' in tables:
            try:
                schema_editor.execute(
                    "ALTER TABLE currency_rates ADD COLUMN IF NOT EXISTS rate_type VARCHAR(8) NOT NULL DEFAULT 'BUY';"
                )
            except Exception:
                # Fallback for engines without IF NOT EXISTS support
                try:
                    schema_editor.execute(
                        "ALTER TABLE currency_rates ADD COLUMN rate_type VARCHAR(8) NOT NULL DEFAULT 'BUY';"
                    )
                except Exception:
                    # Ignore if already exists or not supported
                    pass

    operations = [
        migrations.RunPython(add_rate_type_column, reverse_code=migrations.RunPython.noop),
    ]
