from django.db import migrations, models
from django.utils import timezone


def backfill_created_at(apps, schema_editor):
    RateCard = apps.get_model('quotes', 'RateCard')
    RateCard.objects.filter(created_at__isnull=True).update(created_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ('quotes', '0003_unique_ratecard_route'),
    ]

    operations = [
        # Add field allowing null for backfill
        migrations.AddField(
            model_name='ratecard',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=True),
        ),
        migrations.RunPython(backfill_created_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='ratecard',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, null=False),
        ),
        migrations.AddIndex(
            model_name='ratecard',
            index=models.Index(fields=['origin'], name='idx_ratecard_origin'),
        ),
        migrations.AddIndex(
            model_name='ratecard',
            index=models.Index(fields=['destination'], name='idx_ratecard_destination'),
        ),
    ]
