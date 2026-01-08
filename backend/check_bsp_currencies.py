"""Quick script to check what currencies BSP actually provides."""
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'rate_engine.settings')
django.setup()

from core.fx_providers.bsp_html import BspHtmlProvider

p = BspHtmlProvider()
html = p._fetch_html()
rates = p._parse_rates(html)

print("Available currencies on BSP website:")
print("-" * 50)
for k in sorted(rates.keys()):
    v = rates[k]
    print(f"  {k}: TT_BUY={v['TT_BUY']}, TT_SELL={v['TT_SELL']}")

print(f"\nTotal: {len(rates)} currencies")
