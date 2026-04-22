from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from django.db import transaction

from pricing_v4.models import RateChangeLog


AUDIT_FIELD_NAMES = {'created_at', 'updated_at', 'created_by', 'updated_by'}
REVISION_LINK_FIELD_NAMES = {'lineage_id', 'supersedes_rate'}


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}
    return value


def serialize_rate_snapshot(instance) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for field in instance._meta.concrete_fields:
        if field.is_relation:
            snapshot[field.name] = getattr(instance, field.attname)
        else:
            snapshot[field.name] = _serialize_value(getattr(instance, field.name))
    return snapshot


def create_rate_change_log(
    *,
    instance,
    actor,
    action: str,
    before_snapshot: dict[str, Any] | None,
    after_snapshot: dict[str, Any] | None,
) -> RateChangeLog:
    return RateChangeLog.objects.create(
        table_name=instance._meta.db_table,
        object_pk=str(instance.pk),
        actor=actor,
        action=action,
        lineage_id=getattr(instance, 'lineage_id', None),
        before_snapshot=before_snapshot,
        after_snapshot=after_snapshot,
    )


def ensure_rate_lineage(instance) -> UUID | None:
    if not hasattr(instance, 'lineage_id'):
        return None

    lineage_id = getattr(instance, 'lineage_id', None) or uuid4()
    if getattr(instance, 'lineage_id', None) != lineage_id:
        setattr(instance, 'lineage_id', lineage_id)
        instance.save(update_fields=['lineage_id'])
    return lineage_id


def get_rate_history_queryset(instance):
    history_qs = RateChangeLog.objects.filter(table_name=instance._meta.db_table)
    lineage_id = ensure_rate_lineage(instance)
    if lineage_id:
        return history_qs.filter(lineage_id=lineage_id).select_related('actor')
    return history_qs.filter(object_pk=str(instance.pk)).select_related('actor')


def _build_clone_data(source_instance, overrides: dict[str, Any], actor) -> dict[str, Any]:
    clone_data: dict[str, Any] = {}
    for field in source_instance._meta.concrete_fields:
        if (
            field.primary_key
            or field.auto_created
            or field.name in AUDIT_FIELD_NAMES
            or field.name in REVISION_LINK_FIELD_NAMES
        ):
            continue
        clone_data[field.name] = deepcopy(getattr(source_instance, field.name))

    clone_data.update(overrides)

    if hasattr(source_instance, 'lineage_id'):
        clone_data['lineage_id'] = ensure_rate_lineage(source_instance)
    if hasattr(source_instance, 'supersedes_rate_id'):
        clone_data['supersedes_rate'] = source_instance
    if hasattr(source_instance, 'created_by_id'):
        clone_data['created_by'] = actor
    if hasattr(source_instance, 'updated_by_id'):
        clone_data['updated_by'] = actor

    return clone_data


@transaction.atomic
def revise_rate_row(
    *,
    source_instance,
    validated_data: dict[str, Any],
    actor,
    retire_previous: bool = True,
):
    ensure_rate_lineage(source_instance)
    source_before = serialize_rate_snapshot(source_instance)
    model_cls = source_instance.__class__
    new_row = model_cls.objects.create(**_build_clone_data(source_instance, validated_data, actor))
    new_after = serialize_rate_snapshot(new_row)

    create_rate_change_log(
        instance=new_row,
        actor=actor,
        action=RateChangeLog.Action.REVISE,
        before_snapshot=source_before,
        after_snapshot=new_after,
    )

    if retire_previous:
        revision_start = new_row.valid_from
        if revision_start <= source_instance.valid_from:
            raise ValueError('Revision start date must be later than the source row valid_from when auto-retiring the prior row.')

        if source_instance.valid_from < revision_start <= source_instance.valid_until:
            source_instance.valid_until = revision_start - timedelta(days=1)
            update_fields = ['valid_until', 'updated_at']
            if hasattr(source_instance, 'updated_by_id'):
                source_instance.updated_by = actor
                update_fields.insert(1, 'updated_by')
            source_instance.save(update_fields=update_fields)

            create_rate_change_log(
                instance=source_instance,
                actor=actor,
                action=RateChangeLog.Action.REVISE,
                before_snapshot=source_before,
                after_snapshot=serialize_rate_snapshot(source_instance),
            )

    return new_row
