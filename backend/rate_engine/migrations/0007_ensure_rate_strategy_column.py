from django.db import migrations, connection


def ensure_rate_strategy(apps, schema_editor):
    table = "ratecards"
    column = "rate_strategy"

    vendor = connection.vendor

    has_column = False
    if vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(f"PRAGMA table_info({table})")
            cols = [row[1] for row in cursor.fetchall()]  # row[1] = name
            has_column = column in cols
    else:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = %s
                """,
                [table, column],
            )
            has_column = cursor.fetchone() is not None

    if not has_column:
        with connection.cursor() as cursor:
            if vendor == "sqlite":
                cursor.execute(
                    "ALTER TABLE ratecards ADD COLUMN rate_strategy VARCHAR(32) DEFAULT 'BREAKS'"
                )
                # Existing rows get NULL; backfill to BREAKS for consistency
                cursor.execute(
                    "UPDATE ratecards SET rate_strategy = 'BREAKS' WHERE rate_strategy IS NULL"
                )
            elif vendor == "postgresql":
                cursor.execute(
                    "ALTER TABLE ratecards ADD COLUMN IF NOT EXISTS rate_strategy VARCHAR(32) DEFAULT 'BREAKS'"
                )
                cursor.execute(
                    "UPDATE ratecards SET rate_strategy = 'BREAKS' WHERE rate_strategy IS NULL"
                )
            else:
                # Fallback generic SQL (may not support IF NOT EXISTS)
                cursor.execute(
                    "ALTER TABLE ratecards ADD COLUMN rate_strategy VARCHAR(32)"
                )
                cursor.execute(
                    "UPDATE ratecards SET rate_strategy = 'BREAKS' WHERE rate_strategy IS NULL"
                )


class Migration(migrations.Migration):
    dependencies = [
        ("rate_engine", "0006_add_rate_strategy_to_ratecards"),
    ]

    operations = [
        migrations.RunPython(ensure_rate_strategy, migrations.RunPython.noop),
    ]

