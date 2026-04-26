from decimal import Decimal

from django.db import migrations


def _next_product_code_id(ProductCode, *, start, stop):
    used_ids = set(ProductCode.objects.filter(id__gte=start, id__lt=stop).values_list("id", flat=True))
    for candidate in range(start, stop):
        if candidate not in used_ids:
            return candidate
    raise ValueError(f"No available ProductCode IDs remain in range {start}-{stop - 1}.")


def _upsert_product_code(
    ProductCode,
    *,
    code,
    description,
    domain,
    category,
    revenue_code,
    cost_code,
    id_start,
    id_stop,
    gst_treatment,
):
    defaults = {
        "description": description,
        "domain": domain,
        "category": category,
        "is_gst_applicable": gst_treatment == "STANDARD",
        "gst_rate": Decimal("0.1000") if gst_treatment == "STANDARD" else Decimal("0.0000"),
        "gst_treatment": gst_treatment,
        "gl_revenue_code": revenue_code,
        "gl_cost_code": cost_code,
        "default_unit": "SHIPMENT",
        "percent_of_product_code": None,
    }

    product = ProductCode.objects.filter(code=code).first()
    if product is None:
        product = ProductCode(id=_next_product_code_id(ProductCode, start=id_start, stop=id_stop), code=code)

    for field, value in defaults.items():
        setattr(product, field, value)
    product.save()
    return product


def _ensure_import_origin_customs_code(ProductCode):
    explicit = ProductCode.objects.filter(code="IMP-CUS-CLR-ORIGIN").first()
    legacy = ProductCode.objects.filter(code="IMP-CUS-CLR").first()
    defaults = {
        "description": "Import Origin Customs Clearance",
        "domain": "IMPORT",
        "category": "CLEARANCE",
        "is_gst_applicable": False,
        "gst_rate": Decimal("0.0000"),
        "gst_treatment": "EXEMPT",
        "gl_revenue_code": "4300",
        "gl_cost_code": "5300",
        "default_unit": "SHIPMENT",
        "percent_of_product_code": None,
    }

    if explicit is None and legacy is not None:
        legacy.code = "IMP-CUS-CLR-ORIGIN"
        for field, value in defaults.items():
            setattr(legacy, field, value)
        legacy.save()
        return legacy

    if explicit is None:
        explicit = ProductCode(id=_next_product_code_id(ProductCode, start=2900, stop=3000), code="IMP-CUS-CLR-ORIGIN")

    for field, value in defaults.items():
        setattr(explicit, field, value)
    explicit.save()
    return explicit


def _append_note(existing_notes, note):
    base = (existing_notes or "").strip()
    if note in base:
        return base
    return f"{base}\n{note}".strip() if base else note


def _repoint_aliases(ChargeAlias, *, alias_text, mode_scope, direction_scope, new_product, note):
    normalized = alias_text.strip().casefold()
    aliases = list(
        ChargeAlias.objects.filter(
            normalized_alias_text=normalized,
            match_type="EXACT",
            mode_scope=mode_scope,
            direction_scope=direction_scope,
        )
    )
    if not aliases:
        return

    correct_aliases = [alias for alias in aliases if alias.product_code_id == new_product.id]
    legacy_aliases = [alias for alias in aliases if alias.product_code_id != new_product.id]

    if correct_aliases:
        for alias in legacy_aliases:
            alias.is_active = False
            alias.notes = _append_note(alias.notes, note)
            alias.save(update_fields=["is_active", "notes"])
        return

    for alias in legacy_aliases:
        alias.product_code = new_product
        alias.notes = _append_note(alias.notes, note)
        alias.save(update_fields=["product_code", "notes"])


def forwards(apps, schema_editor):
    ProductCode = apps.get_model("pricing_v4", "ProductCode")
    ChargeAlias = apps.get_model("pricing_v4", "ChargeAlias")

    import_origin_customs = _ensure_import_origin_customs_code(ProductCode)
    _upsert_product_code(
        ProductCode,
        code="EXP-PRM-ORIGIN",
        description="Export Origin Permit / License",
        domain="EXPORT",
        category="REGULATORY",
        revenue_code="4200",
        cost_code="5200",
        id_start=1900,
        id_stop=2000,
        gst_treatment="ZERO_RATED",
    )

    for alias_text in ("CUS", "Customs Clearance"):
        _repoint_aliases(
            ChargeAlias,
            alias_text=alias_text,
            mode_scope="IMPORT",
            direction_scope="ORIGIN",
            new_product=import_origin_customs,
            note="Repointed to IMP-CUS-CLR-ORIGIN by migration 0027.",
        )


def noop_reverse(apps, schema_editor):
    return


class Migration(migrations.Migration):

    dependencies = [
        ("pricing_v4", "0026_chargealias_operational_fields"),
    ]

    operations = [
        migrations.RunPython(forwards, noop_reverse),
    ]
