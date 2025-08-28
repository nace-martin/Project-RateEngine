from django.db import migrations, models
from django.db.models import Count


def dedupe_ratecards(apps, schema_editor):
    RateCard = apps.get_model('quotes', 'RateCard')
    # Find (origin, destination) groups with duplicates
    dups = (
        RateCard.objects
        .values('origin', 'destination')
        .annotate(cnt=Count('id'))
        .filter(cnt__gt=1)
    )
    for row in dups:
        origin = row['origin']
        destination = row['destination']
        qs = RateCard.objects.filter(origin=origin, destination=destination).order_by('-id')
        keep = qs.first()
        # Delete all others
        qs.exclude(id=keep.id).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0002_shipmentpiece'),
    ]

    operations = [
        migrations.RunPython(dedupe_ratecards, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name='ratecard',
            constraint=models.UniqueConstraint(fields=('origin', 'destination'), name='unique_ratecard_route'),
        ),
    ]

