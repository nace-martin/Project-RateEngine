from django.core.management.base import BaseCommand

from parties.models import OperatingEntity, Organization


ORGANIZATION = "Express Freight Management"
OPERATING_ENTITIES = (
    {"code": "PNG", "name": "EFM PNG", "slug": "efm-png", "country_code": "PG"},
    {"code": "AUS", "name": "EFM Australia", "slug": "efm-australia", "country_code": "AU"},
    {"code": "FJI", "name": "EFM Fiji", "slug": "efm-fiji", "country_code": "FJ"},
    {"code": "SLB", "name": "EFM Solomon Islands", "slug": "efm-solomon-islands", "country_code": "SB"},
)


class Command(BaseCommand):
    help = "Idempotently seed canonical OperatingEntity records."

    def handle(self, *args, **options):
        organization, _ = Organization.objects.get_or_create(
            name=ORGANIZATION,
            defaults={"slug": "express-freight-management"},
        )
        created = updated = existing = 0
        for values in OPERATING_ENTITIES:
            entity, was_created = OperatingEntity.objects.get_or_create(
                organization=organization,
                code=values["code"],
                defaults=values,
            )
            if was_created:
                created += 1
            elif any(getattr(entity, key) != value for key, value in values.items()):
                for key, value in values.items():
                    setattr(entity, key, value)
                entity.save(update_fields=["name", "slug", "country_code", "is_active", "updated_at"])
                updated += 1
            else:
                existing += 1
        self.stdout.write(f"OperatingEntity seed complete: created={created}, updated={updated}, existing={existing}")
