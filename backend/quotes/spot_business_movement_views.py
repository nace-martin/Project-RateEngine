from __future__ import annotations

from django.db import transaction
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import CanEditQuotes
from quotes.services.draft_quote_review_service import is_finalized
from quotes.services.spot_journey_charge_context import (
    assign_live_spot_business_movement,
    business_movement_options,
    current_live_spot_journey,
)
from quotes.spot_models import SPEChargeLineDB, SpotPricingEnvelopeDB
from quotes.spot_views import _get_spe_or_404


class SpotBusinessMovementAPIView(APIView):
    """Read and apply trusted business-movement choices for live SPOT charges."""

    permission_classes = [IsAuthenticated, CanEditQuotes]

    def get(self, request, envelope_id):
        envelope = _get_spe_or_404(request.user, envelope_id)
        payload = []
        for line in envelope.charge_lines.select_related("journey_leg").order_by("bucket", "entered_at", "id"):
            journey = current_live_spot_journey(line)
            if journey is None:
                continue
            audit = line.product_code_resolution_audit_json or {}
            payload.append(
                {
                    "charge_line_id": str(line.id),
                    "charge_label": line.description or line.source_label or "SPOT charge",
                    "bucket": line.bucket,
                    "journey_revision": journey.revision,
                    "assigned_leg_id": str(line.journey_leg_id) if line.journey_leg_id else None,
                    "assigned_leg_key": line.journey_leg.leg_key if line.journey_leg_id else None,
                    "product_code_domain": (
                        line.journey_leg.product_code_domain if line.journey_leg_id else None
                    ),
                    "product_code_resolution_status": audit.get("status"),
                    "product_code_blockers": audit.get("blocker_codes") or [],
                    "options": business_movement_options(line),
                }
            )
        return Response({"envelope_id": str(envelope.id), "charges": payload})

    @transaction.atomic
    def post(self, request, envelope_id):
        envelope = _get_spe_or_404(
            request.user,
            envelope_id,
            queryset=SpotPricingEnvelopeDB.objects.select_for_update().all(),
        )
        if is_finalized(envelope):
            return Response(
                {
                    "error_code": "DRAFT_QUOTE_REVIEW_LOCKED",
                    "error": "Reopen the finalized Draft Quote review before changing a business movement.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        charge_line_id = request.data.get("charge_line_id")
        leg_key = str(request.data.get("leg_key") or "").strip()
        journey_revision = request.data.get("journey_revision")
        if not charge_line_id or not leg_key or journey_revision in (None, ""):
            return Response(
                {
                    "error_code": "BUSINESS_MOVEMENT_INPUT_REQUIRED",
                    "error": "charge_line_id, journey_revision and leg_key are required.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        line = (
            SPEChargeLineDB.objects.select_for_update()
            .select_related("envelope", "journey_leg", "canonical_charge_type")
            .filter(envelope=envelope, id=charge_line_id)
            .first()
        )
        if line is None:
            return Response(
                {"error_code": "CHARGE_LINE_NOT_FOUND", "error": "Charge line was not found in this envelope."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            revision = int(journey_revision)
        except (TypeError, ValueError):
            return Response(
                {"error_code": "JOURNEY_REVISION_INVALID", "error": "journey_revision must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            assign_live_spot_business_movement(
                line,
                journey_revision=revision,
                leg_key=leg_key,
            )
        except ValueError as exc:
            code = str(exc)
            http_status = status.HTTP_409_CONFLICT if code == "JOURNEY_REVISION_STALE" else status.HTTP_400_BAD_REQUEST
            return Response(
                {
                    "error_code": code,
                    "error": "The selected business movement is not valid for the current trusted journey.",
                },
                status=http_status,
            )

        line.refresh_from_db()
        audit = line.product_code_resolution_audit_json or {}
        return Response(
            {
                "status": "accepted",
                "charge_line_id": str(line.id),
                "journey_revision": revision,
                "assigned_leg_id": str(line.journey_leg_id),
                "assigned_leg_key": line.journey_leg.leg_key,
                "product_code_domain": line.journey_leg.product_code_domain,
                "product_code_resolution_status": audit.get("status"),
                "product_code_blockers": audit.get("blocker_codes") or [],
                "message": "Business movement assigned and leg-aware ProductCode resolution rerun.",
            },
            status=status.HTTP_200_OK,
        )
