# backend/pricing_v4/rate_card_config.py
"""
Logical Rate Card Definitions

These define the 5 business-level rate cards as configured views over
existing V4 rate data. This is a read-only view layer - no impact on
pricing calculations or database schema.

Each card is defined by:
- name: Display name
- description: What this card contains
- domain: EXPORT/IMPORT/DOMESTIC
- rate_table: Which model to query (ExportSellRate, ImportSellRate, DomesticSellRate)
- currency_filter: PGK or FCY currencies (AUD/USD/etc.)
- origin_filter: Optional origin airport/zone filter
- destination_filter: Optional destination airport/zone filter
"""

# FCY = Foreign Currencies (non-PGK)
FCY_CURRENCIES = ['AUD', 'USD', 'NZD', 'EUR', 'GBP', 'SGD', 'JPY', 'CNY']

LOGICAL_RATE_CARDS = [
    {
        'id': 'export-prepaid-d2a',
        'name': 'Export Prepaid D2A',
        'description': 'Origin, Clearance, Collection charges + Freight (PGK)',
        'service_scope': 'D2A',
        'domain': 'EXPORT',
        'rate_table': 'ExportSellRate',
        'currency_filter': ['PGK'],
        'origin_filter': None,  # All PNG origins
        'destination_filter': None,  # All destinations
    },
    {
        'id': 'export-collect-d2a',
        'name': 'Export Collect D2A',
        'description': 'Origin, Clearance, Collection charges + Freight (FCY)',
        'service_scope': 'D2A',
        'domain': 'EXPORT',
        'rate_table': 'ExportSellRate',
        'currency_filter': FCY_CURRENCIES,
        'origin_filter': None,
        'destination_filter': None,
    },
    {
        'id': 'import-collect-d2d',
        'name': 'Import Collect D2D',
        'description': 'Origin charges + Freight + Clearance & Delivery (PGK)',
        'service_scope': 'D2D',
        'domain': 'IMPORT',
        'rate_table': 'ImportSellRate',
        'currency_filter': ['PGK'],
        'origin_filter': None,
        'destination_filter': None,
    },
    {
        'id': 'import-prepaid-a2d',
        'name': 'Import Prepaid A2D',
        'description': 'Destination, Clearance & Delivery charges (FCY)',
        'service_scope': 'A2D',
        'domain': 'IMPORT',
        'rate_table': 'ImportSellRate',
        'currency_filter': FCY_CURRENCIES,
        'origin_filter': None,
        'destination_filter': None,
    },
    {
        'id': 'domestic-ex-pom',
        'name': 'Domestic ex-POM',
        'description': 'Domestic rates from Port Moresby (PGK)',
        'service_scope': None,
        'domain': 'DOMESTIC',
        'rate_table': 'DomesticSellRate',
        'currency_filter': ['PGK'],
        'origin_filter': ['POM'],  # POM zone only
        'destination_filter': None,
    },
]


def get_rate_card_config(card_id: str) -> dict | None:
    """Get a specific card config by ID."""
    for card in LOGICAL_RATE_CARDS:
        if card['id'] == card_id:
            return card
    return None
