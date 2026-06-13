"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import {
  getSpotSnapshotMetrics,
  getSpotComparisonMetrics,
  getSpotMaintenanceInsights,
  SpotSnapshotMetricsSummary,
  SpotComparisonMetricsData,
  SpotMaintenanceInsightsData
} from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Loader2,
  ArrowLeft,
  RefreshCw,
  AlertTriangle,
  AlertCircle,
  CheckCircle,
  BarChart3,
  AlertOctagon,
  FileCheck
} from "lucide-react";

export default function SpotValidationDashboardPage() {
  const { user } = useAuth();
  const { isManager, isAdmin } = usePermissions();
  const router = useRouter();

  // Filters
  const [timeframe, setTimeframe] = useState<"7" | "30" | "90">("30");
  const [limit, setLimit] = useState<number>(10);
  const [minSnapshots, setMinSnapshots] = useState<number>(5);

  // Data
  const [snapshotMetrics, setSnapshotMetrics] = useState<SpotSnapshotMetricsSummary | null>(null);
  const [comparisonMetrics, setComparisonMetrics] = useState<SpotComparisonMetricsData | null>(null);
  const [maintenanceInsights, setMaintenanceInsights] = useState<SpotMaintenanceInsightsData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const hasAccess = isManager || isAdmin;

  // Derive date range from timeframe
  const queryFilters = useMemo(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(end.getDate() - parseInt(timeframe));
    return {
      start_date: start.toISOString().split("T")[0],
      end_date: end.toISOString().split("T")[0],
      limit,
      min_snapshots: minSnapshots
    };
  }, [timeframe, limit, minSnapshots]);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      const [snapshots, comparisons, insights] = await Promise.all([
        getSpotSnapshotMetrics(queryFilters),
        getSpotComparisonMetrics(queryFilters),
        getSpotMaintenanceInsights(queryFilters)
      ]);
      setSnapshotMetrics(snapshots);
      setComparisonMetrics(comparisons);
      setMaintenanceInsights(insights);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to load validation metrics.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!user || !hasAccess) return;
    fetchData();
  }, [user, hasAccess, queryFilters]);

  // Auth block
  if (!user) return null;

  if (!hasAccess) {
    return (
      <div className="container mx-auto p-8 max-w-xl text-center space-y-6">
        <div className="flex flex-col items-center justify-center space-y-4">
          <AlertOctagon className="h-16 w-16 text-destructive animate-bounce" />
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Access Denied</h2>
          <p className="text-muted-foreground text-sm">
            Only managers and admins can view SPOT template validation metrics.
          </p>
        </div>
        <Button onClick={() => router.push("/dashboard")} className="mt-4 shadow-sm hover:scale-[1.02] active:scale-[0.98] transition">
          Back to Dashboard
        </Button>
      </div>
    );
  }

  // Service Unavailable (503) state
  const isServiceDisabled = error === "SPOT validation metrics are temporarily disabled.";

  if (isServiceDisabled) {
    return (
      <div className="container mx-auto p-8 max-w-lg text-center space-y-6">
        <div className="flex flex-col items-center justify-center p-8 bg-card border rounded-2xl shadow-xl space-y-4">
          <AlertTriangle className="h-16 w-16 text-amber-500 animate-pulse" />
          <h2 className="text-2xl font-bold tracking-tight text-foreground">Metrics Temporarily Offline</h2>
          <p className="text-muted-foreground text-sm">
            SPOT validation metrics are temporarily disabled.
          </p>
          <Button variant="outline" size="sm" onClick={fetchData} className="mt-4 gap-2">
            <RefreshCw className="h-4 w-4" /> Try Reconnecting
          </Button>
        </div>
        <Button variant="ghost" onClick={() => router.push("/dashboard")}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  // General error layout
  if (error) {
    return (
      <div className="container mx-auto p-8 max-w-2xl space-y-6">
        <Alert variant="destructive" className="border-destructive/30 bg-destructive/10">
          <AlertCircle className="h-4 w-4" />
          <AlertTitle>Error Loading Dashboard</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
        <div className="flex items-center gap-4">
          <Button variant="outline" onClick={fetchData} className="gap-2">
            <RefreshCw className="h-4 w-4" /> Retry
          </Button>
          <Button variant="ghost" onClick={() => router.push("/dashboard")}>
            Back to Dashboard
          </Button>
        </div>
      </div>
    );
  }

  // Summary Metrics calculations
  const totalSnapshots = snapshotMetrics?.total_snapshots ?? 0;
  
  const statusBreakdown = snapshotMetrics?.validation_status_breakdown || { passed: 0, warnings: 0, review: 0 };
  const issuesCount = statusBreakdown.warnings + statusBreakdown.review;
  const issuesPercentage = totalSnapshots > 0 ? Math.round((issuesCount / totalSnapshots) * 100) : 0;
  
  const globalReviewRate = comparisonMetrics?.summary?.global_review_rate_percentage ?? 0;
  
  const templatesRequiringAttention = maintenanceInsights?.insights?.filter(i => i.high_maintenance_pressure).length ?? 0;

  return (
    <div className="container mx-auto p-4 max-w-7xl space-y-6">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold tracking-tight bg-gradient-to-r from-violet-600 to-indigo-600 bg-clip-text text-transparent">
            SPOT Validation Intelligence
          </h1>
          <p className="text-muted-foreground text-sm">
            Template health audits, validation quality review ratios, and snapshot insights.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={fetchData} disabled={loading} className="gap-2">
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Reload
          </Button>
          <Button variant="ghost" size="sm" onClick={() => router.push("/dashboard")} className="gap-2">
            <ArrowLeft className="h-4 w-4" />
            Back
          </Button>
        </div>
      </div>

      {/* Filters Card */}
      <div className="p-4 bg-card/60 backdrop-blur-md rounded-xl border shadow-sm flex flex-wrap items-center gap-6">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground">Date Horizon:</span>
          <Select value={timeframe} onValueChange={(v) => setTimeframe(v as "7" | "30" | "90")}>
            <SelectTrigger className="w-[140px] bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 Days</SelectItem>
              <SelectItem value="30">Last 30 Days</SelectItem>
              <SelectItem value="90">Last 90 Days</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground">Min Snapshots:</span>
          <Select value={String(minSnapshots)} onValueChange={(v) => setMinSnapshots(parseInt(v))}>
            <SelectTrigger className="w-[120px] bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="1">1 snapshot</SelectItem>
              <SelectItem value="3">3 snapshots</SelectItem>
              <SelectItem value="5">5 snapshots</SelectItem>
              <SelectItem value="10">10 snapshots</SelectItem>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-muted-foreground">View Limit:</span>
          <Select value={String(limit)} onValueChange={(v) => setLimit(parseInt(v))}>
            <SelectTrigger className="w-[120px] bg-background">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="10">Top 10</SelectItem>
              <SelectItem value="20">Top 20</SelectItem>
              <SelectItem value="50">Top 50</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 animate-pulse">
          {[1, 2, 3, 4].map(i => (
            <Card key={i} className="bg-card">
              <CardHeader className="h-24 bg-muted/30 rounded-t-xl" />
              <CardContent className="h-16 bg-muted/10 rounded-b-xl" />
            </Card>
          ))}
        </div>
      ) : (
        <>
          {/* Summary Stat Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <Card className="shadow-sm border border-border/80">
              <CardHeader className="pb-2">
                <CardDescription className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">
                  Total Captured Snapshots
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-extrabold text-indigo-600">{totalSnapshots}</div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Generated across active user-facing transactions.
                </p>
              </CardContent>
            </Card>

            <Card className="shadow-sm border border-border/80">
              <CardHeader className="pb-2">
                <CardDescription className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">
                  Failure/Warning Rate
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-extrabold text-rose-500">{issuesPercentage}%</div>
                <div className="w-full bg-muted h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="bg-rose-500 h-1.5 rounded-full transition-all duration-500"
                    style={{ width: `${issuesPercentage}%` }}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">
                  Snapshots requiring review or raising warnings.
                </p>
              </CardContent>
            </Card>

            <Card className="shadow-sm border border-border/80">
              <CardHeader className="pb-2">
                <CardDescription className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">
                  Global Review Rate
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-extrabold text-emerald-500">{Math.round(globalReviewRate)}%</div>
                <div className="w-full bg-muted h-1.5 rounded-full mt-2 overflow-hidden">
                  <div
                    className="bg-emerald-500 h-1.5 rounded-full transition-all duration-500"
                    style={{ width: `${globalReviewRate}%` }}
                  />
                </div>
                <p className="text-[11px] text-muted-foreground mt-2">
                  Ratio of generated discrepancies resolved.
                </p>
              </CardContent>
            </Card>

            <Card className="shadow-sm border border-border/80">
              <CardHeader className="pb-2">
                <CardDescription className="font-semibold text-xs uppercase tracking-wider text-muted-foreground">
                  Hotspot Templates
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="text-3xl font-extrabold text-amber-500">{templatesRequiringAttention}</div>
                <p className="text-[11px] text-muted-foreground mt-1">
                  Expected charge templates displaying high maintenance pressure.
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Maintenance Insights Grid */}
          <Card className="shadow-sm">
            <CardHeader className="border-b bg-muted/10">
              <CardTitle className="text-lg font-bold flex items-center gap-2">
                <AlertTriangle className="h-5 w-5 text-amber-500" />
                Template Maintenance Insights
              </CardTitle>
              <CardDescription>
                Identifies which Expected Charge Templates repeatedly trigger validation failures, warnings, or review prompts.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader className="bg-muted/30">
                    <TableRow>
                      <TableHead className="font-semibold">Template</TableHead>
                      <TableHead className="font-semibold text-center">Snapshots</TableHead>
                      <TableHead className="font-semibold text-center">Issue Ratio</TableHead>
                      <TableHead className="font-semibold text-center">Avg Findings</TableHead>
                      <TableHead className="font-semibold text-center">Review Rate</TableHead>
                      <TableHead className="font-semibold text-center">Priority Score</TableHead>
                      <TableHead className="font-semibold text-right pr-4">Health</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {maintenanceInsights?.insights && maintenanceInsights.insights.length > 0 ? (
                      maintenanceInsights.insights.map((item) => (
                        <TableRow key={item.template_id} className="hover:bg-muted/10 transition-colors">
                          <TableCell className="font-medium">
                            <div>
                              <span className="text-sm font-semibold">{item.template_name}</span>
                              <div className="text-[10px] text-muted-foreground">ID: {item.template_id}</div>
                            </div>
                          </TableCell>
                          <TableCell className="text-center font-medium">{item.snapshot_count}</TableCell>
                          <TableCell className="text-center">
                            <span className={`font-semibold ${item.issue_ratio_percentage > 50 ? "text-rose-500" : "text-amber-500"}`}>
                              {Math.round(item.issue_ratio_percentage)}%
                            </span>
                          </TableCell>
                          <TableCell className="text-center font-medium">
                            {item.average_findings_per_snapshot.toFixed(1)}
                          </TableCell>
                          <TableCell className="text-center">
                            <span className="font-semibold text-emerald-600">
                              {Math.round(item.review_rate_percentage)}%
                            </span>
                          </TableCell>
                          <TableCell className="text-center">
                            <div className="inline-flex items-center justify-center px-2 py-1 bg-indigo-50 border border-indigo-100 rounded text-indigo-700 font-extrabold text-xs">
                              {Math.round(item.maintenance_priority_score)}
                            </div>
                          </TableCell>
                          <TableCell className="text-right pr-4">
                            {item.high_maintenance_pressure ? (
                              <Badge variant="destructive" className="bg-rose-500 animate-pulse">
                                High Pressure
                              </Badge>
                            ) : (
                              <Badge variant="secondary" className="bg-emerald-50 text-emerald-700 border-emerald-200">
                                Stable
                              </Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))
                    ) : (
                      <TableRow>
                        <TableCell colSpan={7} className="text-center p-8 text-muted-foreground">
                          No template insights matches the selected filters.
                        </TableCell>
                      </TableRow>
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          {/* Comparison breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Finding Code Comparison */}
            <Card className="shadow-sm">
              <CardHeader className="border-b bg-muted/10">
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <BarChart3 className="h-4 w-4 text-violet-500" />
                  Discrepancy Breakdown by Code
                </CardTitle>
                <CardDescription>
                  Ratios of manual reviews to captured discrepancies grouping by finding type.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader className="bg-muted/30">
                      <TableRow>
                        <TableHead className="font-semibold text-xs">Finding Code</TableHead>
                        <TableHead className="font-semibold text-xs text-center">Envelopes Affected</TableHead>
                        <TableHead className="font-semibold text-xs text-center">Envelopes Reviewed</TableHead>
                        <TableHead className="font-semibold text-xs text-right pr-4">Review Rate</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparisonMetrics?.finding_code_comparison && comparisonMetrics.finding_code_comparison.length > 0 ? (
                        comparisonMetrics.finding_code_comparison.map((item) => (
                          <TableRow key={item.finding_code} className="hover:bg-muted/10 transition-colors">
                            <TableCell className="font-medium text-xs">
                              <code className="px-1.5 py-0.5 bg-muted rounded font-mono text-foreground">
                                {item.finding_code}
                              </code>
                            </TableCell>
                            <TableCell className="text-center font-medium text-xs">
                              {item.envelopes_with_snapshot_count}
                            </TableCell>
                            <TableCell className="text-center font-medium text-xs">
                              {item.envelopes_reviewed_count}
                            </TableCell>
                            <TableCell className="text-right pr-4 text-xs font-bold text-emerald-600">
                              {Math.round(item.review_rate_percentage)}%
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center p-6 text-muted-foreground text-xs">
                            No finding codes recorded.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>

            {/* Canonical Type Comparison */}
            <Card className="shadow-sm">
              <CardHeader className="border-b bg-muted/10">
                <CardTitle className="text-sm font-bold flex items-center gap-2">
                  <FileCheck className="h-4 w-4 text-indigo-500" />
                  Discrepancy Breakdown by Canonical Type
                </CardTitle>
                <CardDescription>
                  Ratios of manual reviews to captured discrepancies grouping by business charges category.
                </CardDescription>
              </CardHeader>
              <CardContent className="p-0">
                <div className="overflow-x-auto">
                  <Table>
                    <TableHeader className="bg-muted/30">
                      <TableRow>
                        <TableHead className="font-semibold text-xs">Canonical Category</TableHead>
                        <TableHead className="font-semibold text-xs text-center">Envelopes Affected</TableHead>
                        <TableHead className="font-semibold text-xs text-center">Envelopes Reviewed</TableHead>
                        <TableHead className="font-semibold text-xs text-right pr-4">Review Rate</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {comparisonMetrics?.canonical_type_comparison && comparisonMetrics.canonical_type_comparison.length > 0 ? (
                        comparisonMetrics.canonical_type_comparison.map((item) => (
                          <TableRow key={item.canonical_type} className="hover:bg-muted/10 transition-colors">
                            <TableCell className="font-medium text-xs">
                              <span className="font-medium text-foreground">{item.canonical_type}</span>
                            </TableCell>
                            <TableCell className="text-center font-medium text-xs">
                              {item.envelopes_with_snapshot_count}
                            </TableCell>
                            <TableCell className="text-center font-medium text-xs">
                              {item.envelopes_reviewed_count}
                            </TableCell>
                            <TableCell className="text-right pr-4 text-xs font-bold text-emerald-600">
                              {Math.round(item.review_rate_percentage)}%
                            </TableCell>
                          </TableRow>
                        ))
                      ) : (
                        <TableRow>
                          <TableCell colSpan={4} className="text-center p-6 text-muted-foreground text-xs">
                            No canonical types recorded.
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </div>
              </CardContent>
            </Card>
          </div>
        </>
      )}
    </div>
  );
}
