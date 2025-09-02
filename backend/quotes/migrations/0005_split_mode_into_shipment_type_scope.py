from django.db import migrations, models

def forwards_copy_mode(apps, schema_editor):
    Quote = apps.get_model('quotes', 'Quote')

    def map_shipment_type(mode):
        if not mode:
            return 'AIR'
        m = (mode or '').upper()
        if 'SEA' in m:
            return 'SEA'
        if 'CUSTOM' in m:
            return 'CUSTOMS'
        if 'INLAND' in m or 'TRUCK' in m or 'ROAD' in m:
            return 'INLAND'
        return 'AIR'

    def map_service_scope(mode):
        if not mode:
            return 'INTERNATIONAL'
        m = (mode or '').upper()
        if 'DOMESTIC' in m or m in {'AIR_DOMESTIC', 'SEA_DOMESTIC'}:
            return 'DOMESTIC'
        return 'INTERNATIONAL'

    BATCH = 1000
    last_id = 0
    while True:
        batch = list(
            Quote.objects.filter(id__gt=last_id).order_by('id')[:BATCH]
        )
        if not batch:
            break
        for q in batch:
            st = map_shipment_type(getattr(q, 'mode', None))
            sc = map_service_scope(getattr(q, 'mode', None))
            q.shipment_type = st
            q.service_scope = sc
        Quote.objects.bulk_update(batch, ['shipment_type', 'service_scope'])
        last_id = batch[-1].id

def backwards_reconstruct_mode(apps, schema_editor):
    Quote = apps.get_model('quotes', 'Quote')

    def join_mode(st, sc):
        st = (st or '').upper()
        sc = (sc or '').upper()
        if st == 'SEA' and sc == 'DOMESTIC':
            return 'SEA_DOMESTIC'
        if st == 'AIR' and sc == 'DOMESTIC':
            return 'AIR_DOMESTIC'
        if st in {'CUSTOMS', 'INLAND'}:
            return st
        return st or 'AIR'

    BATCH = 1000
    last_id = 0
    while True:
        batch = list(
            Quote.objects.filter(id__gt=last_id).order_by('id')[:BATCH]
        )
        if not batch:
            break
        for q in batch:
            q.mode = join_mode(getattr(q, 'shipment_type', None),
                               getattr(q, 'service_scope', None))
        Quote.objects.bulk_update(batch, ['mode'])
        last_id = batch[-1].id

class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0001_initial'),
    ]

    operations = [
        # Phase A: add new fields (nullable so we can backfill)
        migrations.AddField(
            model_name='quote',
            name='shipment_type',
            field=models.CharField(
                max_length=20, null=True, blank=True,
                help_text='AIR | SEA | CUSTOMS | INLAND'
            ),
        ),
        migrations.AddField(
            model_name='quote',
            name='service_scope',
            field=models.CharField(
                max_length=20, null=True, blank=True,
                help_text='INTERNATIONAL | DOMESTIC'
            ),
        ),

        # Phase B: data migration from legacy `mode`
        migrations.RunPython(forwards_copy_mode, backwards_reconstruct_mode),

        # Phase C: enforce NOT NULL and drop legacy `mode`
        migrations.AlterField(
            model_name='quote',
            name='shipment_type',
            field=models.CharField(
                max_length=20, null=False, default='AIR',
                help_text='AIR | SEA | CUSTOMS | INLAND'
            ),
        ),
        migrations.AlterField(
            model_name='quote',
            name='service_scope',
            field=models.CharField(
                max_length=20, null=False, default='INTERNATIONAL',
                help_text='INTERNATIONAL | DOMESTIC'
            ),
        ),
        migrations.RemoveField(
            model_name='quote',
            name='mode',
        ),
    ]
