import { API_BASE_URL, getJson } from "./shared";

export interface SpotValidationFilters {
  start_date?: string;
  end_date?: string;
  limit?: number;
  min_snapshots?: number;
}

export interface SpotSnapshotMetricsSummary {
  total_snapshots: number;
  unique_envelopes_count: number;
  validation_status_breakdown: {
    passed: number;
    warnings: number;
    review: number;
  };
}

export interface FindingCodeComparisonItem {
  finding_code: string;
  envelopes_with_snapshot_count: number;
  envelopes_reviewed_count: number;
  review_rate_percentage: number;
}

export interface CanonicalTypeComparisonItem {
  canonical_type: string;
  envelopes_with_snapshot_count: number;
  envelopes_reviewed_count: number;
  review_rate_percentage: number;
}

export interface SpotComparisonMetricsData {
  summary: {
    total_envelopes_with_snapshots: number;
    total_envelopes_with_reviews: number;
    global_review_rate_percentage: number;
  };
  finding_code_comparison: FindingCodeComparisonItem[];
  canonical_type_comparison: CanonicalTypeComparisonItem[];
}

export interface SpotMaintenanceInsightItem {
  template_id: number;
  template_name: string;
  snapshot_count: number;
  warnings_count: number;
  review_count: number;
  issue_ratio_percentage: number;
  unreviewed_ratio_percentage: number;
  review_rate_percentage: number;
  average_findings_per_snapshot: number;
  maintenance_priority_score: number;
  high_maintenance_pressure: boolean;
  sample_warning: boolean;
  finding_codes_breakdown: Array<{ code: string; count: number }>;
  canonical_types_breakdown: Array<{ type: string; count: number }>;
}

export interface SpotMaintenanceInsightsData {
  insights: SpotMaintenanceInsightItem[];
}

function buildSpotQueryParams(filters: SpotValidationFilters): string {
  const params = new URLSearchParams();
  if (filters.start_date) params.append("start_date", filters.start_date);
  if (filters.end_date) params.append("end_date", filters.end_date);
  if (filters.limit !== undefined) params.append("limit", String(filters.limit));
  if (filters.min_snapshots !== undefined) params.append("min_snapshots", String(filters.min_snapshots));
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function getSpotSnapshotMetrics(filters: SpotValidationFilters = {}): Promise<SpotSnapshotMetricsSummary> {
  const query = buildSpotQueryParams(filters);
  const url = `${API_BASE_URL}/api/v3/spot/template-validation/snapshot-metrics/${query}`;
  return getJson<SpotSnapshotMetricsSummary>(url);
}

export async function getSpotComparisonMetrics(filters: SpotValidationFilters = {}): Promise<SpotComparisonMetricsData> {
  const query = buildSpotQueryParams(filters);
  const url = `${API_BASE_URL}/api/v3/spot/template-validation/comparison-metrics/${query}`;
  return getJson<SpotComparisonMetricsData>(url);
}

export async function getSpotMaintenanceInsights(filters: SpotValidationFilters = {}): Promise<SpotMaintenanceInsightsData> {
  const query = buildSpotQueryParams(filters);
  const url = `${API_BASE_URL}/api/v3/spot/template-validation/maintenance-insights/${query}`;
  return getJson<SpotMaintenanceInsightsData>(url);
}
