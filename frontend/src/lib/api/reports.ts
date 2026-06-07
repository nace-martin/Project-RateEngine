import { API_BASE_URL, resolveAuthToken } from "./shared";
import type { Tier1Stats } from "../types";

export type DashboardTimeframe = 'weekly' | 'monthly' | 'ytd';

export interface DashboardMetricsData {
  timeframe: DashboardTimeframe;
  start_date: string;
  end_date: string;
  activity_label: string;

  // Pipeline metrics
  pipeline_count: number;
  pipeline_value: number;

  // Finalized metrics
  finalized_count: number;
  finalized_value: number;

  // Sales efficiency metrics
  total_quotes_sent: number;
  quotes_accepted: number;
  quotes_lost: number;
  quotes_expired: number;
  win_rate_percent: number;
  avg_quote_value: number;
  lost_opportunity_value: number;

  // Chart data
  weekly_activity: Array<{ day: string; count: number }>;
}

export async function getDashboardMetrics(
  timeframe: DashboardTimeframe = 'monthly'
): Promise<DashboardMetricsData> {
  const url = API_BASE_URL + `/api/v3/reports/dashboard_metrics/?timeframe=${timeframe}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch dashboard metrics');
  return response.json();
}

// --- Commercial Reporting (Phase 1 MVP) ---

export interface ReportFilters {
  start_date?: string;
  end_date?: string;
  user_id?: string;
  mode?: 'AIR' | 'SEA' | '';
}

export interface FunnelMetricsData {
  quotes_created: number;
  quotes_sent: number;
  quotes_accepted: number;
  quotes_lost: number;
  conversion_rate: number;
  avg_time_to_quote_minutes: number | null;
  filters: ReportFilters;
}

export interface ModeBreakdown {
  mode: string;
  revenue: number;
  cost: number;
  gross_profit: number;
  margin_percent: number;
  count: number;
}

export interface RevenueMarginData {
  total_revenue: number;
  total_cost: number;
  total_gross_profit: number;
  avg_margin_percent: number;
  by_mode: ModeBreakdown[];
  filters: ReportFilters;
}

export interface UserPerformanceItem {
  user_id: number;
  username: string;
  full_name: string;
  quotes_issued: number;
  quotes_sent: number;
  quotes_won: number;
  quotes_lost: number;
  conversion_rate: number;
  total_revenue: number;
  total_gp: number;
  avg_margin: number;
}

export interface UserPerformanceData {
  users: UserPerformanceItem[];
  filters: ReportFilters;
}

function buildReportQueryParams(filters: ReportFilters): string {
  const params = new URLSearchParams();
  if (filters.start_date) params.append('start_date', filters.start_date);
  if (filters.end_date) params.append('end_date', filters.end_date);
  if (filters.user_id) params.append('user_id', filters.user_id);
  if (filters.mode) params.append('mode', filters.mode);
  return params.toString();
}

export async function getFunnelMetrics(filters: ReportFilters = {}): Promise<FunnelMetricsData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/funnel_metrics/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch funnel metrics');
  return response.json();
}

export async function getRevenueMargin(filters: ReportFilters = {}): Promise<RevenueMarginData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/revenue_margin/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch revenue margin');
  return response.json();
}

export async function getUserPerformance(filters: ReportFilters = {}): Promise<UserPerformanceData> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/user_performance/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to fetch user performance');
  return response.json();
}

export async function exportReportData(filters: ReportFilters = {}): Promise<Blob> {
  const query = buildReportQueryParams(filters);
  const url = API_BASE_URL + `/api/v3/reports/export_data/${query ? '?' + query : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });
  if (!response.ok) throw new Error('Failed to export report data');
  return response.blob();
}

export async function getTier1Stats(start_date?: string, end_date?: string): Promise<Tier1Stats> {
  const params = new URLSearchParams();
  if (start_date) params.append('start_date', start_date);
  if (end_date) params.append('end_date', end_date);

  const url = API_BASE_URL + `/api/v3/reports/tier1_customer_stats/${params.toString() ? '?' + params.toString() : ''}`;
  const response = await fetch(url, {
    headers: { Authorization: `Token ${resolveAuthToken()}` },
  });

  if (!response.ok) {
    throw new Error('Failed to fetch Tier-1 stats');
  }
  return response.json();
}
