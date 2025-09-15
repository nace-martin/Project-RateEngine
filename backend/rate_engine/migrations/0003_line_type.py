from django.db import migrations, models

def forwards(apps, schema_editor):
    QuoteLines = apps.get_model('rate_engine', 'QuoteLines')
    for ql in QuoteLines.objects.all():
        ql.line_type = 'BUY' if getattr(ql, 'is_buy', False) else 'SELL'
        ql.save(update_fields=['line_type'])

def backwards(apps, schema_editor):
    QuoteLines = apps.get_model('rate_engine', 'QuoteLines')
    for ql in QuoteLines.objects.all():
        ql.is_buy = ql.line_type == 'BUY'
        ql.is_sell = ql.line_type == 'SELL'
        ql.save(update_fields=['is_buy', 'is_sell'])

class Migration(migrations.Migration):

    dependencies = [
        ('rate_engine', '0002_currency_rates_unique_rate_type'),
    ]

    operations = [
        migrations.AddField(
            model_name='quotelines',
            name='line_type',
            field=models.CharField(max_length=4, choices=[('BUY','Buy'),('SELL','Sell')], default='BUY'),
            preserve_default=False,
        ),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveField(
            model_name='quotelines',
            name='is_buy',
        ),
        migrations.RemoveField(
            model_name='quotelines',
            name='is_sell',
        ),
    ]
