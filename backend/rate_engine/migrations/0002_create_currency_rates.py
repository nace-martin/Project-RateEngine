from django.db import migrations, models


def create_currency_rates_table(apps, schema_editor):
    table_name = 'currency_rates'
    existing_tables = set(schema_editor.connection.introspection.table_names())

    if table_name in existing_tables:
        return

    # Define a lightweight model matching the desired schema
    class TempCurrencyRates(models.Model):
        id = models.BigAutoField(primary_key=True)
        as_of_ts = models.DateTimeField()
        base_ccy = models.TextField()
        quote_ccy = models.TextField()
        rate = models.DecimalField(max_digits=18, decimal_places=8)
        source = models.TextField(null=True, blank=True)

        class Meta:
            app_label = 'rate_engine'
            db_table = table_name

    schema_editor.create_model(TempCurrencyRates)


class Migration(migrations.Migration):
    dependencies = [
        ('rate_engine', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_currency_rates_table, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='currencyrates',
            constraint=models.UniqueConstraint(
                fields=['as_of_ts', 'base_ccy', 'quote_ccy'],
                name='currency_rates_unique',
            ),
        ),
    ]

