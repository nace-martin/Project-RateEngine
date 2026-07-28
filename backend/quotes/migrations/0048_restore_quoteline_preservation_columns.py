import warnings

from django.db import migrations


PRESERVED_COLUMNS = ('base_exchange_rate', 'caf_percent', 'provider_name')


def restore_missing_quote_line_columns(apps, schema_editor):
    QuoteLine = apps.get_model('quotes', 'QuoteLine')
    with schema_editor.connection.cursor() as cursor:
        existing = {
            column.name
            for column in schema_editor.connection.introspection.get_table_description(
                cursor, QuoteLine._meta.db_table
            )
        }
    missing = [name for name in PRESERVED_COLUMNS if name not in existing]
    for name in missing:
        schema_editor.add_field(QuoteLine, QuoteLine._meta.get_field(name))
    if missing:
        warnings.warn(
            'Restored missing quotes_quoteline columns: '
            f'{", ".join(missing)}. Schema is repaired, but previously populated '
            'values can only be recovered from a pre-0047 database backup.',
            RuntimeWarning,
            stacklevel=2,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('quotes', '0047_quoteline_charge_context_json_and_more'),
    ]

    operations = [
        migrations.RunPython(
            restore_missing_quote_line_columns,
            migrations.RunPython.noop,
        ),
    ]
