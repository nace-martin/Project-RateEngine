from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('pricing_v4', '0015_local_rates_decoupling'),
    ]

    operations = [
        migrations.AddField(
            model_name='localsellrate',
            name='is_additive',
            field=models.BooleanField(default=False, help_text='If True, adds a flat amount to the per-kg charge (PER_KG only).'),
        ),
        migrations.AddField(
            model_name='localsellrate',
            name='additive_flat_amount',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Flat amount added when is_additive=True (PER_KG only).', max_digits=10, null=True),
        ),
        migrations.AddField(
            model_name='localcogsrate',
            name='is_additive',
            field=models.BooleanField(default=False, help_text='If True, adds a flat amount to the per-kg charge (PER_KG only).'),
        ),
        migrations.AddField(
            model_name='localcogsrate',
            name='additive_flat_amount',
            field=models.DecimalField(blank=True, decimal_places=2, help_text='Flat amount added when is_additive=True (PER_KG only).', max_digits=10, null=True),
        ),
    ]
