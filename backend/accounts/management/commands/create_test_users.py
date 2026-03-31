from django.core.management.base import BaseCommand
from accounts.models import CustomUser

class Command(BaseCommand):
    help = 'Create test users with different roles'

    def handle(self, *args, **options):
        # Create test users with different roles
        users_data = [
            {
                'username': 'sales_user',
                'password': 'sales_password',
                'role': 'sales',
                'is_active': True,
            },
            {
                'username': 'manager_user',
                'password': 'manager_password',
                'role': 'manager',
                'is_active': True,
            },
            {
                'username': 'finance_user',
                'password': 'finance_password',
                'role': 'finance',
                'is_active': True,
            }
        ]

        for user_data in users_data:
            username = user_data['username']
            password = user_data['password']
            defaults = {
                'role': user_data['role'],
                'is_active': True,
            }
            user, created = CustomUser.objects.update_or_create(
                username=username,
                defaults=defaults,
            )

            user.set_password(password)
            user.save(update_fields=['password'])

            action = "Created" if created else "Updated"
            self.stdout.write(
                self.style.SUCCESS(f"{action} {user_data['role']} user: {user.username}")
            )

        # Ensure a default admin user exists for local development convenience
        admin_username = 'admin'
        admin_password = 'admin123'
        admin_defaults = {
            'email': 'admin@example.com',
            'role': 'admin',
            'is_active': True,
            'is_staff': True,
            'is_superuser': True,
        }

        admin_user, created = CustomUser.objects.update_or_create(
            username=admin_username,
            defaults=admin_defaults,
        )
        admin_user.set_password(admin_password)
        admin_user.save(update_fields=['password'])

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(f"{action} admin user: {admin_username}/{admin_password}")
        )

        self.stdout.write(
            self.style.SUCCESS("All test users created successfully!")
        )
