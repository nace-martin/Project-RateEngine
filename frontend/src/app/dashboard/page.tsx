"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { PlusCircle, ArrowRight, FileText, CheckCircle2, DollarSign, AlertCircle, Clock, TrendingUp, BarChart3 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import ProtectedRoute from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import { getQuotesV3, listSpotEnvelopes, getDashboardMetrics, type DashboardMetricsData, type DashboardTimeframe } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import type { V3QuoteComputeResponse } from "@/lib/types";
import { SpotPricingEnvelope } from "@/lib/spot-types";
import { UnifiedQuote, formatCurrency, formatRoute, getWeight, getCustomerName, calculateSpotTotal, getEffectiveQuoteStatus } from "@/lib/quote-helpers";
import { Button } from "@/components/ui/button";
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
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";
import { KPICard } from "@/components/KPICard";
import { Tier1StatsRow } from "@/components/dashboard/Tier1StatsRow";



interface FxStatusData {
    rates: Array<{ currency: string; tt_buy: string; tt_sell: string }>;
    last_updated: string | null;
    source: string | null;
    is_stale: boolean;
    staleness_hours: number | null;
    staleness_warning: string | null;
}

export default function DashboardPage() {
    const { user } = useAuth();
    const { isFinance, canEditQuotes, isManager, isAdmin } = usePermissions();
    const [allQuotes, setAllQuotes] = useState<V3QuoteComputeResponse[]>([]);
    const [spotDrafts, setSpotDrafts] = useState<SpotPricingEnvelope[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [fxStatus, setFxStatus] = useState<FxStatusData | null>(null);

    // Timeframe and dashboard metrics state for Sales/Manager view
    const [timeframe, setTimeframe] = useState<DashboardTimeframe>('monthly');
    const [dashboardMetrics, setDashboardMetrics] = useState<DashboardMetricsData | null>(null);
    const [metricsLoading, setMetricsLoading] = useState(false);

    // ... (rest of useEffects) ...

    useEffect(() => {
        if (!user) {
            return;
        }
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                // Fetch both Standard Quotes and SPOT Dratfs
                const [quotesData, draftsData] = await Promise.all([
                    getQuotesV3(),
                    listSpotEnvelopes('draft').catch(() => []),
                ]);
                setAllQuotes(quotesData.results);
                setSpotDrafts(draftsData);
            } catch (err: unknown) {
                const message =
                    err instanceof Error ? err.message : "Unable to load data.";
                setError(message);
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, [user]);

    // Fetch FX status for Finance users
    useEffect(() => {
        if (!user || !isFinance) return;
        // ... rest of FX fetch ...
        const fetchFxStatus = async () => {
            try {
                const token = localStorage.getItem('authToken');
                const response = await fetch(`${API_BASE_URL}/api/v4/fx/status/`, {
                    headers: {
                        'Authorization': token ? `Token ${token}` : '',
                        'Content-Type': 'application/json',
                    },
                });
                if (response.ok) {
                    const data = await response.json();
                    setFxStatus(data);
                }
            } catch (err) {
                console.error('Failed to fetch FX status:', err);
            }
        };
        fetchFxStatus();
    }, [user, isFinance]);

    const shouldFetchDashboardMetrics = !isFinance && (isManager || isAdmin);

    // Fetch dashboard metrics for Manager/Admin users when timeframe changes
    useEffect(() => {
        if (!user || !shouldFetchDashboardMetrics) {
            setDashboardMetrics(null);
            setMetricsLoading(false);
            return;
        }

        const fetchMetrics = async () => {
            setMetricsLoading(true);
            try {
                const data = await getDashboardMetrics(timeframe);
                setDashboardMetrics(data);
            } catch (err) {
                console.error('Failed to fetch dashboard metrics:', err);
            } finally {
                setMetricsLoading(false);
            }
        };
        fetchMetrics();
    }, [user, shouldFetchDashboardMetrics, timeframe]);

    // Metrics calculations
    const metrics = useMemo(() => {
        const normalizedStatus = (status?: string, validUntil?: string | null) =>
            getEffectiveQuoteStatus(status ?? "", validUntil);

        const draftQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'DRAFT');
        const finalizedQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'FINALIZED');
        const sentQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'SENT');
        const acceptedQuotes = allQuotes.filter(q => {
            const status = normalizedStatus(q.status, q.valid_until);
            return status === 'ACCEPTED' || status === 'APPROVED';
        });
        const lostQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'LOST');
        const expiredQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'EXPIRED');
        const cancelledQuotes = allQuotes.filter(q => normalizedStatus(q.status, q.valid_until) === 'CANCELLED');

        const currency = allQuotes[0]?.latest_version.totals.total_sell_fcy_currency ?? "PGK";

        // Total value of finalized quotes
        const finalizedValue = finalizedQuotes.reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        // Pipeline value (all non-cancelled)
        const pipelineValue = allQuotes
            .filter(q => normalizedStatus(q.status, q.valid_until) !== 'CANCELLED')
            .reduce((sum, quote) => {
                const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
                return sum + (isNaN(amount) ? 0 : amount);
            }, 0);

        // Velocity (Growth last 7 days)
        const sevenDaysAgo = new Date();
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

        const newQuotesLast7Days = allQuotes.filter(q => new Date(q.created_at) > sevenDaysAgo);
        const newValueLast7Days = newQuotesLast7Days.reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        // Approximation of "Previous Pipeline" = Current - New
        const previousPipeline = pipelineValue - newValueLast7Days;
        const velocityPercent = previousPipeline > 0 ? ((newValueLast7Days / previousPipeline) * 100).toFixed(0) : "0";

        // Needs Attention (Expiring in 24h)
        const expiringSoon = allQuotes.filter(q => {
            if (!q.valid_until) return false;
            const status = normalizedStatus(q.status, q.valid_until);
            if (status === 'FINALIZED' || status === 'SENT') return false;
            // Logic: is valid_until within next 24h?
            const expiry = new Date(q.valid_until);
            const now = new Date();
            const diffHours = (expiry.getTime() - now.getTime()) / (1000 * 60 * 60);
            return diffHours > 0 && diffHours < 48; // Using 48h to be generous for demo
        });

        const totalSentCount = sentQuotes.length + acceptedQuotes.length + lostQuotes.length + expiredQuotes.length;
        const winRatePercent = totalSentCount > 0 ? Math.round((acceptedQuotes.length / totalSentCount) * 100) : 0;

        const avgQuoteValue = finalizedQuotes.length > 0 ? finalizedValue / finalizedQuotes.length : 0;
        const lostOpportunityValue = [...lostQuotes, ...expiredQuotes].reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        return {
            draftCount: draftQuotes.length,
            finalizedCount: finalizedQuotes.length,
            sentCount: sentQuotes.length,
            approvedCount: acceptedQuotes.length,
            cancelledCount: cancelledQuotes.length,
            totalQuotes: allQuotes.length,
            finalizedValue,
            pipelineValue,
            currency,
            velocityPercent,
            expiringSoon,
            newQuotesLast7DaysCount: newQuotesLast7Days.length,
            totalSentCount,
            acceptedCount: acceptedQuotes.length,
            lostCount: lostQuotes.length,
            expiredCount: expiredQuotes.length,
            winRatePercent,
            avgQuoteValue,
            lostOpportunityValue,
        };
    }, [allQuotes]);

    // Chart Data (Last 7 Days Activity)
    const chartData = useMemo(() => {
        const days = Array.from({ length: 7 }, (_, i) => {
            const d = new Date();
            d.setDate(d.getDate() - (6 - i)); // 6 days ago to today
            return d.toISOString().split('T')[0];
        });

        const counts = days.map(day => {
            return allQuotes.filter(q => q.created_at.startsWith(day)).length +
                spotDrafts.filter(d => d.created_at.startsWith(day)).length;
        });

        const max = Math.max(...counts, 1);

        return days.map((day, i) => ({
            day: new Date(day).toLocaleDateString('en-US', { weekday: 'short' }),
            count: counts[i],
            heightPercent: (counts[i] / max) * 100
        }));
    }, [allQuotes, spotDrafts]);

    const weeklyActivityData = dashboardMetrics?.weekly_activity ?? chartData;
    const weeklyActivityMax = Math.max(...weeklyActivityData.map(a => a.count), 1);

    // Unified Data Logic for Recent Activity
    const recentQuotes = useMemo<UnifiedQuote[]>(() => {
        const unified: UnifiedQuote[] = [];

        // 1. Standard Quotes
        allQuotes.forEach(q => {
            const totalAmt = q.latest_version?.totals?.total_sell_fcy_incl_gst;
            const currency = q.latest_version?.totals?.total_sell_fcy_currency;
            unified.push({
                id: q.id,
                type: "STANDARD",
                number: q.quote_number,
                customer: getCustomerName(q.customer),
                route: `${formatRoute(q.origin_location)} → ${formatRoute(q.destination_location)}`,
                date: q.created_at,
                updatedAt: q.updated_at,
                weight: getWeight(q),
                status: q.status,
                rawStatus: getEffectiveQuoteStatus(q.status, q.valid_until),
                total: formatCurrency(totalAmt, currency),
                actionLink: `/quotes/${q.id}`,
                mode: q.mode,
                createdBy: q.created_by || "Unknown"
            });
        });

        // 2. Add Spot Drafts
        spotDrafts.forEach(d => {
            const params = new URLSearchParams({
                customer_name: d.customer_name || "",
                service_scope: (d.shipment.service_scope || "D2D").toUpperCase(),
                payment_term: (d.shipment.payment_term || "prepaid").toUpperCase(),
            });
            unified.push({
                id: d.id,
                type: "SPOT_DRAFT",
                number: `SQ-${d.id.substring(0, 6).toUpperCase()}`,
                customer: d.customer_name || "Spot Request",
                route: `${formatRoute(d.shipment.origin_code)} → ${formatRoute(d.shipment.destination_code)}`,
                date: d.created_at,
                updatedAt: d.updated_at,
                weight: `${d.shipment.total_weight_kg} kg`,
                status: "Draft",
                rawStatus: "DRAFT",
                total: calculateSpotTotal(d),
                actionLink: `/quotes/spot/${d.id}?${params.toString()}`,
                mode: "AIR", // SPOT is implicitly AIR for now
                createdBy: "User" // SPOT drafts don't have explicit creator stored yet
            });
        });

        return unified.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).slice(0, 5);
    }, [allQuotes, spotDrafts]);


    const displayName = user?.username;

    // ========== FINANCE DASHBOARD ==========
    if (isFinance) {
        // Finance-specific metrics (PGK only)
        const now = new Date();
        const currentMonth = now.getMonth();
        const currentYear = now.getFullYear();

        // Filter finalized quotes for current month
        const finalizedThisMonth = allQuotes.filter(q => {
            if (q.status?.toLowerCase() !== 'finalized') return false;
            const createdAt = new Date(q.created_at);
            return createdAt.getMonth() === currentMonth && createdAt.getFullYear() === currentYear;
        });

        // Finalized Revenue in PGK
        const finalizedRevenuePGK = finalizedThisMonth.reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_pgk_incl_gst || quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        // Draft quotes only for pipeline
        const draftQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'draft');
        const pipelinePGK = draftQuotes.reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_pgk_incl_gst || quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        return (
            <ProtectedRoute>
                <main className="container mx-auto space-y-8 py-8 max-w-7xl">
                    {/* Finance Hero Section - Clean, No Icons */}
                    <section className="rounded-3xl bg-slate-900 px-8 py-10 shadow-xl">
                        <p className="text-sm font-semibold uppercase tracking-wider text-emerald-400 mb-2">
                            Financial Oversight
                        </p>
                        <h1 className="text-3xl font-bold text-white">
                            Welcome back, {displayName}
                        </h1>
                        <p className="mt-2 max-w-2xl text-slate-400">
                            Monitor quote value, FX exposure, and finalized revenue — all in one place.
                        </p>
                        <div className="mt-6 flex flex-wrap gap-3">
                            <Button size="default" className="bg-white text-slate-900 hover:bg-slate-100 font-semibold" asChild>
                                <Link href="/quotes">View All Quotes</Link>
                            </Button>
                            <Button variant="outline" size="default" className="border-slate-600 bg-transparent text-slate-300 hover:bg-slate-800 hover:text-white" asChild>
                                <Link href="/settings">Rate Controls</Link>
                            </Button>
                        </div>
                    </section>

                    {/* Finance KPI Widgets - Standardized */}
                    <section className="grid gap-6 md:grid-cols-3">
                        {/* Widget A: Finalized Revenue (PGK) */}
                        <KPICard
                            title="Finalized Revenue (This Month)"
                            value={loading ? <Skeleton className="h-8 w-32" /> : `PGK ${finalizedRevenuePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
                            description={`${finalizedThisMonth.length} finalized quotes`}
                            status="success"
                            icon={DollarSign}
                        />

                        {/* Widget B: Pipeline Exposure (Drafts) */}
                        <KPICard
                            title="Pipeline Exposure (Drafts)"
                            value={loading ? <Skeleton className="h-8 w-32" /> : `PGK ${pipelinePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
                            description={`${draftQuotes.length} draft quotes in market`}
                            status="info"
                            icon={BarChart3}
                        />

                        {/* Widget C: FX Rates */}
                        <KPICard
                            title="FX Rates"
                            value={fxStatus ? (fxStatus.is_stale ? "Stale" : "Current") : <Skeleton className="h-8 w-24" />}
                            status={fxStatus?.is_stale ? "warning" : "info"}
                            icon={TrendingUp}
                        >
                            <div className="mt-4">
                                {fxStatus ? (
                                    <div className="space-y-1">
                                        {fxStatus.rates
                                            .filter(r => !r.currency.startsWith('PGK'))
                                            .slice(0, 3)
                                            .map((rate) => {
                                                const base = rate.currency.split('/')[0] || rate.currency;
                                                return (
                                                    <div key={rate.currency} className="flex justify-between text-sm">
                                                        <span>{base}/PGK</span>
                                                        <span className="font-mono">{parseFloat(rate.tt_sell).toFixed(4)}</span>
                                                    </div>
                                                );
                                            })}
                                        <div className="pt-2 border-t mt-2">
                                            <p className="text-xs text-muted-foreground">
                                                Source: {fxStatus.source || 'BSP'}
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <div className="space-y-2">
                                        <Skeleton className="h-4 w-full" />
                                        <Skeleton className="h-4 w-full" />
                                    </div>
                                )}
                            </div>
                        </KPICard>
                    </section>

                    {/* Recent Quote Activity Table - New Columns */}
                    <Card className="border border-slate-200 shadow-sm bg-white scroll-mt-20">
                        <CardHeader className="border-b bg-slate-50/40 px-6 py-4">
                            <div className="flex items-center justify-between">
                                <div>
                                    <CardTitle>Recent Quote Activity</CardTitle>
                                    <CardDescription>Latest quotes for audit and review</CardDescription>
                                </div>
                                <Button variant="outline" size="sm" className="bg-white" asChild>
                                    <Link href="/quotes">View All</Link>
                                </Button>
                            </div>
                        </CardHeader>
                        <CardContent className="p-0">
                            {loading ? (
                                <div className="flex items-center justify-center py-12 text-muted-foreground">
                                    <span className="text-sm">Loading quotes...</span>
                                </div>
                            ) : error ? (
                                <div className="p-4 text-red-600">{error}</div>
                            ) : recentQuotes.length === 0 ? (
                                <EmptyState
                                    title="No quotes available"
                                    description="There are no recent quotes to display."
                                    icon={FileText}
                                    className="py-12 border-none"
                                />
                            ) : (
                                <div className="overflow-x-auto">
                                    <Table>
                                        <TableHeader>
                                            <TableRow className="bg-muted/30">
                                                <TableHead>Quote #</TableHead>
                                                <TableHead>Customer</TableHead>
                                                <TableHead>Route</TableHead>
                                                <TableHead>Mode</TableHead>
                                                <TableHead>User</TableHead>
                                                <TableHead className="text-right">Total (Inc. GST)</TableHead>
                                                <TableHead>Status</TableHead>
                                                <TableHead>Action</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {recentQuotes.map((quote) => (
                                                <TableRow key={quote.id}>
                                                    <TableCell className="font-medium">{quote.number}</TableCell>
                                                    <TableCell>{quote.customer}</TableCell>
                                                    <TableCell className="text-muted-foreground">
                                                        {quote.route}
                                                    </TableCell>
                                                    <TableCell>{quote.mode}</TableCell>
                                                    <TableCell className="text-muted-foreground text-sm">{quote.createdBy}</TableCell>
                                                    <TableCell className="text-right font-medium tabular-nums">
                                                        {quote.total}
                                                    </TableCell>
                                                    <TableCell>
                                                        <QuoteStatusBadge status={quote.rawStatus} size="sm" />
                                                    </TableCell>
                                                    <TableCell className="text-right">
                                                        <Button
                                                            variant="ghost"
                                                            size="sm"
                                                            asChild
                                                            className="h-8 text-primary hover:text-primary/80 hover:bg-primary/5"
                                                        >
                                                            <Link href={quote.actionLink}>
                                                                {["DRAFT", "draft"].includes(quote.rawStatus) ? "Resume" : "View"}
                                                            </Link>
                                                        </Button>
                                                    </TableCell>
                                                </TableRow>
                                            ))}
                                        </TableBody>
                                    </Table>
                                </div>
                            )}
                        </CardContent>
                    </Card>
                </main>
            </ProtectedRoute>
        );
    }

    // ========== SALES/MANAGER/ADMIN DASHBOARD ==========
    return (
        <ProtectedRoute>
            <main className="container mx-auto space-y-8 py-8 max-w-7xl font-sans">
                {/* MODERN HERO SECTION */}
                <section className="relative rounded-[2rem] overflow-hidden shadow-2xl">
                    {/* Gradient Background */}
                    <div className="absolute inset-0 bg-gradient-to-br from-[#0F52BA] via-[#1a65d8] to-[#0d3d8a]" />
                    {/* Abstract Shapes/Glass effect */}
                    <div className="absolute top-0 right-0 w-[500px] h-[500px] bg-white/5 rounded-full blur-3xl -mr-20 -mt-20 pointer-events-none"></div>
                    <div className="absolute bottom-0 left-0 w-[300px] h-[300px] bg-white/5 rounded-full blur-3xl -ml-10 -mb-10 pointer-events-none"></div>

                    <div className="relative z-10 px-10 py-12 text-white flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                        <div className="space-y-4 max-w-2xl">
                            <div className="inline-flex items-center rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-blue-100 backdrop-blur-md border border-white/10">
                                Quoting Control Center
                            </div>
                            <h1 className="text-4xl md:text-5xl font-bold tracking-tight text-white drop-shadow-sm">
                                Hello, {displayName}
                            </h1>
                            <p className="text-lg text-blue-100 leading-relaxed font-light">
                                You have <span className="font-semibold text-white">{metrics.draftCount} quotes in progress</span>.
                                Monitor your pipeline and keep things moving.
                            </p>

                            <div className="flex flex-wrap gap-3 pt-4">
                                {canEditQuotes && (
                                    <Button size="lg" className="bg-white text-primary hover:bg-blue-50 font-semibold h-12 px-6 rounded-xl shadow-lg shadow-blue-900/20 border-0" asChild>
                                        <Link href="/quotes/new">
                                            <PlusCircle className="mr-2 h-5 w-5" />
                                            New Quote
                                        </Link>
                                    </Button>
                                )}
                                <Button variant="outline" size="lg" className="bg-white/10 text-white border-white/20 hover:bg-white/20 h-12 px-6 rounded-xl backdrop-blur-sm" asChild>
                                    <Link href="/quotes">
                                        View All
                                        <ArrowRight className="ml-2 h-4 w-4" />
                                    </Link>
                                </Button>
                                {(isManager || isAdmin) && (
                                    <Button variant="outline" size="lg" className="bg-white/10 text-white border-white/20 hover:bg-white/20 h-12 px-6 rounded-xl backdrop-blur-sm" asChild>
                                        <Link href="/dashboard/management">
                                            <BarChart3 className="mr-2 h-4 w-4" />
                                            Performance
                                        </Link>
                                    </Button>
                                )}
                            </div>
                        </div>

                        {/* Needs Attention Widget (Glass Card) */}
                        {metrics.expiringSoon.length > 0 ? (
                            <div className="w-full md:w-[320px] bg-white/10 backdrop-blur-md border border-white/20 rounded-2xl p-5 shadow-inner">
                                <div className="flex items-start gap-3">
                                    <div className="p-2 bg-amber-500/20 rounded-lg text-amber-200">
                                        <Clock className="h-5 w-5" />
                                    </div>
                                    <div className="flex-1">
                                        <h3 className="font-semibold text-white mb-1">Needs Attention</h3>
                                        <p className="text-sm text-blue-100 mb-3">
                                            <span className="font-bold text-amber-300">{metrics.expiringSoon.length} quotes</span> expiring soon.
                                        </p>
                                        <Button size="sm" variant="secondary" className="w-full bg-white/90 text-primary hover:bg-white border-none shadow-none text-xs h-8">
                                            Send Reviews
                                        </Button>
                                    </div>
                                </div>
                            </div>
                        ) : (
                            // Fallback widget if nothing urgent
                            <div className="w-full md:w-[280px] bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl p-6 text-center">
                                <CheckCircle2 className="h-8 w-8 text-emerald-300 mx-auto mb-2 opacity-80" />
                                <p className="text-white font-medium">All caught up!</p>
                                <p className="text-sm text-blue-200">No urgent items pending.</p>
                            </div>
                        )}
                    </div>
                </section>

                {/* KPI SECTION */}
                <section className="space-y-6">
                    {/* Timeframe Toggle */}
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-slate-800">Sales Metrics</h2>
                        <div className="flex gap-2 bg-slate-100 p-1 rounded-lg">
                            {(['weekly', 'monthly', 'ytd'] as const).map((tf) => (
                                <button
                                    key={tf}
                                    onClick={() => setTimeframe(tf)}
                                    className={`px-4 py-1.5 text-sm font-medium rounded-md transition-all ${timeframe === tf
                                        ? 'bg-[#0F52BA] text-white shadow-sm'
                                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-200'
                                        }`}
                                >
                                    {tf === 'ytd' ? 'YTD' : tf.charAt(0).toUpperCase() + tf.slice(1)}
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Row 1: Core Metrics */}
                    <div className="grid gap-6 md:grid-cols-3">
                        {/* 1. Quote Activity Chart */}
                        <KPICard
                            title="Quote Activity"
                            value={metricsLoading ? <Skeleton className="h-9 w-16" /> : (dashboardMetrics?.weekly_activity.reduce((sum, d) => sum + d.count, 0) ?? metrics.newQuotesLast7DaysCount)}
                            status="info"
                            icon={FileText}
                            className="overflow-hidden"
                            action={<TrendingUp className="h-4 w-4 text-success" />}
                            description={dashboardMetrics?.activity_label ?? "Last 7 days"}
                        >
                            <div className="mt-4 flex h-28 items-end gap-2 justify-between">
                                {weeklyActivityData.map((d, i) => {
                                    const count = 'count' in d ? d.count : 0;
                                    const heightPercent = (count / weeklyActivityMax) * 100;
                                    const dayLabel = (() => {
                                        if (!('day' in d)) {
                                            return '';
                                        }
                                        const rawDay = d.day;
                                        if (typeof rawDay !== 'string') {
                                            return rawDay ? String(rawDay) : '';
                                        }
                                        const parsed = new Date(rawDay);
                                        if (!Number.isNaN(parsed.getTime())) {
                                            return parsed.toLocaleDateString('en-US', { weekday: 'short' });
                                        }
                                        return rawDay;
                                    })();
                                    return (
                                        <div key={i} className="group/bar flex h-full flex-1 flex-col items-center gap-2">
                                            <div className="flex h-full w-full items-end rounded-md bg-slate-50 px-1">
                                                <div
                                                    className="relative w-full rounded-t-md bg-blue-200 transition-colors group-hover/bar:bg-blue-500"
                                                    style={{ height: `${Math.max(heightPercent, count > 0 ? 10 : 6)}%` }}
                                                >
                                                    <div className="absolute -top-8 left-1/2 -translate-x-1/2 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] whitespace-nowrap text-white opacity-0 transition-opacity group-hover/bar:opacity-100 z-10">
                                                        {count}
                                                    </div>
                                                </div>
                                            </div>
                                            <span className="text-[10px] font-medium uppercase text-slate-400">{dayLabel}</span>
                                        </div>
                                    );
                                })}
                            </div>
                        </KPICard>

                        {/* 2. Finalized Quotes */}
                        <KPICard
                            title="Finalized Quotes"
                            value={metricsLoading ? <Skeleton className="h-9 w-16" /> : (dashboardMetrics?.finalized_count ?? metrics.finalizedCount)}
                            description={
                                metricsLoading
                                    ? undefined
                                    : (dashboardMetrics?.finalized_count ?? metrics.finalizedCount) > 0
                                        ? "Finalized or accepted in the selected period"
                                        : "No finalized or accepted quotes in the selected period"
                            }
                            status="success"
                            icon={CheckCircle2}
                            trend={{
                                value: metricsLoading ? <Skeleton className="h-4 w-20" /> : formatCurrency(String(dashboardMetrics?.finalized_value ?? metrics.finalizedValue), 'PGK'),
                                label: "Total Value",
                                positive: true
                            }}
                        />

                        {/* 3. Total Pipeline */}
                        <KPICard
                            title="Total Pipeline"
                            value={metricsLoading ? <Skeleton className="h-9 w-32" /> : formatCurrency(String(dashboardMetrics?.pipeline_value ?? metrics.pipelineValue), 'PGK')}
                            description={`${dashboardMetrics?.pipeline_count ?? metrics.draftCount} draft${(dashboardMetrics?.pipeline_count ?? metrics.draftCount) !== 1 ? 's' : ''} in progress`}
                            status="info"
                            icon={DollarSign}
                        />
                    </div>

                    {/* Row 2: Sales Efficiency Metrics */}
                    <div className="grid gap-6 md:grid-cols-3">
                        {/* 4. Win Rate % */}
                        <KPICard
                            title="Win Rate"
                            value={metricsLoading ? "-" : `${dashboardMetrics?.win_rate_percent ?? metrics.winRatePercent}%`}
                            status={
                                (dashboardMetrics?.total_quotes_sent ?? metrics.totalSentCount) === 0 ? "neutral" :
                                    (dashboardMetrics?.win_rate_percent ?? metrics.winRatePercent) >= 30 ? "success" : "warning"
                            }
                            icon={TrendingUp}
                            description={`${dashboardMetrics?.quotes_accepted ?? metrics.acceptedCount} won of ${dashboardMetrics?.total_quotes_sent ?? metrics.totalSentCount} sent`}
                        >
                            {/* Simple visual bar for Win Rate */}
                            <div className="mt-4 h-2 w-full bg-slate-100 rounded-full overflow-hidden">
                                <div
                                    className={`h-full rounded-full ${(dashboardMetrics?.win_rate_percent ?? metrics.winRatePercent) >= 30 ? 'bg-success' : 'bg-warning'
                                        }`}
                                    style={{ width: `${Math.min(dashboardMetrics?.win_rate_percent ?? metrics.winRatePercent, 100)}%` }}
                                />
                            </div>
                        </KPICard>

                        {/* 5. Avg Quote Value */}
                        <KPICard
                            title="Avg Quote Value"
                            value={metricsLoading ? <Skeleton className="h-9 w-28" /> : formatCurrency(String(dashboardMetrics?.avg_quote_value ?? metrics.avgQuoteValue), dashboardMetrics ? 'PGK' : metrics.currency)}
                            description="Based on finalized or accepted quotes in the selected period"
                            status="info"
                            icon={DollarSign}
                        />

                        {/* 6. Lost Opportunity */}
                        <KPICard
                            title="Lost Opportunity"
                            value={metricsLoading ? <Skeleton className="h-9 w-28" /> : formatCurrency(String(dashboardMetrics?.lost_opportunity_value ?? metrics.lostOpportunityValue), dashboardMetrics ? 'PGK' : metrics.currency)}
                            description={`${(dashboardMetrics?.quotes_lost ?? metrics.lostCount) + (dashboardMetrics?.quotes_expired ?? metrics.expiredCount)} quotes lost or expired`}
                            status="danger"
                            icon={AlertCircle}
                        />
                    </div>

                    {/* Row 3: Tier-1 Customer Stats */}
                    <div>
                        <h3 className="text-sm font-semibold text-slate-500 mb-3 uppercase tracking-wider">Customer Engagement</h3>
                        <Tier1StatsRow timeframe={timeframe} />
                    </div>
                </section>


            </main>
        </ProtectedRoute >
    );
}
