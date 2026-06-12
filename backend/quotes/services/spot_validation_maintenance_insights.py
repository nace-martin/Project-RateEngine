import logging
from django.db.models import Count
from quotes.spot_models import (
    SpotTemplateValidationSnapshot,
    SpotTemplateValidationEvent,
    ExpectedChargeTemplate
)

logger = logging.getLogger(__name__)

class SpotTemplateValidationMaintenanceInsightsService:
    @classmethod
    def get_maintenance_insights(cls, user, start_date, end_date, filters=None, limit=10, min_snapshots=5):
        """
        Gathers template validation snapshots, calculates Maintenance Priority Scores,
        and aggregates pressure signals / finding breakdowns.
        """
        if filters is None:
            filters = {}

        from quotes.selectors import get_spes_for_user
        visible_envelopes = get_spes_for_user(user)

        # 1. Base query for snapshots
        snapshots_qs = SpotTemplateValidationSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            envelope__in=visible_envelopes
        )

        template_id = filters.get("template_id")
        if template_id is not None:
            snapshots_qs = snapshots_qs.filter(template_id=template_id)

        # Python-level load
        snapshots = list(snapshots_qs)

        # Fetch template metadata
        template_names = {t.id: t.name for t in ExpectedChargeTemplate.objects.all()}

        # Group snapshots by template_id
        snapshots_by_template = {}
        for s in snapshots:
            tid = s.template_id
            if tid is None:
                continue
            snapshots_by_template.setdefault(tid, []).append(s)

        insights_list = []

        # Heuristic constants
        issue_ratio_weight = 0.4
        avg_findings_weight = 0.3
        unreviewed_ratio_weight = 0.3
        avg_findings_cap = 5.0

        for tid, t_snaps in snapshots_by_template.items():
            total_snapshots = len(t_snaps)

            # Apply min_snapshots threshold
            if total_snapshots < min_snapshots:
                continue

            unique_envelopes_count = len({s.envelope_id for s in t_snaps})

            # Validation status breakdown
            validation_status_breakdown = {"passed": 0, "warnings": 0, "review": 0}
            issue_snapshots_count = 0
            total_findings = 0
            for s in t_snaps:
                status_val = s.validation_status
                validation_status_breakdown[status_val] = validation_status_breakdown.get(status_val, 0) + 1
                if status_val in ["warnings", "review"]:
                    issue_snapshots_count += 1
                total_findings += s.finding_count

            # 1. Issue ratio
            issue_ratio_percentage = 0.0
            if total_snapshots > 0:
                issue_ratio_percentage = round((issue_snapshots_count / total_snapshots) * 100, 2)
            issue_ratio = issue_ratio_percentage / 100.0

            # 2. Average findings
            average_findings_per_snapshot = 0.0
            if total_snapshots > 0:
                average_findings_per_snapshot = round(total_findings / total_snapshots, 2)
            
            avg_findings_normalized = min(average_findings_per_snapshot / avg_findings_cap, 1.0)

            # 3. Review rate & Unreviewed ratio
            t_envelope_ids = {s.envelope_id for s in t_snaps}
            envelopes_with_findings_ids = {s.envelope_id for s in t_snaps if s.finding_count > 0}
            envelopes_with_findings_count = len(envelopes_with_findings_ids)

            # Query matching reviewed events
            events_qs = SpotTemplateValidationEvent.objects.filter(
                event_type="finding_reviewed",
                created_at__gte=start_date,
                created_at__lte=end_date,
                envelope_id__in=t_envelope_ids
            )
            reviewed_envelope_ids = {e.envelope_id for e in events_qs}
            envelopes_reviewed_ids = reviewed_envelope_ids.intersection(envelopes_with_findings_ids)
            envelopes_reviewed_count = len(envelopes_reviewed_ids)

            review_rate_percentage = 100.0
            if envelopes_with_findings_count > 0:
                review_rate_percentage = round(
                    (envelopes_reviewed_count / envelopes_with_findings_count) * 100, 2
                )
            
            unreviewed_ratio_percentage = round(100.0 - review_rate_percentage, 2)
            unreviewed_ratio = unreviewed_ratio_percentage / 100.0

            # Maintenance Priority Score
            maintenance_priority_score = round(
                (issue_ratio_weight * issue_ratio +
                 avg_findings_weight * avg_findings_normalized +
                 unreviewed_ratio_weight * unreviewed_ratio) * 100, 2
            )

            # Pressure flags
            issue_snaps = [s for s in t_snaps if s.validation_status in ["warnings", "review"]]
            missing_charge_snapshots_count = sum(
                1 for s in issue_snaps if "expected_charge_missing" in (s.finding_codes or [])
            )
            unexpected_charge_snapshots_count = sum(
                1 for s in issue_snaps if "unexpected_charge_present" in (s.finding_codes or [])
            )

            missing_charge_pressure = False
            unexpected_charge_pressure = False
            if len(issue_snaps) > 0:
                missing_charge_pressure = (missing_charge_snapshots_count / len(issue_snaps)) > 0.5
                unexpected_charge_pressure = (unexpected_charge_snapshots_count / len(issue_snaps)) > 0.5

            high_maintenance_pressure = (
                maintenance_priority_score > 70.0 or
                (review_rate_percentage < 15.0 and total_snapshots >= 5)
            )

            # Summaries
            finding_code_counts = {}
            canonical_type_counts = {}
            for s in t_snaps:
                for code in (s.finding_codes or []):
                    finding_code_counts[code] = finding_code_counts.get(code, 0) + 1
                for c_type in (s.canonical_types or []):
                    canonical_type_counts[c_type] = canonical_type_counts.get(c_type, 0) + 1

            finding_codes_breakdown = [
                {"code": k, "snapshot_count": v}
                for k, v in sorted(finding_code_counts.items(), key=lambda x: x[1], reverse=True)
            ]
            canonical_types_breakdown = [
                {"canonical_type": k, "snapshot_count": v}
                for k, v in sorted(canonical_type_counts.items(), key=lambda x: x[1], reverse=True)
            ]

            # Primary template hash (take the latest one in the range)
            t_snaps_sorted = sorted(t_snaps, key=lambda x: x.created_at, reverse=True)
            latest_hash = t_snaps_sorted[0].template_hash if t_snaps_sorted else ""

            insights_list.append({
                "template_id": tid,
                "template_name": template_names.get(tid, f"Template #{tid}"),
                "template_hash": latest_hash,
                "maintenance_priority_score": maintenance_priority_score,
                "total_snapshots": total_snapshots,
                "unique_envelopes_count": unique_envelopes_count,
                "validation_status_breakdown": validation_status_breakdown,
                "finding_codes_breakdown": finding_codes_breakdown,
                "canonical_types_breakdown": canonical_types_breakdown,
                "envelopes_with_findings_count": envelopes_with_findings_count,
                "envelopes_reviewed_count": envelopes_reviewed_count,
                "issue_ratio_percentage": issue_ratio_percentage,
                "unreviewed_ratio_percentage": unreviewed_ratio_percentage,
                "review_rate_percentage": review_rate_percentage,
                "average_findings_per_snapshot": average_findings_per_snapshot,
                "sample_warning": total_snapshots < 5,
                "maintenance_signals": {
                    "high_maintenance_pressure": high_maintenance_pressure,
                    "missing_charge_pressure": missing_charge_pressure,
                    "unexpected_charge_pressure": unexpected_charge_pressure
                }
            })

        # Sort descending by priority_score, then total_snapshots desc, then template_id asc
        insights_list.sort(
            key=lambda x: (-x["maintenance_priority_score"], -x["total_snapshots"], x["template_id"])
        )
        insights = insights_list[:limit]

        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }

        filters_applied = {
            "min_snapshots": min_snapshots
        }
        if template_id is not None:
            filters_applied["template_id"] = template_id

        score_basis = {
            "issue_ratio_weight": issue_ratio_weight,
            "avg_findings_weight": avg_findings_weight,
            "unreviewed_ratio_weight": unreviewed_ratio_weight,
            "avg_findings_cap": avg_findings_cap
        }

        return {
            "period": period,
            "filters_applied": filters_applied,
            "score_basis": score_basis,
            "insights": insights
        }
