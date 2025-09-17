from django.core.management.base import BaseCommand
from decimal import Decimal

from organizations.models import Organizations


class Command(BaseCommand):
    help = "Seed a few demo organizations for local development"

    def handle(self, *args, **options):
        demo_orgs = [
            {
                "name": "Demo Org",
                "audience": "PGK_LOCAL",
                "default_sell_currency": "PGK",
                "gst_pct": Decimal("10.00"),
                "country_code": "PG",
            },
            {
                "name": "PNG Mining Co",
                "audience": "PGK_LOCAL",
                "default_sell_currency": "PGK",
                "gst_pct": Decimal("10.00"),
                "country_code": "PG",
            },
            {
                "name": "AU Importer Pty Ltd",
                "audience": "PGK_LOCAL",
                "default_sell_currency": "PGK",
                "gst_pct": Decimal("10.00"),
                "country_code": "AU",
            },
        ]

        created = 0
        for data in demo_orgs:
            obj, was_created = Organizations.objects.get_or_create(
                name=data["name"],
                defaults=data,
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Created organization: {obj.name}"))
            else:
                # Optionally update fields if they drift
                changed = False
                for k, v in data.items():
                    if getattr(obj, k) != v:
                        setattr(obj, k, v)
                        changed = True
                if changed:
                    obj.save()
                    self.stdout.write(self.style.WARNING(f"Updated organization: {obj.name}"))
                else:
                    self.stdout.write(self.style.NOTICE(f"Exists: {obj.name}"))

        self.stdout.write(self.style.SUCCESS(f"Organizations ready (created {created})."))


