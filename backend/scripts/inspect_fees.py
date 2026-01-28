"""
Utility: Inspect fees for a specific ratecard (Pricing V3).

Run from repo root:
  python backend/scripts/inspect_fees.py

Optional env var to override the ratecard name:
  RATECARD_NAME="PNG Domestic BUY Rates (Flat per KG)"
"""

import os
import sys


def _bootstrap_django() -> None:
    """Ensure `backend/` is importable and Django is configured."""
    repo_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
    )
    backend_path = os.path.join(repo_root, "backend")
    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "rate_engine.settings")

    import django  # noqa: WPS433 (local import after path bootstrap)

    django.setup()


def main() -> int:
    _bootstrap_django()

    from pricing_v3.models import RateCard, RateLine

    target_name = os.environ.get(
        "RATECARD_NAME", "PNG Domestic BUY Rates (Flat per KG)"
    )

    try:
        rc = RateCard.objects.get(name=target_name)
    except RateCard.DoesNotExist:
        print(f"RateCard not found: {target_name}")
        # List available for help
        print("Available RateCards:")
        for card in RateCard.objects.all()[:10]:
             print(f" - {card.name}")
        return 1

    print(f"RateCard Found: {rc.name} (ID: {rc.id})")
    
    # Iterate over lines and prefetch breaks for efficiency
    lines = RateLine.objects.filter(card=rc).select_related("component").prefetch_related("breaks")
    
    print(f"{'Component':<20} {'Method':<15} {'Unit':<10} {'Min Charge':<12} {'Rate/Percent'}")
    print("-" * 80)

    for line in lines:
        component_code = line.component.code
        method = line.method
        unit = line.unit or "-"
        min_charge = str(line.min_charge)
        
        # Determine rate display
        rate_display = "-"
        if line.percent_value:
            rate_display = f"{line.percent_value * 100}%"
        else:
            breaks = list(line.breaks.all())
            if breaks:
                if len(breaks) == 1:
                    rate_display = str(breaks[0].rate)
                else:
                    # Show range of rates or first one with a '+'
                    rate_display = f"{breaks[0].rate}..."
        
        print(f"{component_code:<20} {method:<15} {unit:<10} {min_charge:<12} {rate_display}")
    
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
