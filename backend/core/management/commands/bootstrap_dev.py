# backend/core/management/commands/bootstrap_dev.py
import os
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

class Command(BaseCommand):
    help = "Idempotently ensure a dev superuser + DRF token exists and print the token."

    def handle(self, *args, **opts):
        User = get_user_model()
        username = os.getenv("DEV_ADMIN_USER", "nas")
        email = os.getenv("DEV_ADMIN_EMAIL", "nas@example.com")
        password = os.getenv("DEV_ADMIN_PASS", "ChangeMe123!")

        user, created = User.objects.get_or_create(
            username=username,
            defaults={"email": email, "is_staff": True, "is_superuser": True},
        )
        if created:
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Created superuser '{username}'"))
        else:
            self.stdout.write(f"Superuser '{username}' already exists")

        try:
            from rest_framework.authtoken.models import Token
            token, _ = Token.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(f"TOKEN: {token.key}"))
        except Exception:
            self.stdout.write("DRF authtoken not installed; skipping token.")
