import os
import sys
from decimal import Decimal


BASE_DIR = os.path.dirname(__file__)  # backend/
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

import django  # noqa: E402

django.setup()

from rate_engine.engine import compute_quote, ShipmentInput, Piece  # noqa: E402


def main():
    payload = ShipmentInput(
        origin_iata="POM",
        dest_iata="LAE",
        shipment_type="DOMESTIC",
        service_scope="AIRPORT_AIRPORT",
        audience="PGK_LOCAL",
        sell_currency="PGK",
        pieces=[
            Piece(
                weight_kg=Decimal("50.0"),
                length_cm=Decimal("100"),
                width_cm=Decimal("50"),
                height_cm=Decimal("20"),
            )
        ],
    )

    res = compute_quote(payload)
    print("BUY:")
    for l in res.buy_lines:
        print(l.code, str(l.extended.amount), l.extended.currency, "-", l.description)

    print("SELL:")
    for l in res.sell_lines:
        print(l.code, str(l.extended.amount), l.extended.currency, "-", l.description)

    print("TOTALS:", {k: (str(v.amount), v.currency) for k, v in res.totals.items()})
    print("SNAPSHOT:", res.snapshot)


if __name__ == "__main__":
    main()

