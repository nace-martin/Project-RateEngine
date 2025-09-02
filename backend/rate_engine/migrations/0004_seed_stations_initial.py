from django.db import migrations, connection

STATIONS = [
    # Papua New Guinea (PG)
    ("POM", "Port Moresby", "PG"),
    ("LAE", "Lae / Nadzab", "PG"),
    ("HGU", "Mount Hagen", "PG"),
    ("RAB", "Rabaul / Tokua", "PG"),
    ("GUR", "Alotau / Gurney", "PG"),
    ("KVG", "Kavieng", "PG"),
    ("MAG", "Madang", "PG"),
    ("HKN", "Hoskins", "PG"),
    ("KIE", "Kieta / Aropa", "PG"),
    ("WWK", "Wewak", "PG"),
    ("VAI", "Vanimo", "PG"),
    ("TBG", "Tabubil", "PG"),

    # Australia (AU)
    ("BNE", "Brisbane", "AU"),
    ("SYD", "Sydney", "AU"),
    ("MEL", "Melbourne", "AU"),
    ("CNS", "Cairns", "AU"),
    ("PER", "Perth", "AU"),

    # Singapore (SG)
    ("SIN", "Singapore Changi", "SG"),

    # Hong Kong (HK)
    ("HKG", "Hong Kong Intl", "HK"),

    # Mainland China (CN)
    ("PVG", "Shanghai Pudong", "CN"),
    ("NGB", "Ningbo", "CN"),
    ("TSN", "Tianjin / Xingang", "CN"),
    ("TAO", "Qingdao", "CN"),
]

def seed_stations_forward(apps, schema_editor):
    """
    Idempotent seed for 'stations' table.
    Works on PostgreSQL and SQLite. Assumes a UNIQUE constraint on stations.iata.
    """
    vendor = connection.vendor
    with connection.cursor() as cur:
        if vendor == "postgresql":
            sql = """
                INSERT INTO stations (iata, city, country)
                VALUES (%s, %s, %s)
                ON CONFLICT (iata) DO NOTHING;
            """
            cur.executemany(sql, STATIONS)
        elif vendor == "sqlite":
            sql = """
                INSERT OR IGNORE INTO stations (iata, city, country)
                VALUES (?, ?, ?);
            """
            cur.executemany(sql, STATIONS)
        else:
            # Fallback via ORM if you ever change DB vendor
            Station = apps.get_model("rate_engine", "Station")
            for iata, city, country in STATIONS:
                Station.objects.get_or_create(iata=iata, defaults={"city": city, "country": country})

def seed_stations_reverse(apps, schema_editor):
    """
    Safe reverse: delete only the rows we inserted (by IATA code list).
    Won't touch any other stations you may have added later.
    """
    iatas = [row[0] for row in STATIONS]
    # Use vendor-agnostic parameterization
    placeholders = ", ".join(["%s"] * len(iatas)) if connection.vendor == "postgresql" else ", ".join(["?"] * len(iatas))
    sql = f"DELETE FROM stations WHERE iata IN ({placeholders})"
    with connection.cursor() as cur:
        cur.execute(sql, iatas)

class Migration(migrations.Migration):

    dependencies = [
        # Make sure this depends on the migration that created 'stations'
        # Update the tuple below to match your project (e.g., ('rate_engine','0001_initial'))
        ('rate_engine', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(seed_stations_forward, seed_stations_reverse),
    ]
