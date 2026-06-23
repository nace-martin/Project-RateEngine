import json
import re
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand
from django.db.models import Q

from pricing_v4.models import (
    CanonicalChargeType,
    ChargeAlias,
    ProductCode,
    ProductCodeCreationRequest,
)
from quotes.spot_models import SPEChargeLineDB


READY = "READY_FOR_LAUNCH"
NOT_READY = "NOT_READY_FOR_LAUNCH"

CATEGORY_EXISTING_PRODUCT_CODE = "EXISTING_PRODUCTCODE_AVAILABLE"
CATEGORY_ALIAS_REQUIRED = "ALIAS_MAPPING_REQUIRED"
CATEGORY_NEW_PRODUCT_CODE = "NEW_PRODUCTCODE_REQUIRED"
CATEGORY_MANUAL_REVIEW = "AMBIGUOUS_MANUAL_REVIEW_REQUIRED"

ACTION_MAP_EXISTING = "map_to_existing_product_code"
ACTION_CREATE_ALIAS = "create_alias"
ACTION_CREATE_PRODUCT_CODE = "create_new_product_code"
ACTION_MANUAL_REVIEW = "leave_for_manual_review"

STOP_WORDS = {
    "a",
    "an",
    "and",
    "charge",
    "charges",
    "fee",
    "fees",
    "for",
    "from",
    "of",
    "per",
    "the",
    "to",
}

CANONICAL_HINTS = [
    (("fuel", "fsc"), "FUEL_SURCHARGE", ProductCode.CATEGORY_SURCHARGE),
    (("awb", "air waybill", "waybill"), "AWB_DOCUMENTATION", ProductCode.CATEGORY_DOCUMENTATION),
    (("edi",), "EDI_DOCUMENTATION", ProductCode.CATEGORY_DOCUMENTATION),
    (("documentation", "document"), "DOCUMENTATION", ProductCode.CATEGORY_DOCUMENTATION),
    (("terminal", "cto", "cargo terminal"), "TERMINAL_HANDLING", ProductCode.CATEGORY_HANDLING),
    (("security", "screening", "x-ray", "xray"), "SECURITY_SCREENING", ProductCode.CATEGORY_SCREENING),
    (("customs", "clearance"), "CUSTOMS_CLEARANCE", ProductCode.CATEGORY_CLEARANCE),
    (("pickup", "pick up", "pick-up", "cartage"), "PICKUP_CARTAGE", ProductCode.CATEGORY_CARTAGE),
    (("license", "licence", "permit"), "REGULATORY_PERMIT", ProductCode.CATEGORY_REGULATORY),
    (("air transfer", "transfer"), "AIR_TRANSFER", ProductCode.CATEGORY_HANDLING),
    (("admin", "compliance", "handling"), "HANDLING_ADMIN", ProductCode.CATEGORY_HANDLING),
    (("airfreight", "air freight", "freight"), "AIR_FREIGHT", ProductCode.CATEGORY_FREIGHT),
]

SPECIFIC_CONTEXT_PATTERNS = [
    re.compile(r"\b[A-Z]{3}\b\s*[-–]\s*\b[A-Z]{3}\b", re.IGNORECASE),
    re.compile(r"\bvia\b", re.IGNORECASE),
    re.compile(r"\([^)]*(origin|destination|metro|[A-Z]{3})[^)]*\)", re.IGNORECASE),
]


def normalize_label(value: str | None) -> str:
    return ProductCodeCreationRequest.normalize_label(value)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", normalize_label(value))
        if token and token not in STOP_WORDS
    }


def _line_queryset():
    return (
        SPEChargeLineDB.objects
        .select_related("envelope")
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
        .order_by("normalized_label", "id")
    )


def _product_code_summary(product_code: ProductCode) -> dict:
    return {
        "id": product_code.id,
        "code": product_code.code,
        "description": product_code.description,
        "domain": product_code.domain,
        "category": product_code.category,
        "default_unit": product_code.default_unit,
    }


def _request_summary(req: ProductCodeCreationRequest) -> dict:
    return {
        "request_id": req.id,
        "status": req.status,
        "source_label": req.source_label,
        "suggested_name": req.suggested_name,
        "approved_product_code_id": req.approved_product_code_id,
    }


