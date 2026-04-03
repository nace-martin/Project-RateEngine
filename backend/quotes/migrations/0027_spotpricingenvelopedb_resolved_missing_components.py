from django.db import migrations, models


def _normalize_missing_components(raw_value):
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        raw_list = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        raw_list = list(raw_value)
    else:
        return []
    return [str(item).upper() for item in raw_list if str(item).strip()]


def backfill_resolved_missing_components(apps, schema_editor):
    SpotPricingEnvelopeDB = apps.get_model("quotes", "SpotPricingEnvelopeDB")
    for envelope in SpotPricingEnvelopeDB.objects.all().only("id", "shipment_context_json"):
        ctx = envelope.shipment_context_json or {}
        envelope.resolved_missing_components = _normalize_missing_components(
            ctx.get("missing_components")
        )
        envelope.save(update_fields=["resolved_missing_components"])


class Migration(migrations.Migration):

    dependencies = [
        ("quotes", "0026_add_canonical_audit_metadata"),
    ]

    operations = [
        migrations.AddField(
            model_name="spotpricingenvelopedb",
            name="resolved_missing_components",
            field=models.JSONField(
                default=list,
                help_text="Cached list of SPOT components still missing actionable charges.",
            ),
        ),
        migrations.RunPython(
            backfill_resolved_missing_components,
            migrations.RunPython.noop,
        ),
    ]
