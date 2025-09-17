from django.core.management.base import BaseCommand
from django.db import connection, transaction


class Command(BaseCommand):
    help = "Dev-only: Truncate quotes and quote_lines tables and reset identity sequences."

    def handle(self, *args, **options):
        sql_statements = [
            "TRUNCATE TABLE quote_lines RESTART IDENTITY CASCADE;",
            "TRUNCATE TABLE quotes RESTART IDENTITY CASCADE;",
        ]

        with transaction.atomic():
            with connection.cursor() as cursor:
                for stmt in sql_statements:
                    cursor.execute(stmt)

        self.stdout.write(self.style.SUCCESS("Truncated quotes and quote_lines and reset identities."))
        self.stdout.write(self.style.WARNING("Next: run 'python manage.py migrate quotes' if you have pending schema changes."))

