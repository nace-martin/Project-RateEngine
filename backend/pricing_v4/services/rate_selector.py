from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Iterable, Sequence
from uuid import UUID

from django.db import models
from django.db.models import QuerySet

from pricing_v4.models import (
    DomesticCOGS,
    DomesticSellRate,
    ExportCOGS,
    ExportSellRate,
    ImportCOGS,
    ImportSellRate,
    LocalCOGSRate,
    LocalSellRate,
)


class RateSelectionError(Exception):
    pass


class RateNotFoundError(RateSelectionError):
    def __init__(self, model_name: str, context: 'RateSelectionContext', message: str | None = None):
        self.model_name = model_name
        self.context = context
        super().__init__(message or f'No {model_name} matched selection context.')


class RateAmbiguityError(RateSelectionError):
    def __init__(
        self,
        model_name: str,
        context: 'RateSelectionContext',
        *,
        stage: str,
        unresolved_dimensions: Sequence[str],
        candidates: Sequence[models.Model],
    ):
        self.model_name = model_name
        self.context = context
        self.stage = stage
        self.unresolved_dimensions = list(unresolved_dimensions)
        self.candidates = list(candidates)
        candidate_labels = ', '.join(_candidate_label(candidate) for candidate in self.candidates[:5])
        dims = ', '.join(self.unresolved_dimensions)
        super().__init__(
            f'Ambiguous {model_name} selection at stage {stage}; unresolved dimensions: {dims}. '
            f'Candidates: {candidate_labels}'
        )


