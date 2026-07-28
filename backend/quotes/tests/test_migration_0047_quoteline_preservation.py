import uuid
import warnings
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


MIGRATE_FROM = ('quotes', '0046_draftquotedecisiondb')
MIGRATE_0047 = ('quotes', '0047_quoteline_charge_context_json_and_more')
MIGRATE_TO = ('quotes', '0048_restore_quoteline_preservation_columns')
PRESERVED_COLUMNS = {
    'base_exchange_rate': ('DecimalField', Decimal('1.234567')),
    'caf_percent': ('DecimalField', Decimal('0.1250')),
    'provider_name': ('CharField', 'Sentinel Provider'),
}


class QuoteLineMigrationSafetyTests(TransactionTestCase):
    def tearDown(self):
        MigrationExecutor(connection).migrate([MIGRATE_TO])
        super().tearDown()
        connection.close()

    @staticmethod
    def _column_description():
        with connection.cursor() as cursor:
            return {
                column.name: column
                for column in connection.introspection.get_table_description(
                    cursor, 'quotes_quoteline'
                )
            }

    @staticmethod
    def _create_quote_snapshot(apps):
        Company = apps.get_model('parties', 'Company')
        Quote = apps.get_model('quotes', 'Quote')
        QuoteVersion = apps.get_model('quotes', 'QuoteVersion')
        QuoteLine = apps.get_model('quotes', 'QuoteLine')
        QuoteTotal = apps.get_model('quotes', 'QuoteTotal')

        company = Company.objects.create(
            name=f'Migration Safety {uuid.uuid4()}',
            is_customer=True,
        )
        quote = Quote.objects.create(
            customer=company,
            mode='AIR',
            shipment_type='IMPORT',
        )
        version = QuoteVersion.objects.create(quote=quote, version_number=1)
        line = QuoteLine.objects.create(
            quote_version=version,
            service_component=None,
            cost_pgk=Decimal('80.00'),
            sell_pgk=Decimal('100.00'),
            sell_pgk_incl_gst=Decimal('110.00'),
            sell_fcy=Decimal('100.00'),
            sell_fcy_incl_gst=Decimal('110.00'),
        )
        total = QuoteTotal.objects.create(
            quote_version=version,
            total_cost_pgk=Decimal('80.00'),
            total_sell_pgk=Decimal('100.00'),
            total_sell_pgk_incl_gst=Decimal('110.00'),
            total_sell_fcy=Decimal('100.00'),
            total_sell_fcy_incl_gst=Decimal('110.00'),
        )
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE quotes_quoteline '
                'SET base_exchange_rate = %s, caf_percent = %s, provider_name = %s '
                'WHERE id = %s',
                [
                    PRESERVED_COLUMNS['base_exchange_rate'][1],
                    PRESERVED_COLUMNS['caf_percent'][1],
                    PRESERVED_COLUMNS['provider_name'][1],
                    line.pk.hex,
                ],
            )
        return line.pk, total.pk

    def _assert_preserved_schema(self):
        descriptions = self._column_description()
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(
                cursor, 'quotes_quoteline'
            )
        for name, (field_type, _) in PRESERVED_COLUMNS.items():
            column = descriptions[name]
            self.assertTrue(column.null_ok)
            self.assertIsNone(column.default)
            self.assertEqual(
                connection.introspection.get_field_type(column.type_code, column),
                field_type,
            )
            self.assertFalse(any(
                name in constraint['columns']
                and (
                    constraint['index']
                    or constraint['unique']
                    or constraint['primary_key']
                    or constraint['foreign_key']
                )
                for constraint in constraints.values()
            ))

        if connection.vendor == 'sqlite':
            with connection.cursor() as cursor:
                sqlite_types = {
                    row[1]: row[2].lower()
                    for row in cursor.execute('PRAGMA table_info(quotes_quoteline)')
                }
            self.assertEqual(sqlite_types['base_exchange_rate'], 'decimal')
            self.assertEqual(sqlite_types['caf_percent'], 'decimal')
            self.assertEqual(sqlite_types['provider_name'], 'varchar(255)')
        elif connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT column_name, data_type, numeric_precision, numeric_scale, "
                    "character_maximum_length FROM information_schema.columns "
                    "WHERE table_name = 'quotes_quoteline' AND column_name IN %s",
                    [tuple(PRESERVED_COLUMNS)],
                )
                physical = {row[0]: row[1:] for row in cursor.fetchall()}
            self.assertEqual(physical['base_exchange_rate'], ('numeric', 12, 6, None))
            self.assertEqual(physical['caf_percent'], ('numeric', 10, 4, None))
            self.assertEqual(
                physical['provider_name'],
                ('character varying', None, None, 255),
            )

    def test_pre_0047_upgrade_preserves_columns_values_rows_ids_and_totals(self):
        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATE_FROM])
        old_apps = executor.loader.project_state([MIGRATE_FROM]).apps
        line_id, total_id = self._create_quote_snapshot(old_apps)
        line_count = old_apps.get_model('quotes', 'QuoteLine').objects.count()
        total_before = old_apps.get_model('quotes', 'QuoteTotal').objects.get(pk=total_id)
        total_values = (
            total_before.total_cost_pgk,
            total_before.total_sell_pgk,
            total_before.total_sell_pgk_incl_gst,
            total_before.total_sell_fcy,
            total_before.total_sell_fcy_incl_gst,
        )

        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATE_TO])
        apps = executor.loader.project_state([MIGRATE_TO]).apps

        self._assert_preserved_schema()
        self.assertEqual(apps.get_model('quotes', 'QuoteLine').objects.count(), line_count)
        line = apps.get_model('quotes', 'QuoteLine').objects.get(pk=line_id)
        self.assertEqual(line.base_exchange_rate, PRESERVED_COLUMNS['base_exchange_rate'][1])
        self.assertEqual(line.caf_percent, PRESERVED_COLUMNS['caf_percent'][1])
        self.assertEqual(line.provider_name, PRESERVED_COLUMNS['provider_name'][1])
        total = apps.get_model('quotes', 'QuoteTotal').objects.get(pk=total_id)
        self.assertEqual(
            (
                total.total_cost_pgk,
                total.total_sell_pgk,
                total.total_sell_pgk_incl_gst,
                total.total_sell_fcy,
                total.total_sell_fcy_incl_gst,
            ),
            total_values,
        )
        self.assertEqual(apps.get_model('quotes', 'ShipmentJourneyDB').objects.count(), 0)
        self.assertEqual(apps.get_model('quotes', 'ShipmentLegDB').objects.count(), 0)
        policies = apps.get_model('quotes', 'RouteAutomationPolicyDB').objects.all()
        self.assertEqual(policies.count(), 6)
        self.assertFalse(policies.filter(enabled=True).exists())

    def test_already_applied_0047_restores_missing_schema_and_warns_about_data(self):
        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATE_0047])
        apps = executor.loader.project_state([MIGRATE_0047]).apps
        line_id, total_id = self._create_quote_snapshot(apps)
        with connection.cursor() as cursor:
            for name in PRESERVED_COLUMNS:
                cursor.execute(f'ALTER TABLE quotes_quoteline DROP COLUMN {name}')

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            executor = MigrationExecutor(connection)
            executor.migrate([MIGRATE_TO])

        self._assert_preserved_schema()
        warning_text = ' '.join(str(item.message) for item in caught)
        self.assertIn('pre-0047 database backup', warning_text)
        apps = executor.loader.project_state([MIGRATE_TO]).apps
        line = apps.get_model('quotes', 'QuoteLine').objects.get(pk=line_id)
        self.assertIsNone(line.base_exchange_rate)
        self.assertIsNone(line.caf_percent)
        self.assertIsNone(line.provider_name)
        self.assertTrue(
            apps.get_model('quotes', 'QuoteTotal').objects.filter(pk=total_id).exists()
        )

    def test_fresh_database_migrates_from_zero(self):
        executor = MigrationExecutor(connection)
        executor.migrate([('quotes', None)])
        executor = MigrationExecutor(connection)
        executor.migrate([MIGRATE_TO])
        apps = executor.loader.project_state([MIGRATE_TO]).apps

        self._assert_preserved_schema()
        self.assertEqual(apps.get_model('quotes', 'ShipmentJourneyDB').objects.count(), 0)
        self.assertEqual(apps.get_model('quotes', 'ShipmentLegDB').objects.count(), 0)
        policies = apps.get_model('quotes', 'RouteAutomationPolicyDB').objects.all()
        self.assertEqual(policies.count(), 6)
        self.assertFalse(policies.filter(enabled=True).exists())
