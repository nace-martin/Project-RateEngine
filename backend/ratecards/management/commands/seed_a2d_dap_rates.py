"""
Legacy command retained only as a deprecation guard.

A2DDAPRate was decommissioned and archived into ratecards_a2d_dap_rate_archive
in migration 0012. Import destination local tariffs now live in
pricing_v4.LocalSellRate and pricing_v4.LocalCOGSRate.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'DEPRECATED: A2DDAPRate has been removed. Use Pricing V4 LocalSellRate seeds/imports.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Ignored. This command is deprecated.',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING('A2DDAPRate is decommissioned and cannot be seeded.'))
        self.stdout.write('Use one of the Pricing V4 pathways instead:')
        self.stdout.write('  1) python manage.py seed_import_dest_sell')
        self.stdout.write('  2) python manage.py seed_import_dest_sell_aud')
        self.stdout.write('  3) POST /api/v4/rates/local-sell/ (or CSV import)')
