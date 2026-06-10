# backend/quotes/services/spot_learning_service.py
"""
SPOT Resolution Learning Service

Records structured learning events when users resolve SPOT charge exceptions.
These events form the training corpus for future confidence-based auto-resolution.

Phase 10.3a: Recording only. No confidence scoring or auto-resolution yet.
"""

from __future__ import annotations

import logging
from typing import Optional

from django.utils import timezone

from quotes.spot_learning_models import SpotResolutionLearningEvent
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB

logger = logging.getLogger(__name__)


def _extract_shipment_context(envelope: SpotPricingEnvelopeDB) -> dict:
    """Extract denormalized shipment context fields from SPE for the learning event."""
    ctx = envelope.shipment_context_json or {}
    return {
        'origin_code': str(ctx.get('origin_code') or '').upper()[:5],
        'destination_code': str(ctx.get('destination_code') or '').upper()[:5],
        'mode': str(ctx.get('mode') or '').upper()[:10],
        'shipment_type': str(ctx.get('shipment_type') or '').upper()[:10],
        'service_scope': str(ctx.get('service_scope') or '').upper()[:10],
    }


def _extract_source_context(charge_line: SPEChargeLineDB) -> dict:
    """Extract source batch context from the charge line's parent source batch."""
    batch = charge_line.source_batch
    if batch is None:
        return {
            'source_kind': '',
            'source_label_supplier': '',
        }
    return {
        'source_kind': str(batch.source_kind or '')[:20],
        'source_label_supplier': str(batch.label or '')[:255],
    }


def record_manual_resolution_event(
    charge_line: SPEChargeLineDB,
    envelope: SpotPricingEnvelopeDB,
    resolved_product_code,
    user,
) -> SpotResolutionLearningEvent:
    """
    Record a learning event when a user manually resolves a charge line
    by selecting a ProductCode.

    Determines the resolution_type based on what the system had suggested:
    - If the system had a deterministic match and the user confirmed it:
      CONFIRM_PATTERN_MATCH
    - If the system had no suggestion or the user chose a different code:
      MANUAL_PRODUCT_CODE
    """
    system_suggested = charge_line.resolved_product_code
    user_agreed = (
        system_suggested is not None
        and resolved_product_code is not None
        and system_suggested.id == resolved_product_code.id
    )

    if user_agreed and charge_line.normalization_method:
        resolution_type = SpotResolutionLearningEvent.ResolutionType.CONFIRM_PATTERN_MATCH
    else:
        resolution_type = SpotResolutionLearningEvent.ResolutionType.MANUAL_PRODUCT_CODE

    shipment_ctx = _extract_shipment_context(envelope)
    source_ctx = _extract_source_context(charge_line)

    event = SpotResolutionLearningEvent.objects.create(
        charge_line=charge_line,
        envelope=envelope,
        source_label=str(charge_line.source_label or charge_line.description or '')[:255],
        normalized_label=str(charge_line.normalized_label or '')[:255],
        bucket=str(charge_line.bucket or '')[:30],
        normalization_status_before=str(charge_line.normalization_status or '')[:20],
        normalization_method_before=str(charge_line.normalization_method or '')[:20],
        system_suggested_product_code=system_suggested,
        resolution_type=resolution_type,
        resolved_product_code=resolved_product_code,
        user_agreed_with_suggestion=user_agreed,
        resolved_by=user,
        confidence_at_resolution=None,  # Cold-start: no confidence scoring yet
        **shipment_ctx,
        **source_ctx,
    )

    logger.info(
        "Learning event recorded: %s -> %s (%s) by %s [envelope=%s]",
        event.normalized_label,
        resolved_product_code.code if resolved_product_code else 'None',
        resolution_type,
        user.username,
        str(envelope.id)[:8],
    )
    return event


def record_conditional_resolution_event(
    charge_line: SPEChargeLineDB,
    envelope: SpotPricingEnvelopeDB,
    action: str,
    user,
) -> SpotResolutionLearningEvent:
    """
    Record a learning event when a user resolves a conditional charge line
    by choosing KEEP or REMOVE.
    """
    action_upper = str(action).strip().upper()
    if action_upper == 'KEEP':
        resolution_type = SpotResolutionLearningEvent.ResolutionType.CONDITIONAL_KEEP
    elif action_upper == 'REMOVE':
        resolution_type = SpotResolutionLearningEvent.ResolutionType.CONDITIONAL_REMOVE
    else:
        logger.warning(
            "Unknown conditional action '%s' for charge line %s",
            action, charge_line.id,
        )
        return None

    shipment_ctx = _extract_shipment_context(envelope)
    source_ctx = _extract_source_context(charge_line)

    # For conditional resolutions, the "resolved product code" is the
    # effective product code the line resolves to (only meaningful for KEEP).
    resolved_pc = charge_line.effective_resolved_product_code if action_upper == 'KEEP' else None

    event = SpotResolutionLearningEvent.objects.create(
        charge_line=charge_line,
        envelope=envelope,
        source_label=str(charge_line.source_label or charge_line.description or '')[:255],
        normalized_label=str(charge_line.normalized_label or '')[:255],
        bucket=str(charge_line.bucket or '')[:30],
        normalization_status_before=str(charge_line.normalization_status or '')[:20],
        normalization_method_before=str(charge_line.normalization_method or '')[:20],
        system_suggested_product_code=charge_line.resolved_product_code,
        resolution_type=resolution_type,
        resolved_product_code=resolved_pc,
        user_agreed_with_suggestion=False,  # Conditional is a binary keep/remove, not a suggestion agreement
        resolved_by=user,
        confidence_at_resolution=None,  # Cold-start
        **shipment_ctx,
        **source_ctx,
    )

    logger.info(
        "Conditional learning event recorded: %s -> %s (%s) by %s [envelope=%s]",
        event.normalized_label,
        action_upper,
        resolution_type,
        user.username,
        str(envelope.id)[:8],
    )
    return event
