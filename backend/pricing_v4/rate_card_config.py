# backend/pricing_v4/rate_card_config.py
"""
Logical V4 pricing views for admin/reporting screens.

These definitions are intentionally aligned to the current V4 pricing
architecture, not the legacy V3 partner-rate-card model.

Each logical card describes:
- the business use-case shown in the UI
- the underlying source tables that currently support that use-case
- the pricing model used by the engine

This layer is read-only and exists to explain the current commercial model.
It does not drive quote calculations.
"""

FCY_CURRENCIES = ["AUD", "USD", "NZD", "EUR", "GBP", "SGD", "JPY", "CNY"]


LOGICAL_RATE_CARDS = [
    {
        "id": "export-collect-d2a",
        "name": "Export Collect D2A",
        "description": "Export collect pricing for PNG-origin shipments with local origin sell plus PGK lane sell.",
        "service_scope": "D2A",
        "domain": "EXPORT",
        "pricing_model": "Explicit sell rates",
        "source_tables": ["LocalSellRate", "ExportSellRate"],
        "notes": [
            "Local PNG export sell charges come from LocalSellRate with direction EXPORT.",
            "Lane-specific export sell charges come from ExportSellRate.",
            "Legacy Partner Rate Cards are not part of this pricing path.",
        ],
        "sources": [
            {
                "table": "LocalSellRate",
                "label": "Origin local sell",
                "pricing_role": "SELL",
                "direction": "EXPORT",
                "payment_term": "COLLECT",
                "currency_filter": ["PGK"],
            },
            {
                "table": "ExportSellRate",
                "label": "Lane sell",
                "pricing_role": "SELL",
                "currency_filter": ["PGK"],
            },
        ],
    },
    {
        "id": "export-prepaid-d2a",
        "name": "Export Prepaid D2A",
        "description": "Export prepaid pricing with PNG-origin local sell plus FCY lane sell.",
        "service_scope": "D2A",
        "domain": "EXPORT",
        "pricing_model": "Explicit sell rates",
        "source_tables": ["LocalSellRate", "ExportSellRate"],
        "notes": [
            "Local PNG export sell charges come from LocalSellRate with direction EXPORT.",
            "Lane-specific export sell charges come from ExportSellRate.",
            "Foreign-currency lane sell is maintained separately from local PGK sell.",
        ],
        "sources": [
            {
                "table": "LocalSellRate",
                "label": "Origin local sell",
                "pricing_role": "SELL",
                "direction": "EXPORT",
                "payment_term": "PREPAID",
                "currency_filter": ["PGK"],
            },
            {
                "table": "ExportSellRate",
                "label": "Lane sell",
                "pricing_role": "SELL",
                "currency_filter": FCY_CURRENCIES,
            },
        ],
    },
    {
        "id": "import-collect-a2d",
        "name": "Import Collect A2D",
        "description": "Import collect pricing with destination local sell and lane buy inputs used for cost-plus calculation.",
        "service_scope": "A2D",
        "domain": "IMPORT",
        "pricing_model": "Mixed: explicit local sell + cost-plus lane pricing",
        "source_tables": ["LocalSellRate", "ImportCOGS"],
        "notes": [
            "Destination local import sell charges come from LocalSellRate with direction IMPORT.",
            "Lane-specific import buy inputs come from ImportCOGS.",
            "The engine derives lane sell from buy-side inputs plus FX, CAF, and policy margin.",
            "ImportSellRate is not the primary launch data source for this flow.",
        ],
        "sources": [
            {
                "table": "LocalSellRate",
                "label": "Destination local sell",
                "pricing_role": "SELL",
                "direction": "IMPORT",
                "payment_term": "COLLECT",
            },
            {
                "table": "ImportCOGS",
                "label": "Lane buy inputs",
                "pricing_role": "COGS",
            },
        ],
    },
    {
        "id": "import-prepaid-a2d",
        "name": "Import Prepaid A2D",
        "description": "Import prepaid pricing with destination local sell and lane buy inputs used for cost-plus calculation.",
        "service_scope": "A2D",
        "domain": "IMPORT",
        "pricing_model": "Mixed: explicit local sell + cost-plus lane pricing",
        "source_tables": ["LocalSellRate", "ImportCOGS"],
        "notes": [
            "Destination local import sell charges come from LocalSellRate with direction IMPORT.",
            "Lane-specific import buy inputs come from ImportCOGS.",
            "The engine derives lane sell from buy-side inputs plus FX, CAF, and policy margin.",
            "ImportSellRate is not the primary launch data source for this flow.",
        ],
        "sources": [
            {
                "table": "LocalSellRate",
                "label": "Destination local sell",
                "pricing_role": "SELL",
                "direction": "IMPORT",
                "payment_term": "PREPAID",
            },
            {
                "table": "ImportCOGS",
                "label": "Lane buy inputs",
                "pricing_role": "COGS",
            },
        ],
    },
    {
        "id": "domestic-launch-sell",
        "name": "Domestic Launch Sell",
        "description": "Domestic sell tariffs for the launch corridors.",
        "service_scope": "A2A",
        "domain": "DOMESTIC",
        "pricing_model": "Explicit sell rates",
        "source_tables": ["DomesticSellRate"],
        "notes": [
            "Domestic customer-facing sell tariffs come from DomesticSellRate.",
            "Domestic buy-side rates remain separate in DomesticCOGS.",
        ],
        "sources": [
            {
                "table": "DomesticSellRate",
                "label": "Domestic sell",
                "pricing_role": "SELL",
                "currency_filter": ["PGK"],
            }
        ],
    },
]


def get_rate_card_config(card_id: str) -> dict | None:
    """Get a specific logical card definition by ID."""
    for card in LOGICAL_RATE_CARDS:
        if card["id"] == card_id:
            return card
    return None
