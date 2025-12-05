import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from quotes.models import Quote

# Get quote QT-43
quote = Quote.objects.filter(quote_number='QT-43').first()
if quote:
    version = quote.versions.order_by('-version_number').first()
    print(f'Quote: {quote.quote_number}')
    print()
    print('All Lines:')
    for line in version.lines.all():
        sc = line.service_component
        print(f'  {sc.code}:')
        print(f'    cost_pgk: {line.cost_pgk}')
        print(f'    cost_fcy: {line.cost_fcy}')
        print(f'    cost_fcy_currency: {line.cost_fcy_currency}')
        print(f'    exchange_rate: {line.exchange_rate}')
        print(f'    cost_source: {line.cost_source}')
        print()
