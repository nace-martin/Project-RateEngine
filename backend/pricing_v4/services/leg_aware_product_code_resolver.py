from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from pricing_v4.contracts.charge_context import (
    PHASE_16D_RULE_VERSION,
    ChargeContext,
    CommercialPosition,
    LegRole,
    ProductCodeDomain,
    ProductCodeResolverBlockerCode,
    ProductCodeResolutionResult,
    ProductCodeResolutionStatus,
    TransportMode,
    coerce_charge_context,
)
from pricing_v4.models import CanonicalChargeType, ProductCode, ProductCodeContextRule


MANDATORY_CONTEXT_FIELDS: tuple[tuple[str, ProductCodeResolverBlockerCode], ...] = (
    ("canonical_charge_type", ProductCodeResolverBlockerCode.CONTEXT_MISSING_CANONICAL_CHARGE_TYPE),
    ("leg_role", ProductCodeResolverBlockerCode.CONTEXT_MISSING_LEG_ROLE),
    ("product_code_domain", ProductCodeResolverBlockerCode.CONTEXT_MISSING_PRODUCT_CODE_DOMAIN),
    ("commercial_position", ProductCodeResolverBlockerCode.CONTEXT_MISSING_COMMERCIAL_POSITION),
    ("transport_mode", ProductCodeResolverBlockerCode.CONTEXT_MISSING_TRANSPORT_MODE),
)


