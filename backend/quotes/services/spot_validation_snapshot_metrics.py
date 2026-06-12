import logging
from django.db.models import Count
from quotes.spot_models import SpotTemplateValidationSnapshot

logger = logging.getLogger(__name__)

class SpotTemplateValidationSnapshotMetricsService:
    @classmethod
    def get_snapshot_metrics(cls, user, start_date, end_date, filters=None, limit=10):
        """
        Aggregates operational validation metrics strictly from SpotTemplateValidationSnapshot records.
        """
        if filters is None:
            filters = {}

        from quotes.selectors import get_spes_for_user
        visible_envelopes = get_spes_for_user(user)

        # Base query with date range
        queryset = SpotTemplateValidationSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            envelope__in=visible_envelopes
        )

        # Apply database filters
        trigger = filters.get("trigger")
        if trigger:
            queryset = queryset.filter(trigger=trigger)

        validation_status = filters.get("validation_status")
        if validation_status:
            queryset = queryset.filter(validation_status=validation_status)

        template_id = filters.get("template_id")
        if template_id is not None:
            queryset = queryset.filter(template_id=template_id)

        # Load snapshots into memory to perform Python-level json-filtering and aggregates.
        # This bypasses SQLite contains-lookup support limitations.
        snapshots = list(queryset)

        finding_code = filters.get("finding_code")
        if finding_code:
            snapshots = [s for s in snapshots if finding_code in (s.finding_codes or [])]

        canonical_type = filters.get("canonical_type")
        if canonical_type:
            snapshots = [s for s in snapshots if canonical_type in (s.canonical_types or [])]

        # 1. total_snapshots
        total_snapshots = len(snapshots)

        # 2. unique_envelopes_count
        unique_envelopes_count = len({s.envelope_id for s in snapshots})

        # 3. by_validation_status breakdown
        by_validation_status = {"passed": 0, "warnings": 0, "review": 0}
        for s in snapshots:
            status_val = s.validation_status
            by_validation_status[status_val] = by_validation_status.get(status_val, 0) + 1

        # 4. by_trigger breakdown
        by_trigger = {"envelope_created": 0, "envelope_updated": 0, "sales_acknowledged": 0}
        for s in snapshots:
            trigger_val = s.trigger
            by_trigger[trigger_val] = by_trigger.get(trigger_val, 0) + 1

        # 5. snapshots_without_template
        snapshots_without_template = sum(1 for s in snapshots if s.template_id is None)

        # 6. review_or_warning_snapshot_count & percentage
        review_or_warning_snapshot_count = sum(
            1 for s in snapshots if s.validation_status in ["warnings", "review"]
        )
        
        review_or_warning_percentage = 0.0
        if total_snapshots > 0:
            review_or_warning_percentage = round(
                (review_or_warning_snapshot_count / total_snapshots) * 100, 2
            )

        # 7. Count finding code and canonical type frequencies
        finding_code_counts = {}
        canonical_type_counts = {}
        for s in snapshots:
            f_codes = s.finding_codes or []
            for f_code in f_codes:
                finding_code_counts[f_code] = finding_code_counts.get(f_code, 0) + 1
            c_types = s.canonical_types or []
            for c_type in c_types:
                canonical_type_counts[c_type] = canonical_type_counts.get(c_type, 0) + 1

        top_finding_codes = [
            {"code": code, "snapshot_count": count}
            for code, count in sorted(finding_code_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        ]

        top_canonical_types = [
            {"canonical_type": c_type, "snapshot_count": count}
            for c_type, count in sorted(canonical_type_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
        ]

        # 8. templates_requiring_attention
        template_stats = {}
        for s in snapshots:
            tid = s.template_id
            thash = s.template_hash or ""
            if tid is None:
                continue
            key = (tid, thash)
            if key not in template_stats:
                template_stats[key] = {"total": 0, "issues": 0}
            template_stats[key]["total"] += 1
            if s.validation_status in ["warnings", "review"]:
                template_stats[key]["issues"] += 1

        templates_req_attention = []
        for (tid, thash), stats in template_stats.items():
            total = stats["total"]
            issues = stats["issues"]
            pct = round((issues / total) * 100, 2) if total > 0 else 0.0
            templates_req_attention.append({
                "template_id": tid,
                "template_hash": thash,
                "total_snapshots": total,
                "review_or_warning_percentage": pct
            })
        
        # Sort by review_or_warning_percentage desc, then total_snapshots desc, then template_id asc
        templates_req_attention.sort(
            key=lambda x: (-x["review_or_warning_percentage"], -x["total_snapshots"], x["template_id"])
        )
        templates_requiring_attention = templates_req_attention[:limit]

        # 9. stability_metrics
        envelope_hashes = {}
        for s in snapshots:
            env_id = s.envelope_id
            envelope_hashes.setdefault(env_id, set()).add(s.findings_hash)

        total_envelopes = len(envelope_hashes)
        stable_envelopes_count = 0
        unstable_envelopes_count = 0
        for env_id, hashes in envelope_hashes.items():
            if len(hashes) <= 1:
                stable_envelopes_count += 1
            else:
                unstable_envelopes_count += 1

        stability_metrics = {
            "total_envelopes": total_envelopes,
            "stable_envelopes_count": stable_envelopes_count,
            "unstable_envelopes_count": unstable_envelopes_count
        }

        # Format period & applied filters info
        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }

        filters_applied = {k: v for k, v in filters.items() if v is not None}

        return {
            "period": period,
            "filters_applied": filters_applied,
            "total_snapshots": total_snapshots,
            "unique_envelopes_count": unique_envelopes_count,
            "by_validation_status": by_validation_status,
            "by_trigger": by_trigger,
            "snapshots_without_template": snapshots_without_template,
            "review_or_warning_snapshot_count": review_or_warning_snapshot_count,
            "review_or_warning_percentage": review_or_warning_percentage,
            "top_finding_codes": top_finding_codes,
            "top_canonical_types": top_canonical_types,
            "templates_requiring_attention": templates_requiring_attention,
            "stability_metrics": stability_metrics
        }
