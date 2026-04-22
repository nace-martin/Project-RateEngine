from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from pricing_v4.models import ChargeAlias, ProductCode


class NormalizationStatus(str, Enum):
    MATCHED = "MATCHED"
    AMBIGUOUS = "AMBIGUOUS"
    UNMAPPED = "UNMAPPED"


class NormalizationMethod(str, Enum):
    EXACT_ALIAS = "EXACT_ALIAS"
    PATTERN_ALIAS = "PATTERN_ALIAS"
    NONE = "NONE"


@dataclass(frozen=True)
class ChargeNormalizationScope:
    mode_scope: str = ChargeAlias.ModeScope.ANY
    direction_scope: str = ChargeAlias.DirectionScope.ANY

    def normalized(self) -> "ChargeNormalizationScope":
        return ChargeNormalizationScope(
            mode_scope=_normalize_scope_value(
                self.mode_scope,
                valid_values=ChargeAlias.ModeScope.values,
                default=ChargeAlias.ModeScope.ANY,
                field_name="mode_scope",
            ),
            direction_scope=_normalize_scope_value(
                self.direction_scope,
                valid_values=ChargeAlias.DirectionScope.values,
                default=ChargeAlias.DirectionScope.ANY,
                field_name="direction_scope",
            ),
        )


@dataclass(frozen=True)
class ChargeNormalizationResult:
    resolved_charge_alias: ChargeAlias | None
    resolved_product_code: ProductCode | None
    normalization_status: NormalizationStatus
    normalization_method: NormalizationMethod
    raw_label: str
    normalized_label: str
    matched_alias_ids: tuple[int, ...] = ()
    candidate_count: int = 0


def normalize_charge_label(raw_label: str) -> str:
    return ChargeAlias.normalize_alias_text_value(raw_label)


def resolve_charge_alias(
    raw_label: str,
    *,
    mode_scope: str = ChargeAlias.ModeScope.ANY,
    direction_scope: str = ChargeAlias.DirectionScope.ANY,
) -> ChargeNormalizationResult:
    raw_value = str(raw_label or "")
    normalized_label = normalize_charge_label(raw_value)
    scope = ChargeNormalizationScope(
        mode_scope=mode_scope,
        direction_scope=direction_scope,
    ).normalized()

    if not normalized_label:
        return ChargeNormalizationResult(
            resolved_charge_alias=None,
            resolved_product_code=None,
            normalization_status=NormalizationStatus.UNMAPPED,
            normalization_method=NormalizationMethod.NONE,
            raw_label=raw_value,
            normalized_label=normalized_label,
        )

    scoped_aliases = _scoped_active_aliases(scope)

    exact_matches = list(
        scoped_aliases.filter(
            match_type=ChargeAlias.MatchType.EXACT,
            normalized_alias_text=normalized_label,
        )
    )
    exact_result = _build_resolution_result(
        raw_label=raw_value,
        normalized_label=normalized_label,
        candidates=exact_matches,
        method=NormalizationMethod.EXACT_ALIAS,
    )
    if exact_result is not None:
        return exact_result

    pattern_matches = [
        alias
        for alias in scoped_aliases.exclude(match_type=ChargeAlias.MatchType.EXACT)
        if _alias_matches(alias, normalized_label)
    ]
    pattern_result = _build_resolution_result(
        raw_label=raw_value,
        normalized_label=normalized_label,
        candidates=pattern_matches,
        method=NormalizationMethod.PATTERN_ALIAS,
    )
    if pattern_result is not None:
        return pattern_result

    return ChargeNormalizationResult(
        resolved_charge_alias=None,
        resolved_product_code=None,
        normalization_status=NormalizationStatus.UNMAPPED,
        normalization_method=NormalizationMethod.NONE,
        raw_label=raw_value,
        normalized_label=normalized_label,
    )


def _scoped_active_aliases(scope: ChargeNormalizationScope):
    normalized_scope = scope.normalized()
    return (
        ChargeAlias.objects.filter(
            is_active=True,
            mode_scope__in=_scope_filter_values(
                normalized_scope.mode_scope,
                any_value=ChargeAlias.ModeScope.ANY,
            ),
            direction_scope__in=_scope_filter_values(
                normalized_scope.direction_scope,
                any_value=ChargeAlias.DirectionScope.ANY,
            ),
        )
        .select_related("product_code")
        .order_by("priority", "id")
    )


def _scope_filter_values(value: str, *, any_value: str) -> list[str]:
    if value == any_value:
        return [any_value]
    return [any_value, value]


def _normalize_scope_value(
    value: str | None,
    *,
    valid_values: Iterable[str],
    default: str,
    field_name: str,
) -> str:
    normalized = str(value or "").strip().upper() or default
    valid = set(valid_values)
    if normalized not in valid:
        raise ValueError(f"{field_name} must be one of {sorted(valid)}.")
    return normalized


def _alias_matches(alias: ChargeAlias, normalized_label: str) -> bool:
    alias_value = alias.normalized_alias_text
    if alias.match_type == ChargeAlias.MatchType.CONTAINS:
        return alias_value in normalized_label
    if alias.match_type == ChargeAlias.MatchType.STARTS_WITH:
        return normalized_label.startswith(alias_value)
    if alias.match_type == ChargeAlias.MatchType.ENDS_WITH:
        return normalized_label.endswith(alias_value)
    return False


def _build_resolution_result(
    *,
    raw_label: str,
    normalized_label: str,
    candidates: list[ChargeAlias],
    method: NormalizationMethod,
) -> ChargeNormalizationResult | None:
    if not candidates:
        return None

    top_priority = candidates[0].priority
    winning_candidates = [candidate for candidate in candidates if candidate.priority == top_priority]
    matched_alias_ids = tuple(candidate.id for candidate in winning_candidates if candidate.id is not None)
    winning_product_codes = {candidate.product_code_id for candidate in winning_candidates}

    if len(winning_product_codes) > 1:
        return ChargeNormalizationResult(
            resolved_charge_alias=None,
            resolved_product_code=None,
            normalization_status=NormalizationStatus.AMBIGUOUS,
            normalization_method=method,
            raw_label=raw_label,
            normalized_label=normalized_label,
            matched_alias_ids=matched_alias_ids,
            candidate_count=len(winning_candidates),
        )

    winner = winning_candidates[0]
    return ChargeNormalizationResult(
        resolved_charge_alias=winner,
        resolved_product_code=winner.product_code,
        normalization_status=NormalizationStatus.MATCHED,
        normalization_method=method,
        raw_label=raw_label,
        normalized_label=normalized_label,
        matched_alias_ids=matched_alias_ids,
        candidate_count=len(winning_candidates),
    )
