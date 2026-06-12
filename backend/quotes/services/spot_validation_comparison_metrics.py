import logging
from quotes.spot_models import SpotTemplateValidationSnapshot, SpotTemplateValidationEvent

logger = logging.getLogger(__name__)

class SpotTemplateValidationComparisonMetricsService:
    @classmethod
    def get_comparison_metrics(cls, user, start_date, end_date, filters=None, limit=10):
        """
        Calculates comparison metrics between validation snapshots and reviewed findings.
        Aggregates at the distinct envelope level to prevent updates/lifecycles from skewing metrics.
        """
        if filters is None:
            filters = {}

        from quotes.selectors import get_spes_for_user
        visible_envelopes = get_spes_for_user(user)

        # 1. Query snapshots matching date range and filters
        snapshots_qs = SpotTemplateValidationSnapshot.objects.filter(
            created_at__gte=start_date,
            created_at__lte=end_date,
            envelope__in=visible_envelopes
        ).defer("findings_json")

        template_id = filters.get("template_id")
        if template_id is not None:
            snapshots_qs = snapshots_qs.filter(template_id=template_id)

        # Python-level filters for json fields to support SQLite
        snapshots = list(snapshots_qs)

        finding_code = filters.get("finding_code")
        if finding_code:
            snapshots = [s for s in snapshots if finding_code in (s.finding_codes or [])]

        canonical_type = filters.get("canonical_type")
        if canonical_type:
            snapshots = [s for s in snapshots if canonical_type in (s.canonical_types or [])]

        # Unique envelopes that generated validation snapshots
        snapshot_envelope_ids = {s.envelope_id for s in snapshots}
        total_envelopes_with_snapshots = len(snapshot_envelope_ids)

        # 2. Query matching reviewed events (type = 'finding_reviewed')
        events_qs = SpotTemplateValidationEvent.objects.filter(
            event_type="finding_reviewed",
            created_at__gte=start_date,
            created_at__lte=end_date,
            envelope_id__in=snapshot_envelope_ids
        )

        if finding_code:
            events_qs = events_qs.filter(finding_code=finding_code)

        if canonical_type:
            events_qs = events_qs.filter(canonical_type=canonical_type)

        events = list(events_qs)

        # Unique envelopes with review actions
        reviewed_envelope_ids = {e.envelope_id for e in events}
        total_envelopes_with_reviews = len(reviewed_envelope_ids)

        global_review_rate_percentage = 0.0
        if total_envelopes_with_snapshots > 0:
            global_review_rate_percentage = round(
                (total_envelopes_with_reviews / total_envelopes_with_snapshots) * 100, 2
            )

        # 3. Finding Code Comparison
        generated_envs_by_code = {}
        for s in snapshots:
            f_codes = s.finding_codes or []
            for code in f_codes:
                generated_envs_by_code.setdefault(code, set()).add(s.envelope_id)

        reviewed_envs_by_code = {}
        for e in events:
            reviewed_envs_by_code.setdefault(e.finding_code, set()).add(e.envelope_id)

        finding_code_comp_list = []
        for code, gen_envs in generated_envs_by_code.items():
            gen_count = len(gen_envs)
            rev_envs = reviewed_envs_by_code.get(code, set())
            matched_rev_envs = rev_envs.intersection(gen_envs)
            rev_count = len(matched_rev_envs)
            rate = round((rev_count / gen_count) * 100, 2) if gen_count > 0 else 0.0
            finding_code_comp_list.append({
                "finding_code": code,
                "envelopes_generated_count": gen_count,
                "envelopes_reviewed_count": rev_count,
                "review_rate_percentage": rate
            })

        # Sort: envelopes_generated_count desc, then envelopes_reviewed_count desc, then finding_code asc
        finding_code_comp_list.sort(
            key=lambda x: (-x["envelopes_generated_count"], -x["envelopes_reviewed_count"], x["finding_code"])
        )
        finding_code_comparison = finding_code_comp_list[:limit]

        # 4. Canonical Type Comparison
        generated_envs_by_cct = {}
        for s in snapshots:
            c_types = s.canonical_types or []
            for c_type in c_types:
                generated_envs_by_cct.setdefault(c_type, set()).add(s.envelope_id)

        reviewed_envs_by_cct = {}
        for e in events:
            if e.canonical_type:
                reviewed_envs_by_cct.setdefault(e.canonical_type, set()).add(e.envelope_id)

        cct_comp_list = []
        for cct, gen_envs in generated_envs_by_cct.items():
            gen_count = len(gen_envs)
            rev_envs = reviewed_envs_by_cct.get(cct, set())
            matched_rev_envs = rev_envs.intersection(gen_envs)
            rev_count = len(matched_rev_envs)
            rate = round((rev_count / gen_count) * 100, 2) if gen_count > 0 else 0.0
            cct_comp_list.append({
                "canonical_type": cct,
                "envelopes_generated_count": gen_count,
                "envelopes_reviewed_count": rev_count,
                "review_rate_percentage": rate
            })

        cct_comp_list.sort(
            key=lambda x: (-x["envelopes_generated_count"], -x["envelopes_reviewed_count"], x["canonical_type"])
        )
        canonical_type_comparison = cct_comp_list[:limit]

        # Form period & applied filters info
        period = {
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }

        filters_applied = {k: v for k, v in filters.items() if v is not None}

        return {
            "period": period,
            "filters_applied": filters_applied,
            "summary": {
                "total_envelopes_with_snapshots": total_envelopes_with_snapshots,
                "total_envelopes_with_reviews": total_envelopes_with_reviews,
                "global_review_rate_percentage": global_review_rate_percentage
            },
            "finding_code_comparison": finding_code_comparison,
            "canonical_type_comparison": canonical_type_comparison
        }
