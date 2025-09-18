
from django.db import migrations


REGION_MAP = {
    'PNG': 'PNG',
    'PGK': 'PNG',
    'AU': 'AU',
    'AUD': 'AU',
    'USD': 'USD',
    'OVERSEAS': 'OVERSEAS',
}

PARTY_MAP = {
    'CUSTOMER': 'CUSTOMER',
    'LOCAL': 'CUSTOMER',
    'AGENT': 'AGENT',
}

SETTLEMENT_VALUES = {'PREPAID', 'COLLECT'}


def normalise_audience(raw: str):
    tokens = [t.strip().upper() for t in raw.split('_') if t.strip()]
    region_token = tokens[0] if tokens else 'OVERSEAS'
    party_token = tokens[1] if len(tokens) >= 2 else ''
    settlement_token = tokens[2] if len(tokens) >= 3 else ''

    if party_token in SETTLEMENT_VALUES and not settlement_token:
        settlement_token = party_token
        party_token = ''

    region = REGION_MAP.get(region_token, region_token)
    party = PARTY_MAP.get(party_token, 'CUSTOMER')
    settlement = settlement_token if settlement_token in SETTLEMENT_VALUES else 'PREPAID'

    code = f"{region}_{party}_{settlement}"
    return region, party, settlement, code


def populate_audience(apps, schema_editor):
    Audience = apps.get_model('pricing', 'Audience')
    Ratecard = apps.get_model('pricing', 'Ratecards')

    audience_cache = {}

    distinct_codes = (
        Ratecard.objects.exclude(audience_old__isnull=True)
        .exclude(audience_old__exact='')
        .values_list('audience_old', flat=True)
        .distinct()
    )

    for raw_code in distinct_codes:
        region, party, settlement, code = normalise_audience(raw_code)
        audience, created = Audience.objects.get_or_create(
            party_type=party,
            region=region,
            settlement=settlement,
            defaults={'code': code, 'is_active': True},
        )
        if audience.code != code:
            audience.code = code
            audience.save(update_fields=['code'])
        audience_cache[raw_code] = audience

    for ratecard in Ratecard.objects.all():
        if not ratecard.audience_old:
            continue
        audience = audience_cache.get(ratecard.audience_old)
        if audience is None:
            region, party, settlement, code = normalise_audience(ratecard.audience_old)
            audience, _ = Audience.objects.get_or_create(
                party_type=party,
                region=region,
                settlement=settlement,
                defaults={'code': code, 'is_active': True},
            )
            if audience.code != code:
                audience.code = code
                audience.save(update_fields=['code'])
            audience_cache[ratecard.audience_old] = audience
        ratecard.audience = audience
        ratecard.save(update_fields=['audience'])


def unpopulate_audience(apps, schema_editor):
    Ratecard = apps.get_model('pricing', 'Ratecards')
    Ratecard.objects.update(audience=None)


class Migration(migrations.Migration):

    dependencies = [
        ('pricing', '0002_audience_model'),
    ]

    operations = [
        migrations.RunPython(populate_audience, unpopulate_audience),
    ]
