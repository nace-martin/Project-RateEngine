import logging
from django.db.models import Count
from quotes.spot_models import SpotTemplateValidationEvent

logger = logging.getLogger(__name__)

class SpotTemplateValidationMetricsService:
    @classmethod
    def get_review_metrics(cls, start_date=None, end_date=None):
        """
        Aggregates review metrics strictly from SpotTemplateValidationEvent records
        where event_type = "finding_reviewed".
        """
        # Base queryset
        queryset = SpotTemplateValidationEvent.objects.filter(event_type="finding_reviewed")

        # Date range filtering
        if start_date:
            queryset = queryset.filter(created_at__gte=start_date)
        if end_date:
            queryset = queryset.filter(created_at__lte=end_date)

        # 1. total_reviewed_events
        total_reviewed_events = queryset.count()

        # 2. reviewed_by_finding_code
        reviewed_by_finding_code = {}
        for row in queryset.values("finding_code").annotate(count=Count("id")).order_by("-count"):
            reviewed_by_finding_code[row["finding_code"]] = row["count"]

        # 3. reviewed_by_canonical_type
        reviewed_by_canonical_type = {}
        for row in queryset.values("canonical_type").annotate(count=Count("id")).order_by("-count"):
            c_type = row["canonical_type"] or "Unknown/Unmapped"
            reviewed_by_canonical_type[c_type] = row["count"]

        # 4. reviewed_by_user
        reviewed_by_user = {}
        for row in queryset.values("user__username").annotate(count=Count("id")).order_by("-count"):
            username = row["user__username"] or "System/Unknown"
            reviewed_by_user[username] = row["count"]

        # 5. latest_events
        latest_events = []
        for event in queryset.select_related("user").order_by("-created_at")[:10]:
            comment = event.metadata.get("comment") if isinstance(event.metadata, dict) else None
            latest_events.append({
                "id": str(event.id),
                "finding_fingerprint": event.finding_fingerprint,
                "finding_code": event.finding_code,
                "canonical_type": event.canonical_type,
                "user": event.user.username if event.user else "System/Unknown",
                "comment": comment,
                "created_at": event.created_at.isoformat()
            })

        # 6. top_reviewed_fingerprints
        top_reviewed_fingerprints = []
        fingerprint_rows = (
            queryset.values(
                "finding_fingerprint",
                "finding_code",
                "canonical_type",
                "template_line_id",
                "charge_line_id"
            )
            .annotate(count=Count("id"))
            .order_by("-count")[:10]
        )
        for row in fingerprint_rows:
            top_reviewed_fingerprints.append({
                "finding_fingerprint": row["finding_fingerprint"],
                "finding_code": row["finding_code"],
                "canonical_type": row["canonical_type"],
                "template_line_id": row["template_line_id"],
                "charge_line_id": str(row["charge_line_id"]) if row["charge_line_id"] else None,
                "count": row["count"]
            })

        return {
            "total_reviewed_events": total_reviewed_events,
            "reviewed_by_finding_code": reviewed_by_finding_code,
            "reviewed_by_canonical_type": reviewed_by_canonical_type,
            "reviewed_by_user": reviewed_by_user,
            "latest_events": latest_events,
            "top_reviewed_fingerprints": top_reviewed_fingerprints
        }
