from decimal import Decimal

from django.db import migrations


def _next_import_product_code_id(ProductCode):
    used_ids = set(
        ProductCode.objects.filter(id__gte=2000, id__lt=3000).values_list("id", flat=True)
    )
    for candidate in range(2900, 3000):
        if candidate not in used_ids:
            return candidate
    raise ValueError("No available extension 29xx ProductCode IDs remain for IMPORT domain.")


def _upsert_product_code(ProductCode, *, code, description, category, revenue_code, cost_code):
    defaults = {
        "description": description,
        "domain": "IMPORT",
        "category": category,
        "is_gst_applicable": False,
        "gst_rate": Decimal("0.0000"),
        "gst_treatment": "EXEMPT",
        "gl_revenue_code": revenue_code,
        "gl_cost_code": cost_code,
        "default_unit": "SHIPMENT",
        "percent_of_product_code": None,
    }

    product = ProductCode.objects.filter(code=code).first()
    if product is None:
        product = ProductCode(id=_next_import_product_code_id(ProductCode), code=code, **defaults)
    else:
        for field, value in defaults.items():
            setattr(product, field, value)
    product.save()
    return product


def _append_note(existing_notes, note):
    base = (existing_notes or "").strip()
    if note in base:
        return base
    return f"{base}\n{note}".strip() if base else note


def _repoint_alias(ChargeAlias, *, alias_text, match_type, mode_scope, direction_scope, old_code, new_product, note):
    normalized = alias_text.strip().casefold()
    aliases = list(
        ChargeAlias.objects.select_related("product_code").filter(
            normalized_alias_text=normalized,
            match_type=match_type,
            mode_scope=mode_scope,
            direction_scope=direction_scope,
        )
    )
    if not aliases:
        return

    correct_aliases = [alias for alias in aliases if alias.product_code_id == new_product.id]
    legacy_aliases = [alias for alias in aliases if alias.product_code.code == old_code]

    if correct_aliases:
        for alias in legacy_aliases:
            changed = False
            if alias.is_active:
                alias.is_active = False
                changed = True
            updated_notes = _append_note(alias.notes, note)
            if alias.notes != updated_notes:
                alias.notes = updated_notes
                changed = True
            if changed:
                alias.save(update_fields=["is_active", "notes"])
        return

    for alias in legacy_aliases:
        alias.product_code = new_product
        alias.notes = _append_note(alias.notes, note)
        alias.full_clean()
        alias.save(update_fields=["product_code", "notes", "normalized_alias_text"])


def forwards(apps, schema_editor):
    ProductCode = apps.get_model("pricing_v4", "ProductCode")
    ChargeAlias = apps.get_model("pricing_v4", "ChargeAlias")

    permit_code = _upsert_product_code(
        ProductCode,
        code="IMP-PRM-ORIGIN",
        description="Import Origin Permit / License",
        category="REGULATORY",
        revenue_code="4200",
        cost_code="5200",
    )
    customs_code = _upsert_product_code(
        ProductCode,
        code="IMP-CUS-CLR",
        description="Import Customs Clearance",
        category="CLEARANCE",
        revenue_code="4300",
        cost_code="5300",
    )

    _repoint_alias(
        ChargeAlias,
        alias_text="Export License",
        match_type="EXACT",
        mode_scope="IMPORT",
        direction_scope="ORIGIN",
        old_code="IMP-DOC-ORIGIN",
        new_product=permit_code,
        note="Repointed to IMP-PRM-ORIGIN by migration 0024.",
    )
    _repoint_alias(
        ChargeAlias,
        alias_text="CUS",
        match_type="EXACT",
        mode_scope="IMPORT",
        direction_scope="ORIGIN",
        old_code="IMP-AGENCY-ORIGIN",
        new_product=customs_code,
        note="Repointed to IMP-CUS-CLR by migration 0024.",
    )
    _repoint_alias(
        ChargeAlias,
        alias_text="Customs Clearance",
        match_type="EXACT",
        mode_scope="IMPORT",
        direction_scope="ORIGIN",
        old_code="IMP-AGENCY-ORIGIN",
        new_product=customs_code,
        note="Repointed to IMP-CUS-CLR by migration 0024.",
    )


def noop_reverse(apps, schema_editor):
    # Non-destructive on purpose: these ProductCodes and alias updates may be
    # referenced by live rate data once applied.
    return


class Migration(migrations.Migration):

    dependencies = [
        ("pricing_v4", "0023_chargealias"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
