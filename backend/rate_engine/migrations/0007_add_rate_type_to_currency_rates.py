from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0006_alter_quotes_status"),
    ]

    operations = [
        migrations.RunSQL(
            sql=(
                """
                ALTER TABLE currency_rates
                ADD COLUMN IF NOT EXISTS rate_type VARCHAR(8) NOT NULL DEFAULT 'BUY';
                """
            ),
            reverse_sql=(
                """
                -- Safe reverse: do not drop the column automatically to avoid data loss.
                -- If needed, it can be removed manually.
                SELECT 1;
                """
            ),
        ),
    ]

