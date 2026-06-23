import json

from django.core.management.base import BaseCommand

from pricing_v4.models import ProductCodeCreationRequest
from quotes.serializers import SPEChargeLineSerializer
from quotes.spot_models import SPEChargeLineDB


READY = "READY_FOR_LAUNCH"
NOT_READY = "NOT_READY_FOR_LAUNCH"


def _line_payload(line: SPEChargeLineDB) -> dict:
    return {
        "charge_line_id": str(line.id),
        "envelope_id": str(line.envelope_id),
        "quote_id": str(line.envelope.quote_id) if line.envelope.quote_id else None,
        "source_label": line.source_label,
        "normalized_label": line.normalized_label,
        "description": line.description,
        "normalization_status": line.normalization_status,
        "manual_resolution_status": line.manual_resolution_status,
        "manual_resolved_product_code_id": line.manual_resolved_product_code_id,
    }


def _request_payload(req: ProductCodeCreationRequest) -> dict:
    return {
        "request_id": req.id,
        "status": req.status,
        "source_label": req.source_label,
        "suggested_name": req.suggested_name,
        "approved_product_code_id": req.approved_product_code_id,
        "source_envelope_id": str(req.source_envelope_id) if req.source_envelope_id else None,
        "source_charge_line_id": str(req.source_charge_line_id) if req.source_charge_line_id else None,
        "source_quote_id": str(req.source_quote_id) if req.source_quote_id else None,
    }


def _suggested_product_code(line: SPEChargeLineDB) -> dict | None:
    serializer = SPEChargeLineSerializer(instance=line)
    return serializer.data.get("suggested_approved_product_code")


def build_report() -> dict:
    unresolved_lines = list(
        SPEChargeLineDB.objects
        .select_related("envelope", "manual_resolved_product_code")
        .filter(
            normalization_status__in=[
                SPEChargeLineDB.NormalizationStatus.UNMAPPED,
                SPEChargeLineDB.NormalizationStatus.AMBIGUOUS,
            ],
        )
        .exclude(
            manual_resolution_status=SPEChargeLineDB.ManualResolutionStatus.RESOLVED,
            manual_resolved_product_code__isnull=False,
        )
        .order_by("envelope_id", "bucket", "entered_at", "id")
    )

    pending_requests = list(
        ProductCodeCreationRequest.objects
        .filter(status=ProductCodeCreationRequest.STATUS_PENDING)
        .select_related("approved_product_code", "source_envelope", "source_charge_line", "source_quote")
        .order_by("-created_at", "-id")
    )
    approved_requests = list(
        ProductCodeCreationRequest.objects
        .filter(
            status=ProductCodeCreationRequest.STATUS_APPROVED,
            approved_product_code__isnull=False,
        )
        .select_related("approved_product_code", "source_envelope", "source_charge_line", "source_quote")
        .order_by("-approved_at", "-created_at", "-id")
    )
    rejected_requests = list(
        ProductCodeCreationRequest.objects
        .filter(status=ProductCodeCreationRequest.STATUS_REJECTED)
        .select_related("source_envelope", "source_charge_line", "source_quote")
        .order_by("-rejected_at", "-created_at", "-id")
    )

    approved_not_applied = []
    rejected_matching_unresolved = []
    suggested_not_resolved = []

    unresolved_by_id = {line.id: line for line in unresolved_lines}
    unresolved_by_norm = {}
    for line in unresolved_lines:
        norm = ProductCodeCreationRequest.normalize_label(line.normalized_label or line.description or "")
        if norm:
            unresolved_by_norm.setdefault(norm, []).append(line)

    for req in approved_requests:
        matching_lines = []
        if req.source_charge_line_id and req.source_charge_line_id in unresolved_by_id:
            matching_lines.append(unresolved_by_id[req.source_charge_line_id])
        matching_lines.extend(unresolved_by_norm.get(req.normalized_source_label, []))
        for line in {line.id: line for line in matching_lines}.values():
            if line.manual_resolved_product_code_id != req.approved_product_code_id:
                approved_not_applied.append(
                    {
                        **_request_payload(req),
                        **_line_payload(line),
                    }
                )

    for req in rejected_requests:
        matching_lines = []
        if req.source_charge_line_id and req.source_charge_line_id in unresolved_by_id:
            matching_lines.append(unresolved_by_id[req.source_charge_line_id])
        matching_lines.extend(unresolved_by_norm.get(req.normalized_source_label, []))
        for line in {line.id: line for line in matching_lines}.values():
            rejected_matching_unresolved.append(
                {
                    **_request_payload(req),
                    **_line_payload(line),
                }
            )

    for line in unresolved_lines:
        suggested = _suggested_product_code(line)
        if suggested:
            suggested_not_resolved.append(
                {
                    **_line_payload(line),
                    "suggested_approved_product_code": suggested,
                }
            )

    blocking_counts = {
        "pending_product_code_requests": len(pending_requests),
        "approved_requests_not_applied": len(approved_not_applied),
        "rejected_requests_matching_unresolved_lines": len(rejected_matching_unresolved),
        "unresolved_product_code_review_lines": len(unresolved_lines),
        "suggested_approved_product_code_not_resolved": len(suggested_not_resolved),
    }
    readiness_status = READY if all(count == 0 for count in blocking_counts.values()) else NOT_READY

    return {
        "readiness_status": readiness_status,
        "blocking_counts": blocking_counts,
        "pending_product_code_requests": [_request_payload(req) for req in pending_requests],
        "approved_requests_not_applied": approved_not_applied,
        "rejected_requests_matching_unresolved_lines": rejected_matching_unresolved,
        "unresolved_product_code_review_lines": [_line_payload(line) for line in unresolved_lines],
        "suggested_approved_product_code_not_resolved": suggested_not_resolved,
    }


class Command(BaseCommand):
    help = "Read-only SPOT/ProductCode close-loop readiness report."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format.",
        )

    def handle(self, *args, **options):
        report = build_report()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        self.stdout.write(f"readiness_status: {report['readiness_status']}")
        self.stdout.write("blocking_counts:")
        for key, count in report["blocking_counts"].items():
            self.stdout.write(f"- {key}: {count}")
