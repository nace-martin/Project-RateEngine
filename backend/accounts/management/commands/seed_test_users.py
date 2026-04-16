from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

User = get_user_model()

class Command(BaseCommand):
    help = 'Seeds the database with test users for E2E testing'

    def handle(self, *args, **options):
        default_organization = User._default_organization()
        users_data = [
            {
                'username': 'admin',
                'email': 'admin@example.com',
                'password': 'admin123',
                'role': 'admin',
                'department': User.DEPARTMENT_AIR_FREIGHT,
                'organization': default_organization,
                'is_active': True,
                'is_staff': True,
                'is_superuser': True
            },
            {
                'username': 'manager',
                'email': 'manager@example.com',
                'password': 'manager123',
                'role': 'manager',
                'department': User.DEPARTMENT_AIR_FREIGHT,
                'organization': default_organization,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'sales',
                'email': 'sales@example.com',
                'password': 'sales123',
                'role': 'sales',
                'department': User.DEPARTMENT_AIR_FREIGHT,
                'organization': default_organization,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            },
            {
                'username': 'finance',
                'email': 'finance@example.com',
                'password': 'finance123',
                'role': 'finance',
                'department': User.DEPARTMENT_AIR_FREIGHT,
                'organization': default_organization,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            },
            # Additional users for enhanced testing
            {
                'username': 'sales_sea',
                'email': 'sales_sea@example.com',
                'password': 'sales123',
                'role': 'sales',
                'department': User.DEPARTMENT_SEA_FREIGHT,
                'organization': default_organization,
                'is_active': True,
                'is_staff': False,
                'is_superuser': False
            }
        ]

        for user_data in users_data:
            username = user_data['username']
            password = user_data.pop('password')
            
            user, created = User.objects.update_or_create(
                username=username,
                defaults=user_data
            )
            
            # Always set password to ensure known state
            user.set_password(password)
            user.save()
            
            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f'{action} user: {username}'))
            
        self.stdout.write(self.style.SUCCESS('Successfully seeded test users'))