@dataclass
class RateSelectionContext:
    product_code_id: int
    quote_date: date
    currency: str | None = None
    origin_airport: str | None = None
    destination_airport: str | None = None
    origin_zone: str | None = None
    destination_zone: str | None = None
    location: str | None = None
    direction: str | None = None
    payment_term: str | None = None
    agent_id: int | None = None
    carrier_id: int | None = None
    allowed_payment_terms: Sequence[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def normalized(self) -> 'RateSelectionContext':
        return RateSelectionContext(
            product_code_id=self.product_code_id,
            quote_date=self.quote_date,
            currency=_normalize_text(self.currency),
            origin_airport=_normalize_text(self.origin_airport),
            destination_airport=_normalize_text(self.destination_airport),
            origin_zone=_normalize_text(self.origin_zone),
            destination_zone=_normalize_text(self.destination_zone),
            location=_normalize_text(self.location),
            direction=_normalize_text(self.direction),
            payment_term=_normalize_text(self.payment_term),
            agent_id=self.agent_id,
            carrier_id=self.carrier_id,
            allowed_payment_terms=tuple(_normalize_text(value) for value in (self.allowed_payment_terms or ())),
            metadata=dict(self.metadata or {}),
        )


@dataclass
class RateSelectionResult:
    record: models.Model
    match_type: str
    fallback_applied: bool
    stage: str
    context: RateSelectionContext


def _serialize_scalar(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    return value


def _normalize_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _candidate_label(candidate: models.Model) -> str:
    parts = [f'#{candidate.pk}']
    if hasattr(candidate, 'currency'):
        parts.append(f'currency={getattr(candidate, "currency", None)}')
    if hasattr(candidate, 'agent_id') or hasattr(candidate, 'carrier_id'):
        parts.append(f'counterparty={_counterparty_signature(candidate)}')
    if hasattr(candidate, 'payment_term'):
        parts.append(f'payment_term={getattr(candidate, "payment_term", None)}')
    parts.append(f'valid_from={getattr(candidate, "valid_from", None)}')
    return ' '.join(parts)


def serialize_selection_context(context: RateSelectionContext) -> dict[str, Any]:
    normalized = context.normalized()
    payload = {
        'product_code_id': normalized.product_code_id,
        'quote_date': normalized.quote_date.isoformat(),
        'currency': normalized.currency,
        'origin_airport': normalized.origin_airport,
        'destination_airport': normalized.destination_airport,
        'origin_zone': normalized.origin_zone,
        'destination_zone': normalized.destination_zone,
        'location': normalized.location,
        'direction': normalized.direction,
        'payment_term': normalized.payment_term,
        'agent_id': normalized.agent_id,
        'carrier_id': normalized.carrier_id,
        'allowed_payment_terms': list(normalized.allowed_payment_terms or ()),
        'metadata': normalized.metadata or {},
    }
    return {key: value for key, value in payload.items() if value not in (None, '', [], {})}


def serialize_rate_candidate(candidate: models.Model) -> dict[str, Any]:
    fields = {
        'id': candidate.pk,
        'product_code_id': getattr(candidate, 'product_code_id', None),
        'currency': getattr(candidate, 'currency', None),
        'origin_airport': getattr(candidate, 'origin_airport', None),
        'destination_airport': getattr(candidate, 'destination_airport', None),
        'origin_zone': getattr(candidate, 'origin_zone', None),
        'destination_zone': getattr(candidate, 'destination_zone', None),
        'location': getattr(candidate, 'location', None),
        'direction': getattr(candidate, 'direction', None),
        'payment_term': getattr(candidate, 'payment_term', None),
        'agent_id': getattr(candidate, 'agent_id', None),
        'carrier_id': getattr(candidate, 'carrier_id', None),
        'valid_from': getattr(candidate, 'valid_from', None),
        'valid_until': getattr(candidate, 'valid_until', None),
        'lineage_id': getattr(candidate, 'lineage_id', None),
    }
    return {
        key: _serialize_scalar(value)
        for key, value in fields.items()
        if value is not None
    }


def resolve_missing_dimensions(
    unresolved_dimensions: Sequence[str],
    candidates: Sequence[models.Model],
) -> list[str]:
    missing_dimensions: list[str] = []
    for dimension in unresolved_dimensions:
        if dimension == 'currency':
            missing_dimensions.append('buy_currency')
            continue
        if dimension != 'counterparty':
            missing_dimensions.append(dimension)
            continue

        agent_ids = {
            getattr(candidate, 'agent_id', None)
            for candidate in candidates
            if getattr(candidate, 'agent_id', None) is not None
        }
        carrier_ids = {
            getattr(candidate, 'carrier_id', None)
            for candidate in candidates
            if getattr(candidate, 'carrier_id', None) is not None
        }

        if len(agent_ids) > 1 and not carrier_ids:
            missing_dimensions.append('agent_id')
        elif len(carrier_ids) > 1 and not agent_ids:
            missing_dimensions.append('carrier_id')
        elif len(agent_ids) == 1 and not carrier_ids:
            continue
        elif len(carrier_ids) == 1 and not agent_ids:
            continue
        elif agent_ids and carrier_ids:
            missing_dimensions.extend(['agent_id', 'carrier_id'])
        else:
            missing_dimensions.append('counterparty')

    ordered: list[str] = []
    for dimension in missing_dimensions:
        if dimension not in ordered:
            ordered.append(dimension)
    return ordered


def build_rate_selection_error_payload(
    error: RateSelectionError,
    *,
    component: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        'component': component,
        'selector_context': serialize_selection_context(getattr(error, 'context', None)) if getattr(error, 'context', None) else {},
        'detail': str(error),
    }

    if isinstance(error, RateAmbiguityError):
        missing_dimensions = resolve_missing_dimensions(error.unresolved_dimensions, error.candidates)
        payload.update(
            {
                'error_code': 'RATE_SELECTION_AMBIGUOUS',
                'model': error.model_name,
                'stage': error.stage,
                'missing_dimensions': missing_dimensions,
                'conflicting_rows': [serialize_rate_candidate(candidate) for candidate in error.candidates[:10]],
                'suggested_remediation': _build_remediation_message(missing_dimensions),
            }
        )
    elif isinstance(error, RateNotFoundError):
        payload.update(
            {
                'error_code': 'RATE_SELECTION_NOT_FOUND',
                'model': error.model_name,
                'missing_dimensions': [],
                'conflicting_rows': [],
                'suggested_remediation': 'Create or revise a rate row that matches the requested selector context.',
            }
        )
    else:
        payload.update(
            {
                'error_code': 'RATE_SELECTION_ERROR',
                'missing_dimensions': [],
                'conflicting_rows': [],
            }
        )
    return payload


def _build_remediation_message(missing_dimensions: Sequence[str]) -> str:
    if not missing_dimensions:
        return 'Retire or revise overlapping active rows so a single deterministic match remains.'

    labels = {
        'agent_id': 'agent',
        'carrier_id': 'carrier',
        'buy_currency': 'buy currency',
        'counterparty': 'counterparty',
    }
    readable = [labels.get(item, item.replace('_', ' ')) for item in missing_dimensions]
    if len(readable) == 1:
        return f'Provide {readable[0]} to resolve the rate selection.'
    return f"Provide these dimensions to resolve the rate selection: {', '.join(readable)}."


def _ordered(qs: QuerySet) -> QuerySet:
    return qs.order_by('-valid_from', '-updated_at', '-id')


def _active_queryset(model_cls: type[models.Model], quote_date: date) -> QuerySet:
    return _ordered(
        model_cls.objects.filter(
            valid_from__lte=quote_date,
            valid_until__gte=quote_date,
        )
    )


def _resolve_stage(
    *,
    qs: QuerySet,
    model_name: str,
    context: RateSelectionContext,
    stage: str,
    match_type: str,
    fallback_applied: bool,
    unresolved_dimensions: Sequence[str] = (),
) -> RateSelectionResult | None:
    candidates = list(qs[:20])
    if not candidates:
        return None

    for dimension in unresolved_dimensions:
        values = {_dimension_value(candidate, dimension) for candidate in candidates}
        if len(values) > 1:
            raise RateAmbiguityError(
                model_name,
                context,
                stage=stage,
                unresolved_dimensions=unresolved_dimensions,
                candidates=candidates,
            )

    return RateSelectionResult(
        record=candidates[0],
        match_type=match_type,
        fallback_applied=fallback_applied,
        stage=stage,
        context=context,
    )


def _dimension_value(candidate: models.Model, dimension: str) -> Any:
    if dimension == 'counterparty':
        return _counterparty_signature(candidate)
    return getattr(candidate, f'{dimension}_id', getattr(candidate, dimension, None))


def _counterparty_signature(candidate: models.Model) -> tuple[str, int | None]:
    agent_id = getattr(candidate, 'agent_id', None)
    carrier_id = getattr(candidate, 'carrier_id', None)
    if agent_id is not None:
        return ('agent', agent_id)
    if carrier_id is not None:
        return ('carrier', carrier_id)
    return ('none', None)


def _apply_counterparty_filter(qs: QuerySet, context: RateSelectionContext) -> tuple[QuerySet, Sequence[str]]:
    if context.agent_id is not None:
        return qs.filter(agent_id=context.agent_id, carrier__isnull=True), ()
    if context.carrier_id is not None:
        return qs.filter(carrier_id=context.carrier_id, agent__isnull=True), ()
    return qs, ('counterparty',)


def _lane_queryset(model_cls: type[models.Model], context: RateSelectionContext) -> QuerySet:
    context = context.normalized()
    qs = _active_queryset(model_cls, context.quote_date).filter(product_code_id=context.product_code_id)
    if context.origin_airport is not None:
        qs = qs.filter(origin_airport=context.origin_airport)
    if context.destination_airport is not None:
        qs = qs.filter(destination_airport=context.destination_airport)
    if context.origin_zone is not None:
        qs = qs.filter(origin_zone=context.origin_zone)
    if context.destination_zone is not None:
        qs = qs.filter(destination_zone=context.destination_zone)
    return qs


def _local_queryset(
    model_cls: type[models.Model],
    context: RateSelectionContext,
    *,
    queryset_override: QuerySet | None = None,
) -> QuerySet:
    context = context.normalized()
    qs = queryset_override if queryset_override is not None else _active_queryset(model_cls, context.quote_date)
    qs = _ordered(qs).filter(
        product_code_id=context.product_code_id,
        location=context.location,
        direction=context.direction,
    )
    return qs


def select_export_sell_rate(
    context: RateSelectionContext,
    *,
    allow_pgk_fallback: bool = False,
) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _lane_queryset(ExportSellRate, context)
    if context.currency:
        result = _resolve_stage(
            qs=base_qs.filter(currency=context.currency),
            model_name='ExportSellRate',
            context=context,
            stage='exact_currency',
            match_type='exact_currency',
            fallback_applied=False,
        )
        if result is not None:
            return result

    if allow_pgk_fallback and context.currency != 'PGK':
        result = _resolve_stage(
            qs=base_qs.filter(currency='PGK'),
            model_name='ExportSellRate',
            context=context,
            stage='pgk_fallback',
            match_type='pgk_fallback',
            fallback_applied=True,
        )
        if result is not None:
            return result

    if context.currency is None:
        result = _resolve_stage(
            qs=base_qs,
            model_name='ExportSellRate',
            context=context,
            stage='single_currency_only',
            match_type='single_currency_only',
            fallback_applied=True,
            unresolved_dimensions=('currency',),
        )
        if result is not None:
            return result

    raise RateNotFoundError('ExportSellRate', context)


def select_import_sell_rate(
    context: RateSelectionContext,
    *,
    allow_pgk_fallback: bool = False,
) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _lane_queryset(ImportSellRate, context)
    if context.currency:
        result = _resolve_stage(
            qs=base_qs.filter(currency=context.currency),
            model_name='ImportSellRate',
            context=context,
            stage='exact_currency',
            match_type='exact_currency',
            fallback_applied=False,
        )
        if result is not None:
            return result

    if allow_pgk_fallback and context.currency != 'PGK':
        result = _resolve_stage(
            qs=base_qs.filter(currency='PGK'),
            model_name='ImportSellRate',
            context=context,
            stage='pgk_fallback',
            match_type='pgk_fallback',
            fallback_applied=True,
        )
        if result is not None:
            return result

    if context.currency is None:
        result = _resolve_stage(
            qs=base_qs,
            model_name='ImportSellRate',
            context=context,
            stage='single_currency_only',
            match_type='single_currency_only',
            fallback_applied=True,
            unresolved_dimensions=('currency',),
        )
        if result is not None:
            return result

    raise RateNotFoundError('ImportSellRate', context)


def select_domestic_sell_rate(context: RateSelectionContext) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _lane_queryset(DomesticSellRate, context)
    if context.currency:
        result = _resolve_stage(
            qs=base_qs.filter(currency=context.currency),
            model_name='DomesticSellRate',
            context=context,
            stage='exact_currency',
            match_type='exact_currency',
            fallback_applied=False,
        )
        if result is not None:
            return result

    result = _resolve_stage(
        qs=base_qs,
        model_name='DomesticSellRate',
        context=context,
        stage='single_currency_only',
        match_type='single_currency_only',
        fallback_applied=context.currency is None,
        unresolved_dimensions=('currency',) if context.currency is None else (),
    )
    if result is not None:
        return result

    raise RateNotFoundError('DomesticSellRate', context)


def _select_counterparty_rate(
    model_cls: type[models.Model],
    context: RateSelectionContext,
    *,
    queryset_override: QuerySet | None = None,
) -> RateSelectionResult:
    context = context.normalized()
    base_qs = queryset_override if queryset_override is not None else _lane_queryset(model_cls, context)

    counterparty_qs, unresolved_counterparty = _apply_counterparty_filter(base_qs, context)
    if context.currency:
        result = _resolve_stage(
            qs=counterparty_qs.filter(currency=context.currency),
            model_name=model_cls.__name__,
            context=context,
            stage='exact_counterparty_exact_currency' if not unresolved_counterparty else 'single_counterparty_exact_currency',
            match_type='exact_currency',
            fallback_applied=bool(unresolved_counterparty),
            unresolved_dimensions=unresolved_counterparty,
        )
        if result is not None:
            return result
        raise RateNotFoundError(model_cls.__name__, context)

    unresolved_dimensions = list(unresolved_counterparty)
    unresolved_dimensions.append('currency')

    result = _resolve_stage(
        qs=counterparty_qs,
        model_name=model_cls.__name__,
        context=context,
        stage='single_counterparty_single_currency',
        match_type='single_counterparty_single_currency',
        fallback_applied=True,
        unresolved_dimensions=tuple(unresolved_dimensions),
    )
    if result is not None:
        return result

    raise RateNotFoundError(model_cls.__name__, context)


def select_export_cogs_rate(context: RateSelectionContext) -> RateSelectionResult:
    return _select_counterparty_rate(ExportCOGS, context)


def select_import_cogs_rate(context: RateSelectionContext) -> RateSelectionResult:
    return _select_counterparty_rate(ImportCOGS, context)


def select_domestic_cogs_rate(context: RateSelectionContext) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _lane_queryset(DomesticCOGS, context)
    return _select_counterparty_rate(DomesticCOGS, context, queryset_override=base_qs)


def select_local_cogs_rate(
    context: RateSelectionContext,
    *,
    queryset_override: QuerySet | None = None,
) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _local_queryset(LocalCOGSRate, context, queryset_override=queryset_override)
    return _select_counterparty_rate(LocalCOGSRate, context, queryset_override=base_qs)


def select_local_sell_rate(
    context: RateSelectionContext,
    *,
    queryset_override: QuerySet | None = None,
    allow_pgk_fallback: bool = False,
) -> RateSelectionResult:
    context = context.normalized()
    base_qs = _local_queryset(LocalSellRate, context, queryset_override=queryset_override)

    payment_term_candidates = list(context.allowed_payment_terms or ())
    if not payment_term_candidates:
        if context.payment_term:
            payment_term_candidates = [context.payment_term]
        else:
            payment_term_candidates = []
    if context.payment_term and 'ANY' not in payment_term_candidates:
        payment_term_candidates = [context.payment_term, 'ANY']
    elif 'ANY' in payment_term_candidates:
        ordered = [value for value in payment_term_candidates if value != 'ANY']
        payment_term_candidates = ordered + ['ANY']

    for payment_term_value in payment_term_candidates:
        stage_qs = base_qs.filter(payment_term=payment_term_value)
        if context.currency:
            result = _resolve_stage(
                qs=stage_qs.filter(currency=context.currency),
                model_name='LocalSellRate',
                context=context,
                stage=f'{payment_term_value.lower()}_exact_currency',
                match_type='exact_payment_term_exact_currency' if payment_term_value != 'ANY' else 'any_payment_term_exact_currency',
                fallback_applied=payment_term_value == 'ANY',
            )
            if result is not None:
                return result

    if allow_pgk_fallback and context.currency != 'PGK':
        for payment_term_value in payment_term_candidates:
            result = _resolve_stage(
                qs=base_qs.filter(payment_term=payment_term_value, currency='PGK'),
                model_name='LocalSellRate',
                context=context,
                stage=f'{payment_term_value.lower()}_pgk_fallback',
                match_type='pgk_fallback',
                fallback_applied=True,
            )
            if result is not None:
                return result

    if context.currency is None:
        for payment_term_value in payment_term_candidates:
            result = _resolve_stage(
                qs=base_qs.filter(payment_term=payment_term_value),
                model_name='LocalSellRate',
                context=context,
                stage=f'{payment_term_value.lower()}_single_currency_only',
                match_type='single_currency_only',
                fallback_applied=True,
                unresolved_dimensions=('currency',),
            )
            if result is not None:
                return result

    raise RateNotFoundError('LocalSellRate', context)
