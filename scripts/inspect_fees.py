"""
Utility: Inspect fees for a specific ratecard.

Run from repo root:
  python scripts/inspect_fees.py

Optional env var to override the ratecard name:
  RATECARD_NAME="PNG Domestic BUY Rates (Flat per KG)"
"""

import os
import sys


def _bootstrap_django() -> None:
    """Ensure `backend/` is importable and Django is configured."""
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
    backend_path = os.path.join(repo_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

    import django  # noqa: WPS433 (local import after path bootstrap)

    django.setup()


def main() -> int:
    _bootstrap_django()

    from rate_engine.models import Ratecards, RatecardFees  # type: ignore

    target_name = os.environ.get(
        "RATECARD_NAME", "PNG Domestic BUY Rates (Flat per KG)"
    )

    try:
        rc = Ratecards.objects.get(name=target_name)
    except Ratecards.DoesNotExist:
        print(f"Ratecard not found: {target_name}")
        return 1

    print("RC", rc.id)
    qs = RatecardFees.objects.filter(ratecard=rc).select_related("fee_type")
    for rf in qs.iterator():
        ft = rf.fee_type
        print(ft.code, ft.basis, str(rf.amount), str(rf.min_amount), rf.currency)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