class LegAwareProductCodeResolver:
    """Deterministic Phase 16D ProductCode resolver.

    This dark-mode resolver never reads client/request direction claims and never
    mutates quotes, SPE charges, aliases, ProductCodes, rules or rates.
    """

    rule_version = PHASE_16D_RULE_VERSION

    def resolve(
        self,
        charge_context: ChargeContext | dict[str, Any],
        requested_product_code: ProductCode | int | str | None = None,
    ) -> ProductCodeResolutionResult:
        raw_blockers = self._raw_context_blockers(charge_context)
        if raw_blockers:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.CONTEXT_INCOMPLETE,
                review_reason="Charge context is incomplete or invalid for leg-aware ProductCode resolution.",
                blocker_codes=raw_blockers,
                audit_evidence={"missing_context": [code.value for code in raw_blockers], "rule_version": self.rule_version},
            )

        try:
            context = coerce_charge_context(charge_context)
        except Exception as exc:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.CONTEXT_INCOMPLETE,
                review_reason=f"Invalid charge context: {exc}",
                blocker_codes=[ProductCodeResolverBlockerCode.CONTEXT_MISSING_PRODUCT_CODE_DOMAIN],
                audit_evidence={"error": str(exc), "rule_version": self.rule_version},
            )

        missing = self._missing_context(context)
        if missing:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.CONTEXT_INCOMPLETE,
                resolved_context=context.to_audit_dict(),
                review_reason="Charge context is incomplete for leg-aware ProductCode resolution.",
                blocker_codes=missing,
                audit_evidence={"missing_context": [code.value for code in missing], "rule_version": self.rule_version},
            )

        rules = list(self._matching_rules(context))
        deterministic_result = self._resolve_from_rules(context, rules)
        if requested_product_code is None:
            return deterministic_result
        if deterministic_result.status != ProductCodeResolutionStatus.ASSIGNED:
            return deterministic_result

        requested_rejection = self._validate_requested_against_deterministic(
            context,
            requested_product_code,
            deterministic_result,
        )
        if requested_rejection is not None:
            return requested_rejection
        return deterministic_result

    def _raw_context_blockers(self, charge_context: ChargeContext | dict[str, Any]) -> list[ProductCodeResolverBlockerCode]:
        if isinstance(charge_context, ChargeContext):
            return []
        raw = charge_context if isinstance(charge_context, dict) else {}
        blockers: list[ProductCodeResolverBlockerCode] = []
        enum_fields = {
            "leg_role": LegRole,
            "product_code_domain": ProductCodeDomain,
            "commercial_position": CommercialPosition,
            "transport_mode": TransportMode,
        }
        for field_name, blocker in MANDATORY_CONTEXT_FIELDS:
            value = raw.get(field_name)
            if value is None or str(value).strip() == "":
                blockers.append(blocker)
                continue
            enum_cls = enum_fields.get(field_name)
            if enum_cls is not None:
                try:
                    enum_cls(str(value).strip().upper())
                except ValueError:
                    blockers.append(blocker)
        return blockers

    def _missing_context(self, context: ChargeContext) -> list[ProductCodeResolverBlockerCode]:
        missing: list[ProductCodeResolverBlockerCode] = []
        for field_name, blocker in MANDATORY_CONTEXT_FIELDS:
            value = getattr(context, field_name, None)
            if value is None or str(value).strip() == "":
                missing.append(blocker)
        if not context.normalized_canonical_charge_type():
            if ProductCodeResolverBlockerCode.CONTEXT_MISSING_CANONICAL_CHARGE_TYPE not in missing:
                missing.append(ProductCodeResolverBlockerCode.CONTEXT_MISSING_CANONICAL_CHARGE_TYPE)
        return missing

    def _matching_rules(self, context: ChargeContext) -> QuerySet[ProductCodeContextRule]:
        canonical_code = context.normalized_canonical_charge_type()
        return (
            ProductCodeContextRule.objects.select_related("canonical_charge_type", "product_code")
            .filter(
                canonical_charge_type__code=canonical_code,
                canonical_charge_type__is_active=True,
                product_code_domain=context.product_code_domain.value,
                product_code__domain=context.product_code_domain.value,
                leg_role=context.leg_role.value,
                commercial_position=context.commercial_position.value,
                transport_mode=context.transport_mode.value,
                is_active=True,
                review_status=ProductCodeContextRule.ReviewStatus.APPROVED,
                product_code__is_active=True,
                product_code__retired_at__isnull=True,
            )
            .filter(
                operational_location__in=["", context.normalized_operational_location()],
                calculation_basis__in=["", context.normalized_calculation_basis()],
                service_scope__in=["", context.normalized_service_scope()],
            )
        )

    def _resolve_from_rules(
        self,
        context: ChargeContext,
        rules: list[ProductCodeContextRule],
        all_candidates: list[dict[str, Any]] | None = None,
    ) -> ProductCodeResolutionResult:
        candidates = all_candidates if all_candidates is not None else [self._candidate_payload(rule, context) for rule in rules]
        if not rules:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.NOT_FOUND,
                resolved_context=context.to_audit_dict(),
                candidate_product_codes=candidates,
                review_reason="No active approved ProductCode context rule matches the trusted leg context.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_CONTEXT_RULE_NOT_FOUND],
                audit_evidence={"candidate_count": len(candidates), "rule_version": self.rule_version},
            )

        ranked = sorted(rules, key=lambda rule: (-self._specificity_for_context(rule, context), rule.priority, rule.id))
        top_specificity = self._specificity_for_context(ranked[0], context)
        top_rules = [rule for rule in ranked if self._specificity_for_context(rule, context) == top_specificity]

        # Priority must not hide an equal-specificity configuration conflict.
        distinct_products = {rule.product_code_id for rule in top_rules}
        if len(top_rules) != 1 or len(distinct_products) != 1:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.NEEDS_CLARIFICATION,
                resolved_context=context.to_audit_dict(),
                candidate_product_codes=candidates,
                clarification_question="Multiple ProductCodes are valid for the same leg context. Clarify the charge context or correct ProductCode context rules.",
                review_reason="Equal-specificity ProductCode context rules are ambiguous.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_CONTEXT_RULE_AMBIGUOUS],
                audit_evidence={
                    "top_specificity": top_specificity,
                    "top_rule_ids": [rule.id for rule in top_rules],
                    "candidate_count": len(candidates),
                    "rule_version": self.rule_version,
                },
            )

        selected_rule = top_rules[0]
        selected_product = selected_rule.product_code
        return ProductCodeResolutionResult(
            status=ProductCodeResolutionStatus.ASSIGNED,
            selected_product_code=selected_product.code,
            selected_product_code_id=selected_product.id,
            candidate_product_codes=candidates,
            resolved_context=context.to_audit_dict(),
            audit_evidence={
                "selected_rule_id": selected_rule.id,
                "selected_rule_specificity": top_specificity,
                "candidate_count": len(candidates),
                "rule_version": self.rule_version,
            },
        )

    def _specificity_for_context(self, rule: ProductCodeContextRule, context: ChargeContext) -> int:
        specificity = 0
        if rule.operational_location and rule.operational_location == context.normalized_operational_location():
            specificity += 1
        if rule.calculation_basis and rule.calculation_basis == context.normalized_calculation_basis():
            specificity += 1
        if rule.service_scope and rule.service_scope == context.normalized_service_scope():
            specificity += 1
        return specificity

    def _validate_requested_against_deterministic(
        self,
        context: ChargeContext,
        requested_product_code: ProductCode | int | str,
        deterministic_result: ProductCodeResolutionResult,
    ) -> ProductCodeResolutionResult | None:
        try:
            product_code = self._get_requested_product_code(requested_product_code)
        except ProductCode.DoesNotExist:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.REJECTED,
                resolved_context=deterministic_result.resolved_context,
                candidate_product_codes=deterministic_result.candidate_product_codes,
                review_reason="Requested ProductCode does not exist.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_DOMAIN_MISMATCH],
                audit_evidence={
                    **deterministic_result.audit_evidence,
                    "requested_product_code": str(requested_product_code),
                    "deterministic_product_code_id": deterministic_result.selected_product_code_id,
                    "rule_version": self.rule_version,
                },
            )

        if product_code.domain != context.product_code_domain.value:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.REJECTED,
                resolved_context=deterministic_result.resolved_context,
                candidate_product_codes=deterministic_result.candidate_product_codes,
                review_reason="Requested ProductCode domain does not match trusted leg domain.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_DOMAIN_MISMATCH],
                audit_evidence={
                    **deterministic_result.audit_evidence,
                    "requested_product_code": self._product_payload(product_code),
                    "deterministic_product_code_id": deterministic_result.selected_product_code_id,
                    "trusted_product_code_domain": context.product_code_domain.value,
                    "rule_version": self.rule_version,
                },
            )

        if not product_code.is_active or product_code.retired_at:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.REJECTED,
                resolved_context=deterministic_result.resolved_context,
                candidate_product_codes=deterministic_result.candidate_product_codes,
                review_reason="Requested ProductCode is inactive or retired.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_INACTIVE_OR_RETIRED],
                audit_evidence={
                    **deterministic_result.audit_evidence,
                    "requested_product_code": self._product_payload(product_code),
                    "deterministic_product_code_id": deterministic_result.selected_product_code_id,
                    "rule_version": self.rule_version,
                },
            )

        if product_code.id != deterministic_result.selected_product_code_id:
            return ProductCodeResolutionResult(
                status=ProductCodeResolutionStatus.REJECTED,
                resolved_context=deterministic_result.resolved_context,
                candidate_product_codes=deterministic_result.candidate_product_codes,
                review_reason="Requested ProductCode is not the deterministic result for the trusted leg context.",
                blocker_codes=[ProductCodeResolverBlockerCode.PRODUCTCODE_DOMAIN_MISMATCH],
                audit_evidence={
                    **deterministic_result.audit_evidence,
                    "requested_product_code": self._product_payload(product_code),
                    "deterministic_product_code_id": deterministic_result.selected_product_code_id,
                    "rule_version": self.rule_version,
                },
            )
        return None

    def _get_requested_product_code(self, requested_product_code: ProductCode | int | str) -> ProductCode:
        if isinstance(requested_product_code, ProductCode):
            return requested_product_code
        lookup = str(requested_product_code).strip()
        if lookup.isdigit():
            return ProductCode.objects.get(id=int(lookup))
        return ProductCode.objects.get(code=lookup)

    def _candidate_payload(self, rule: ProductCodeContextRule, context: ChargeContext) -> dict[str, Any]:
        payload = self._product_payload(rule.product_code)
        payload.update(
            {
                "rule_id": rule.id,
                "canonical_charge_type": rule.canonical_charge_type.code,
                "leg_role": rule.leg_role,
                "commercial_position": rule.commercial_position,
                "transport_mode": rule.transport_mode,
                "operational_location": rule.operational_location or None,
                "calculation_basis": rule.calculation_basis or None,
                "service_scope": rule.service_scope or None,
                "specificity": self._specificity_for_context(rule, context),
                "priority": rule.priority,
            }
        )
        return payload

    @staticmethod
    def _product_payload(product_code: ProductCode) -> dict[str, Any]:
        return {
            "id": product_code.id,
            "code": product_code.code,
            "description": product_code.description,
            "domain": product_code.domain,
            "is_active": product_code.is_active,
            "retired_at": product_code.retired_at.isoformat() if product_code.retired_at else None,
        }
