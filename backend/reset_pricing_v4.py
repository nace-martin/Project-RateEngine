"""Reset pricing_v4 tables for clean migration"""
import sqlite3

conn = sqlite3.connect('db.sqlite3')
c = conn.cursor()

tables = [
    'product_codes',
    'export_cogs',
    'export_sell_rates',
    'import_cogs',
    'import_sell_rates',
    'domestic_cogs',
    'domestic_sell_rates',
]

for t in tables:
    try:
        c.execute(f'DROP TABLE IF EXISTS {t}')
        print(f'Dropped: {t}')
    except Exception as e:
        print(f'Error dropping {t}: {e}')

# Clean migration history
c.execute("DELETE FROM django_migrations WHERE app='pricing_v4'")
conn.commit()
conn.close()
print('Migration history cleared')
