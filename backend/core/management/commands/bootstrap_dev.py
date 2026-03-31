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
        admin_role = getattr(User, "ROLE_ADMIN", "admin")

        user, created = User.objects.get_or_create(
            username=username,
            defaults={
                "email": email,
                "role": admin_role,
                "is_active": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        user.email = email
        if hasattr(user, "role"):
            user.role = admin_role
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.set_password(password)
        user.save()

        action = "Created" if created else "Reset"
        self.stdout.write(self.style.SUCCESS(f"{action} superuser '{username}'"))

        try:
            from rest_framework.authtoken.models import Token
            token, _ = Token.objects.get_or_create(user=user)
            self.stdout.write(self.style.SUCCESS(f"TOKEN: {token.key}"))
        except Exception:
            self.stdout.write("DRF authtoken not installed; skipping token.")

        self.stdout.write(self.style.SUCCESS("Bootstrap complete."))