def _canonical_hint(label: str) -> dict | None:
    normalized = normalize_label(label)
    for aliases, canonical_code, product_category in CANONICAL_HINTS:
        if any(alias in normalized for alias in aliases):
            existing = (
                CanonicalChargeType.objects
                .filter(Q(code__iexact=canonical_code) | Q(name__icontains=canonical_code.replace("_", " ")))
                .filter(is_active=True)
                .order_by("sort_order", "code")
                .first()
            )
            return {
                "code": existing.code if existing else canonical_code,
                "name": existing.name if existing else canonical_code.replace("_", " ").title(),
                "category": existing.category if existing else product_category,
                "exists": bool(existing),
            }
    return None


def _existing_product_code_matches(label: str) -> list[dict]:
    normalized = normalize_label(label)
    tokens = _tokens(label)
    if not normalized or not tokens:
        return []

    candidates = list(
        ProductCode.objects
        .filter(Q(description__icontains=label) | Q(code__icontains=label.split()[0] if label.split() else label))
        .order_by("domain", "category", "id")[:10]
    )

    if len(candidates) < 10:
        for product_code in ProductCode.objects.order_by("domain", "category", "id"):
            if product_code in candidates:
                continue
            pc_tokens = _tokens(f"{product_code.code} {product_code.description} {product_code.category}")
            if tokens and tokens.issubset(pc_tokens):
                candidates.append(product_code)
            elif len(tokens & pc_tokens) >= max(1, min(2, len(tokens))):
                if any(token in pc_tokens for token in {"awb", "fuel", "fsc", "edi", "security", "customs", "terminal"} & tokens):
                    candidates.append(product_code)
            if len(candidates) >= 10:
                break

    return [_product_code_summary(product_code) for product_code in candidates[:10]]


def _approved_request_matches(normalized_label: str) -> list[dict]:
    return [
        _request_summary(req)
        for req in (
            ProductCodeCreationRequest.objects
            .filter(
                normalized_source_label=normalized_label,
                status=ProductCodeCreationRequest.STATUS_APPROVED,
            )
            .order_by("-approved_at", "-rejected_at", "-created_at", "-id")
        )
    ]


def _pending_request_matches(normalized_label: str) -> list[dict]:
    return [
        _request_summary(req)
        for req in (
            ProductCodeCreationRequest.objects
            .filter(
                normalized_source_label=normalized_label,
                status=ProductCodeCreationRequest.STATUS_PENDING,
            )
            .order_by("-created_at", "-id")
        )
    ]


def _active_alias_matches(normalized_label: str) -> list[dict]:
    return [
        {
            "id": alias.id,
            "alias_text": alias.alias_text,
            "match_type": alias.match_type,
            "product_code": _product_code_summary(alias.product_code),
        }
        for alias in (
            ChargeAlias.objects
            .filter(normalized_alias_text=normalized_label, is_active=True)
            .select_related("product_code")
            .order_by("priority", "id")
        )
    ]


def _has_specific_context(label: str) -> bool:
    return any(pattern.search(label or "") for pattern in SPECIFIC_CONTEXT_PATTERNS)


def _classify_label(*, label: str, occurrence_count: int, product_matches: list[dict], approved_matches: list[dict], pending_matches: list[dict], alias_matches: list[dict], canonical_hint: dict | None) -> tuple[str, str]:
    if approved_matches and approved_matches[0].get("approved_product_code_id"):
        return CATEGORY_EXISTING_PRODUCT_CODE, ACTION_MAP_EXISTING
    if alias_matches:
        return CATEGORY_EXISTING_PRODUCT_CODE, ACTION_MAP_EXISTING
    if pending_matches:
        return CATEGORY_NEW_PRODUCT_CODE, ACTION_CREATE_PRODUCT_CODE
    if product_matches and not _has_specific_context(label):
        return CATEGORY_ALIAS_REQUIRED, ACTION_CREATE_ALIAS
    if canonical_hint and canonical_hint.get("category") in {
        ProductCode.CATEGORY_FREIGHT,
        ProductCode.CATEGORY_SURCHARGE,
        ProductCode.CATEGORY_DOCUMENTATION,
        ProductCode.CATEGORY_HANDLING,
        ProductCode.CATEGORY_SCREENING,
        ProductCode.CATEGORY_CLEARANCE,
        ProductCode.CATEGORY_CARTAGE,
        ProductCode.CATEGORY_REGULATORY,
    }:
        return CATEGORY_ALIAS_REQUIRED, ACTION_CREATE_ALIAS
    if occurrence_count > 1 and not _has_specific_context(label):
        return CATEGORY_NEW_PRODUCT_CODE, ACTION_CREATE_PRODUCT_CODE
    return CATEGORY_MANUAL_REVIEW, ACTION_MANUAL_REVIEW


