"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Loader2, PlusCircle, ArrowRight, FileText, CheckCircle2, DollarSign } from "lucide-react";
import ProtectedRoute from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import { getQuotesV3, listSpotEnvelopes } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import type { V3QuoteComputeResponse } from "@/lib/types";
import { SpotPricingEnvelope } from "@/lib/spot-types";
import { UnifiedQuote, formatCurrency, formatRoute, formatDate, getWeight, getCustomerName } from "@/lib/quote-helpers";
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";



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

    // Metrics calculations
    const metrics = useMemo(() => {
        const draftQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'draft');
        const finalizedQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'finalized');
        const sentQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'sent');
        const approvedQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'approved');
        const cancelledQuotes = allQuotes.filter(q => q.status?.toLowerCase() === 'cancelled');

        const currency = allQuotes[0]?.latest_version.totals.total_sell_fcy_currency ?? "PGK";

        // Total value of finalized quotes
        const finalizedValue = finalizedQuotes.reduce((sum, quote) => {
            const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
            return sum + (isNaN(amount) ? 0 : amount);
        }, 0);

        // Pipeline value (all non-cancelled)
        const pipelineValue = allQuotes
            .filter(q => q.status?.toLowerCase() !== 'cancelled')
            .reduce((sum, quote) => {
                const amount = parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0");
                return sum + (isNaN(amount) ? 0 : amount);
            }, 0);

        return {
            draftCount: draftQuotes.length,
            finalizedCount: finalizedQuotes.length,
            sentCount: sentQuotes.length,
            approvedCount: approvedQuotes.length,
            cancelledCount: cancelledQuotes.length,
            totalQuotes: allQuotes.length,
            finalizedValue,
            pipelineValue,
            currency,
        };
    }, [allQuotes]);

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
                weight: getWeight(q),
                status: q.status,
                rawStatus: q.status,
                total: formatCurrency(totalAmt, currency),
                actionLink: `/quotes/${q.id}`,
            });
        });

        // 2. Add Spot Drafts
        spotDrafts.forEach(d => {
            unified.push({
                id: d.id,
                type: "SPOT_DRAFT",
                number: `SPOT-${d.id.substring(0, 6).toUpperCase()}`,
                customer: d.customer_name || "-",
                route: `${formatRoute(d.shipment.origin_code)} → ${formatRoute(d.shipment.destination_code)}`,
                date: d.created_at,
                weight: `${d.shipment.total_weight_kg} kg`,
                status: "Draft",
                rawStatus: "DRAFT",
                total: "-",
                actionLink: `/quotes/spot/${d.id}`,
            });
        });

        return unified.sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime()).slice(0, 5);
    }, [allQuotes, spotDrafts]);


    const renderRecentQuotes = () => {
        if (loading) {
            return (
                <div className="flex items-center justify-center py-12 text-muted-foreground">
                    <Loader2 className="mr-2 h-5 w-5 animate-spin" />
                    <span className="text-sm">Loading quotes...</span>
                </div>
            );
        }

        if (error) {
            return (
                <Alert variant="destructive">
                    <AlertTitle>Something went wrong</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            );
        }

        if (recentQuotes.length === 0) {
            return (
                <div className="flex flex-col items-center justify-center gap-3 py-12 text-center text-muted-foreground">
                    <FileText className="h-12 w-12 opacity-30" />
                    <p className="text-sm">No quotes available.</p>
                </div>
            );
        }

        return (
            <div className="overflow-hidden">
                <Table>
                    <TableHeader>
                        <TableRow className="bg-muted/30 hover:bg-muted/30">
                            <TableHead className="font-semibold text-primary">Quote #</TableHead>
                            <TableHead className="font-semibold">Date</TableHead>
                            <TableHead className="font-semibold">Customer</TableHead>
                            <TableHead className="font-semibold">Route</TableHead>
                            <TableHead className="font-semibold text-right">Weight</TableHead>
                            <TableHead className="font-semibold">Status</TableHead>
                            <TableHead className="text-right font-semibold">Total (inc. GST)</TableHead>
                        </TableRow>
                    </TableHeader>
                    <TableBody>
                        {recentQuotes.map((quote) => (
                            <TableRow
                                key={quote.id}
                                className="cursor-pointer hover:bg-primary/5 transition-colors"
                                onClick={() => window.location.href = quote.actionLink}
                            >
                                <TableCell>
                                    <span className="text-primary font-semibold hover:underline">
                                        {quote.number}
                                    </span>
                                </TableCell>
                                <TableCell className="text-muted-foreground text-sm">
                                    {formatDate(quote.date)}
                                </TableCell>
                                <TableCell className="max-w-[200px] truncate" title={quote.customer}>
                                    {quote.customer}
                                </TableCell>
                                <TableCell className="text-muted-foreground">
                                    {quote.route}
                                </TableCell>
                                <TableCell className="text-right font-mono text-xs text-muted-foreground">
                                    {quote.weight}
                                </TableCell>
                                <TableCell>
                                    {quote.type === "SPOT_DRAFT" ? (
                                        <span className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-xs font-semibold text-amber-700">
                                            Draft (SPOT)
                                        </span>
                                    ) : (
                                        <QuoteStatusBadge status={quote.rawStatus} />
                                    )}
                                </TableCell>
                                <TableCell className="text-right font-semibold tabular-nums">
                                    {quote.total}
                                </TableCell>
                            </TableRow>
                        ))}
                    </TableBody>
                </Table>
            </div>
        );
    };

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



        // Helper to format mode
        const formatMode = (mode: string): string => {
            const modeMap: Record<string, string> = {
                'AIR': 'Air Freight', 'air': 'Air Freight',
                'SEA': 'Sea Freight', 'sea': 'Sea Freight',
                'INLAND': 'Inland Transport', 'inland': 'Inland Transport',
                'ROAD': 'Inland Transport', 'road': 'Inland Transport',
            };
            return modeMap[mode] || mode;
        };



        // Helper to format status text
        const formatStatus = (status: string): string => {
            const s = status?.toLowerCase();
            if (s === 'draft') return 'Draft';
            if (s === 'finalized') return 'Finalized';
            if (s === 'sent') return 'Sent';
            if (s === 'approved') return 'Approved';
            return status;
        };

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

                    {/* Finance KPI Widgets - No Icons, Text Only */}
                    <section className="grid gap-6 md:grid-cols-3">
                        {/* Widget A: Finalized Revenue (PGK) */}
                        <Card className="border border-slate-200 shadow-sm bg-white hover:shadow-md transition-shadow">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">
                                    Finalized Revenue (This Month)
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-slate-900">
                                    PGK {finalizedRevenuePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {finalizedThisMonth.length} finalized quotes
                                </p>
                            </CardContent>
                        </Card>

                        {/* Widget B: Pipeline Exposure (Draft Quotes in PGK) */}
                        <Card className="border border-slate-200 shadow-sm bg-white hover:shadow-md transition-shadow">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">
                                    Pipeline Exposure (Drafts)
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-slate-900">
                                    PGK {pipelinePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                                </div>
                                <p className="text-xs text-muted-foreground mt-1">
                                    {draftQuotes.length} draft quotes in market
                                </p>
                            </CardContent>
                        </Card>

                        {/* Widget C: FX Rates - Text List */}
                        <Card className="border border-slate-200 shadow-sm bg-white hover:shadow-md transition-shadow">
                            <CardHeader className="pb-2">
                                <CardTitle className="text-sm font-medium text-muted-foreground">
                                    FX Rates
                                </CardTitle>
                            </CardHeader>
                            <CardContent>
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
                                                Status: {fxStatus.is_stale ? 'Stale' : 'Current'}
                                            </p>
                                            <p className="text-xs text-muted-foreground">
                                                Source: {fxStatus.source || 'BSP'}
                                            </p>
                                        </div>
                                    </div>
                                ) : (
                                    <p className="text-sm text-muted-foreground">Loading rates...</p>
                                )}
                            </CardContent>
                        </Card>
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
                                <div className="flex flex-col items-center justify-center gap-3 py-12 text-center text-muted-foreground">
                                    <p className="text-sm">No quotes available.</p>
                                </div>
                            ) : (
                                <div className="overflow-x-auto">
                                    <Table>
                                        <TableHeader>
                                            <TableRow className="bg-muted/30">
                                                <TableHead>Quote #</TableHead>
                                                <TableHead>Customer</TableHead>
                                                <TableHead>Route</TableHead>
                                                <TableHead>Mode</TableHead>
                                                <TableHead className="text-right">Total (Inc. GST)</TableHead>
                                                <TableHead>Status</TableHead>
                                                <TableHead>Action</TableHead>
                                            </TableRow>
                                        </TableHeader>
                                        <TableBody>
                                            {recentQuotes.map((quote) => (
                                                <TableRow key={quote.id}>
                                                    <TableCell className="font-medium">{quote.quote_number}</TableCell>
                                                    <TableCell>{getCustomerName(quote.customer)}</TableCell>
                                                    <TableCell className="text-muted-foreground">
                                                        {formatRoute(quote.origin_location)} → {formatRoute(quote.destination_location)}
                                                    </TableCell>
                                                    <TableCell>{formatMode(quote.mode)}</TableCell>
                                                    <TableCell className="text-right font-medium tabular-nums">
                                                        PGK {parseFloat(quote.latest_version.totals.total_sell_pgk_incl_gst || quote.latest_version.totals.total_sell_fcy_incl_gst || "0").toLocaleString('en-US', { maximumFractionDigits: 0 })}
                                                    </TableCell>
                                                    <TableCell>{formatStatus(quote.status)}</TableCell>
                                                    <TableCell>
                                                        <Link href={`/quotes/${quote.id}`} className="text-primary hover:underline text-sm">
                                                            View Quote
                                                        </Link>
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
            <main className="container mx-auto space-y-8 py-8 max-w-7xl">
                {/* Sales Hero Section - Flat Blue */}
                <section className="rounded-3xl bg-primary px-8 py-10 shadow-xl">
                    <div className="relative z-10">
                        <span className="text-sm font-semibold uppercase tracking-wider text-primary-foreground/80">
                            Welcome back, {displayName}
                        </span>
                        <h1 className="mt-2 text-4xl font-bold text-white tracking-tight">
                            Your quoting control center
                        </h1>
                        <p className="mt-3 max-w-2xl text-lg text-primary-foreground/90">
                            Monitor the pipeline, draft new quotes, and keep customers moving — all from one place.
                        </p>
                        <div className="mt-8 flex flex-wrap gap-4">
                            {canEditQuotes && (
                                <Button
                                    size="lg"
                                    className="bg-white text-primary hover:bg-white/90 shadow-sm border border-transparent font-semibold"
                                    asChild
                                >
                                    <Link href="/quotes/new">
                                        <PlusCircle className="mr-2 h-4 w-4" />
                                        New Quote
                                    </Link>
                                </Button>
                            )}
                            <Button
                                variant="outline"
                                size="lg"
                                className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white hover:border-white/50"
                                asChild
                            >
                                <Link href="/quotes">
                                    View Quotes
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                            {(isManager || isAdmin) && (
                                <Button
                                    variant="outline"
                                    size="lg"
                                    className="border-white/30 bg-transparent text-white hover:bg-white/10 hover:text-white hover:border-white/50"
                                    asChild
                                >
                                    <Link href="/dashboard/management">
                                        Management Overview
                                    </Link>
                                </Button>
                            )}
                            <Button
                                variant="ghost"
                                size="lg"
                                className="text-white/80 hover:text-white hover:bg-white/10"
                                asChild
                            >
                                <Link href="/customers">Manage Customers</Link>
                            </Button>
                        </div>
                    </div>
                </section>

                {/* Sales KPI Cards */}
                <section className="grid gap-6 md:grid-cols-3">
                    <Card className="border border-slate-200 shadow-sm bg-white hover:shadow-md transition-shadow">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-slate-600">Draft Quotes</CardTitle>
                            <div className="p-2 bg-slate-100/50 rounded-full">
                                <FileText className="h-5 w-5 text-slate-500" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold tracking-tight text-slate-900">{metrics.draftCount}</div>
                            <p className="text-sm text-muted-foreground mt-1">Quotes in progress</p>
                        </CardContent>
                    </Card>

                    <Card className="border border-emerald-100 shadow-sm bg-white hover:shadow-md transition-shadow">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-emerald-700">Finalized Quotes</CardTitle>
                            <div className="p-2 bg-emerald-50 rounded-full">
                                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-emerald-700 tracking-tight">{metrics.finalizedCount}</div>
                            <p className="text-sm text-emerald-600/80 mt-1">Fully rated by engine</p>
                        </CardContent>
                    </Card>

                    <Card className="border border-blue-100 shadow-sm bg-white hover:shadow-md transition-shadow">
                        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                            <CardTitle className="text-sm font-medium text-primary">Pipeline Value</CardTitle>
                            <div className="p-2 bg-blue-50 rounded-full">
                                <DollarSign className="h-5 w-5 text-primary" />
                            </div>
                        </CardHeader>
                        <CardContent>
                            <div className="text-3xl font-bold text-primary tracking-tight">
                                {formatCurrency(metrics.pipelineValue, metrics.currency)}
                            </div>
                            <p className="text-sm text-primary/70 mt-1">Total value (inc. GST)</p>
                        </CardContent>
                    </Card>
                </section>

                {/* Recent Activity - Standard Table */}
                <Card className="border border-slate-200 shadow-sm bg-white scroll-mt-20">
                    <CardHeader className="border-b bg-slate-50/40 px-6 py-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <CardTitle className="text-lg font-semibold text-slate-800">Recent Activity</CardTitle>
                                <CardDescription className="mt-1">Latest quotes managed by you and your team</CardDescription>
                            </div>
                            <Button variant="outline" size="sm" className="bg-white" asChild>
                                <Link href="/quotes">
                                    View All
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Link>
                            </Button>
                        </div>
                    </CardHeader>
                    <CardContent className="p-0">{renderRecentQuotes()}</CardContent>
                </Card>
            </main>
        </ProtectedRoute>
    );
}
