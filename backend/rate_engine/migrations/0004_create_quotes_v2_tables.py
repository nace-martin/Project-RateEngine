from django.db import migrations, models


def create_quotes_v2_tables(apps, schema_editor):
    existing = set(schema_editor.connection.introspection.table_names())

    class QuotesV2(models.Model):
        id = models.BigAutoField(primary_key=True)
        organization = models.ForeignKey(
            'rate_engine.Organizations', on_delete=models.PROTECT
        )
        status = models.CharField(max_length=32, default='COMPLETE')
        request_snapshot = models.JSONField()
        buy_total = models.DecimalField(max_digits=14, decimal_places=2)
        sell_total = models.DecimalField(max_digits=14, decimal_places=2)
        currency = models.CharField(max_length=3)
        created_at = models.DateTimeField(auto_now_add=True)
        updated_at = models.DateTimeField(auto_now=True)

        class Meta:
            app_label = 'rate_engine'
            db_table = 'quotes_v2'

    class QuoteLinesV2(models.Model):
        id = models.BigAutoField(primary_key=True)
        quote = models.ForeignKey(
            QuotesV2, on_delete=models.CASCADE, related_name='lines'
        )
        code = models.CharField(max_length=64)
        description = models.TextField()
        is_buy = models.BooleanField()
        is_sell = models.BooleanField()
        qty = models.DecimalField(max_digits=12, decimal_places=3)
        unit = models.CharField(max_length=16)
        unit_price = models.DecimalField(max_digits=12, decimal_places=4)
        extended_price = models.DecimalField(max_digits=12, decimal_places=2)
        currency = models.CharField(max_length=3)
        manual_rate_required = models.BooleanField(default=False)

        class Meta:
            app_label = 'rate_engine'
            db_table = 'quote_lines_v2'

    if 'quotes_v2' not in existing:
        schema_editor.create_model(QuotesV2)
    if 'quote_lines_v2' not in existing:
        schema_editor.create_model(QuoteLinesV2)


def drop_quotes_v2_tables(apps, schema_editor):
    with schema_editor.connection.cursor() as cursor:
        # Drop child table first due to FK
        cursor.execute('''
            DROP TABLE IF EXISTS quote_lines_v2;
        ''')
        cursor.execute('''
            DROP TABLE IF EXISTS quotes_v2;
        ''')


class Migration(migrations.Migration):

    dependencies = [
        ("rate_engine", "0003_alter_quotelines_options_alter_quotes_options"),
    ]

    operations = [
        migrations.RunPython(create_quotes_v2_tables, reverse_code=drop_quotes_v2_tables),
    ]

