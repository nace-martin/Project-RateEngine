from django.core.management.base import BaseCommand
from django.contrib.auth.hashers import make_password
from accounts.models import CustomUser

class Command(BaseCommand):
    help = 'Create test users with different roles'

    def handle(self, *args, **options):
        # Create test users with different roles
        users_data = [
            {
                'username': 'sales_user',
                'password': 'sales_password',
                'role': 'sales'
            },
            {
                'username': 'manager_user',
                'password': 'manager_password',
                'role': 'manager'
            },
            {
                'username': 'finance_user',
                'password': 'finance_password',
                'role': 'finance'
            }
        ]

        for user_data in users_data:
            # Check if user already exists
            if CustomUser.objects.filter(username=user_data['username']).exists():
                self.stdout.write(
                    self.style.WARNING(f"User {user_data['username']} already exists")
                )
                continue

            # Create user
            user = CustomUser.objects.create(
                username=user_data['username'],
                password=make_password(user_data['password']),
                role=user_data['role']
            )
            
            self.stdout.write(
                self.style.SUCCESS(f"Successfully created {user_data['role']} user: {user.username}")
            )

        self.stdout.write(
            self.style.SUCCESS("All test users created successfully!")
        )