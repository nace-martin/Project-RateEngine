
from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Airport, Port, Location
import uuid

@receiver(post_save, sender=Airport)
def create_location_for_airport(sender, instance, created, **kwargs):
    """
    Automatically create or update a Location record when an Airport is saved.
    """
    if created:
        # Check if location already exists to avoid duplicates if manually created
        if not Location.objects.filter(airport=instance).exists():
            Location.objects.create(
                id=uuid.uuid4(),
                kind=Location.Kind.AIRPORT,
                name=instance.name,
                code=instance.iata_code,
                country=instance.city.country if instance.city else None,
                city=instance.city,
                airport=instance,
                is_active=True
            )
    else:
        # Update existing location if needed
        Location.objects.filter(airport=instance).update(
            name=instance.name,
            code=instance.iata_code,
            city=instance.city,
            country=instance.city.country if instance.city else None
        )

@receiver(post_save, sender=Port)
def create_location_for_port(sender, instance, created, **kwargs):
    """
    Automatically create or update a Location record when a Port is saved.
    """
    if created:
        if not Location.objects.filter(port=instance).exists():
            Location.objects.create(
                id=uuid.uuid4(),
                kind=Location.Kind.PORT,
                name=instance.name,
                code=instance.unlocode,
                country=instance.city.country if instance.city else None,
                city=instance.city,
                port=instance,
                is_active=True
            )
    else:
        Location.objects.filter(port=instance).update(
            name=instance.name,
            code=instance.unlocode,
            city=instance.city,
            country=instance.city.country if instance.city else None
        )
