# Generated manually for Wave 3B2 architecture correction: clean margin semantics

from decimal import Decimal

from django.db import migrations, models


def ensure_launch_policy_markup_on_cost(apps, schema_editor):
    CommercialTermsPolicy = apps.get_model('pricing_v4', 'CommercialTermsPolicy')
    CommercialTermsPolicy.objects.filter(policy_code="LAUNCH-POLICY-2026").update(
        margin_percent=Decimal("20.00"),
        margin_method="MARKUP_ON_COST",
    )


def reverse_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [  # noqa: RUF012
        ('pricing_v4', '0042_seed_authoritative_commercial_terms_policy'),
    ]

    operations = [  # noqa: RUF012
        migrations.RemoveConstraint(
            model_name='commercialtermspolicy',
            name='comm_policy_margin_valid_range',
        ),
        migrations.RenameField(
            model_name='commercialtermspolicy',
            old_name='target_gross_margin_percent',
            new_name='margin_percent',
        ),
        migrations.AddField(
            model_name='commercialtermspolicy',
            name='margin_method',
            field=models.CharField(
                choices=[('MARKUP_ON_COST', 'Markup on Cost'), ('TARGET_GROSS_MARGIN', 'Target Gross Margin')],
                default='MARKUP_ON_COST',
                max_length=32,
            ),
        ),
        migrations.AddConstraint(
            model_name='commercialtermspolicy',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ('margin_percent__isnull', True),
                    models.Q(
                        ('margin_percent__gte', 0),
                        models.Q(('margin_method', 'MARKUP_ON_COST'), ('margin_percent__lt', 100), _connector='OR'),
                    ),
                    _connector='OR',
                ),
                name='comm_policy_margin_valid_range',
            ),
        ),
        migrations.AddConstraint(
            model_name='commercialtermspolicy',
            constraint=models.CheckConstraint(
                condition=models.Q(('margin_method__in', ['MARKUP_ON_COST', 'TARGET_GROSS_MARGIN'])),
                name='comm_policy_margin_method_valid',
            ),
        ),
        migrations.RunPython(ensure_launch_policy_markup_on_cost, reverse_noop),
    ]