def build_masterdata_audit() -> dict:
    grouped: dict[str, dict] = {}
    source_labels_by_norm: dict[str, Counter] = defaultdict(Counter)
    envelope_ids_by_norm: dict[str, set[str]] = defaultdict(set)
    statuses_by_norm: dict[str, Counter] = defaultdict(Counter)

    for line in _line_queryset():
        normalized = normalize_label(line.normalized_label or line.source_label or line.description)
        if not normalized:
            normalized = normalize_label(line.description)
        if not normalized:
            continue
        grouped.setdefault(
            normalized,
            {
                "normalized_label": normalized,
                "occurrence_count": 0,
                "example_description": line.description,
            },
        )
        grouped[normalized]["occurrence_count"] += 1
        source_labels_by_norm[normalized][line.source_label or line.description or normalized] += 1
        envelope_ids_by_norm[normalized].add(str(line.envelope_id))
        statuses_by_norm[normalized][line.normalization_status] += 1

    labels = []
    category_counts = Counter()
    recommended_action_counts = Counter()
    estimated_fixes_required = 0

    for normalized, row in grouped.items():
        example_label = source_labels_by_norm[normalized].most_common(1)[0][0]
        product_matches = _existing_product_code_matches(example_label)
        approved_matches = _approved_request_matches(normalized)
        pending_matches = _pending_request_matches(normalized)
        alias_matches = _active_alias_matches(normalized)
        canonical_hint = _canonical_hint(example_label)
        category, action = _classify_label(
            label=example_label,
            occurrence_count=row["occurrence_count"],
            product_matches=product_matches,
            approved_matches=approved_matches,
            pending_matches=pending_matches,
            alias_matches=alias_matches,
            canonical_hint=canonical_hint,
        )
        category_counts[category] += 1
        recommended_action_counts[action] += 1
        if category != CATEGORY_MANUAL_REVIEW:
            estimated_fixes_required += 1
        labels.append(
            {
                **row,
                "display_label": example_label,
                "source_label_variants": [
                    {"label": label, "count": count}
                    for label, count in source_labels_by_norm[normalized].most_common()
                ],
                "envelope_count": len(envelope_ids_by_norm[normalized]),
                "normalization_status_counts": dict(statuses_by_norm[normalized]),
                "existing_product_code_matches": product_matches,
                "existing_approved_product_code_request_matches": approved_matches,
                "pending_product_code_request_matches": pending_matches,
                "active_alias_matches": alias_matches,
                "suggested_canonical_charge_type": canonical_hint,
                "remediation_category": category,
                "recommended_action": action,
            }
        )

    labels.sort(key=lambda item: (-item["occurrence_count"], item["normalized_label"]))
    readiness_status = READY if not labels else NOT_READY

    return {
        "readiness_status": readiness_status,
        "readiness_summary": {
            "unique_unresolved_labels": len(labels),
            "unresolved_charge_lines": sum(item["occurrence_count"] for item in labels),
            "estimated_fixes_required": estimated_fixes_required,
            "category_counts": dict(category_counts),
            "recommended_action_counts": dict(recommended_action_counts),
            "expected_readiness_impact": (
                "READY_FOR_LAUNCH after all recommended non-manual fixes are applied and manual-review labels are resolved."
                if labels else
                "Already READY_FOR_LAUNCH for unresolved ProductCode master-data labels."
            ),
        },
        "labels": labels,
    }


class Command(BaseCommand):
    help = "Read-only audit of unresolved SPOT ProductCode master-data labels."

    def add_arguments(self, parser):
        parser.add_argument(
            "--format",
            choices=["text", "json"],
            default="text",
            help="Output format.",
        )

    def handle(self, *args, **options):
        report = build_masterdata_audit()
        if options["format"] == "json":
            self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
            return

        summary = report["readiness_summary"]
        self.stdout.write(f"readiness_status: {report['readiness_status']}")
        self.stdout.write("readiness_summary:")
        for key in ["unique_unresolved_labels", "unresolved_charge_lines", "estimated_fixes_required"]:
            self.stdout.write(f"- {key}: {summary[key]}")
        self.stdout.write("category_counts:")
        for key, count in sorted(summary["category_counts"].items()):
            self.stdout.write(f"- {key}: {count}")
        self.stdout.write("labels:")
        for item in report["labels"]:
            self.stdout.write(
                f"- {item['normalized_label']} "
                f"count={item['occurrence_count']} "
                f"category={item['remediation_category']} "
                f"action={item['recommended_action']}"
            )
