# Written by hand for Pilot Gate B3B: Rate Matrix contract schema (spec v2.1 section 3.5.1).

import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models

# Tables that must hold no rows before this migration runs in either direction.
# Hosted databases were not verified empty, so the migration checks for itself.
GUARDED_MODELS = (
    "CommercialProductCode",
    "CommercialChargeAlias",
    "RateSheet",
    "RateLine",
    "RateApplicability",
    "RateTier",
)


class RateMatrixTablesNotEmpty(RuntimeError):
    """Raised when a guarded table holds rows; the migration changes nothing."""


def assert_rate_matrix_tables_empty(apps, schema_editor):
    """Abort unless every guarded table is empty. Reads only; never changes rows."""
    alias = schema_editor.connection.alias
    populated = {}
    for model_name in GUARDED_MODELS:
        model = apps.get_model("pricing_v4", model_name)
        count = model.objects.using(alias).count()
        if count:
            populated[model._meta.db_table] = count

    if populated:
        detail = ", ".join(f"{table}={count}" for table, count in sorted(populated.items()))
        raise RateMatrixTablesNotEmpty(
            "pricing_v4.0044 refuses to run: expected empty Rate Matrix tables but found "
            f"rows ({detail}). No rows were changed. Review the existing data and obtain "
            "an explicit decision before retrying."
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [  # noqa: RUF012
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('pricing_v4', '0043_commercial_terms_margin_semantics'),
    ]

    operations = [  # noqa: RUF012
        # Forward: runs first, before any schema change.
        migrations.RunPython(assert_rate_matrix_tables_empty, noop),

        # CommercialProductCode: GST classification vocabulary and legacy mapping.
        migrations.RemoveConstraint(
            model_name='commercialproductcode',
            name='comm_product_code_gst_valid',
        ),
        migrations.AlterField(
            model_name='commercialproductcode',
            name='gst_treatment',
            field=models.CharField(
                choices=[('STANDARD', 'Standard'), ('ZERO_RATED', 'Zero Rated'), ('EXEMPT', 'Exempt')],
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name='commercialproductcode',
            constraint=models.CheckConstraint(
                condition=models.Q(('gst_treatment__in', ['STANDARD', 'ZERO_RATED', 'EXEMPT'])),
                name='comm_product_code_gst_valid',
            ),
        ),
        migrations.AddField(
            model_name='commercialproductcode',
            name='legacy_product_code',
            field=models.OneToOneField(
                blank=True,
                help_text='Legacy ProductCode this row mirrors while legacy remains runtime authority',
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='commercial_product_code',
                to='pricing_v4.productcode',
            ),
        ),

        # RateSheet: provenance and version identity.
        migrations.AddField(
            model_name='ratesheet',
            name='source_reference',
            field=models.CharField(
                help_text='Reference to the source tariff document this sheet was loaded from',
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name='ratesheet',
            name='created_by',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='+',
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name='ratesheet',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddConstraint(
            model_name='ratesheet',
            constraint=models.UniqueConstraint(
                fields=('name', 'version'),
                name='rate_sheet_name_version_uniq',
            ),
        ),
        migrations.AddConstraint(
            model_name='ratesheet',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(('source_reference', ''), _negated=True),
                    ('source_reference', django.db.models.functions.text.Trim('source_reference')),
                ),
                name='rate_sheet_source_reference_not_empty',
            ),
        ),

        # RateLine: per-kg plus flat charges.
        migrations.AddField(
            model_name='rateline',
            name='additive_flat_amount',
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text='Flat amount added to the per-kg charge (PER_KG only)',
                max_digits=18,
                null=True,
            ),
        ),
        migrations.AddConstraint(
            model_name='rateline',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('additive_flat_amount__isnull', True),
                    ('additive_flat_amount__gte', 0),
                    _connector='OR',
                ),
                name='rate_line_additive_flat_non_negative',
            ),
        ),
        migrations.AddConstraint(
            model_name='rateline',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('additive_flat_amount__isnull', True),
                    ('rate_basis', 'PER_KG'),
                    _connector='OR',
                ),
                name='rate_line_additive_flat_per_kg_only',
            ),
        ),

        # RateApplicability: explicit payment term (blank = any).
        migrations.AddField(
            model_name='rateapplicability',
            name='payment_term',
            field=models.CharField(
                blank=True,
                choices=[('PREPAID', 'Prepaid'), ('COLLECT', 'Collect')],
                help_text='Blank applies to any payment term',
                max_length=8,
            ),
        ),
        migrations.AddConstraint(
            model_name='rateapplicability',
            constraint=models.CheckConstraint(
                condition=models.Q(('payment_term__in', ['', 'PREPAID', 'COLLECT'])),
                name='rate_app_payment_term_valid',
            ),
        ),

        # Reverse: runs first when unapplying, before any schema change is undone.
        migrations.RunPython(noop, assert_rate_matrix_tables_empty),
    ]
