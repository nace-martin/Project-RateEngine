from django.core.management.base import BaseCommand, CommandError
from accounts.models import CustomUser, OrganizationMembership
from rate_engine.models import Organizations


class Command(BaseCommand):
    help = "Grant a user quote access (can_quote=True) to all organizations for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--username",
            required=True,
            help="Username to grant access for (e.g., sales_user)",
        )
        parser.add_argument(
            "--view-costs",
            action="store_true",
            default=False,
            help="Also enable can_view_costs for the memberships (default: False)",
        )
        parser.add_argument(
            "--role",
            default="sales",
            help="Membership role label to set (default: sales)",
        )

    def handle(self, *args, **options):
        username = options["--username"] if "--username" in options else options.get("username")
        view_costs = bool(options.get("view_costs"))
        role = options.get("role") or "sales"

        try:
            user = CustomUser.objects.get(username=username)
        except CustomUser.DoesNotExist:
            raise CommandError(f"User '{username}' does not exist. Create it first (e.g., manage.py create_test_users).")

        orgs = list(Organizations.objects.all())
        if not orgs:
            self.stdout.write(self.style.WARNING("No organizations found. Seed them with: manage.py seed_organizations"))
            return

        created = 0
        updated = 0
        for org in orgs:
            mem, was_created = OrganizationMembership.objects.get_or_create(
                user=user,
                organization=org,
                defaults={
                    "role": role,
                    "can_quote": True,
                    "can_view_costs": view_costs,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(self.style.SUCCESS(f"Linked {username} to '{org.name}' (can_quote=True)"))
            else:
                changed = False
                if not mem.can_quote:
                    mem.can_quote = True
                    changed = True
                if view_costs and not mem.can_view_costs:
                    mem.can_view_costs = True
                    changed = True
                if role and mem.role != role:
                    mem.role = role
                    changed = True
                if changed:
                    mem.save()
                    updated += 1
                    self.stdout.write(self.style.WARNING(f"Updated membership for '{org.name}'"))

        self.stdout.write(self.style.SUCCESS(
            f"Done. Created {created}, updated {updated}, total orgs processed {len(orgs)}."
        ))

