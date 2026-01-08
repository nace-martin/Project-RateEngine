"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Loader2, PlusCircle, ArrowRight, FileText, CheckCircle2, DollarSign, AlertTriangle, TrendingUp, RefreshCw, Clock, Activity, BarChart3, Shield } from "lucide-react";
import ProtectedRoute from "@/components/protected-route";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import { getQuotesV3 } from "@/lib/api";
import { API_BASE_URL } from "@/lib/config";
import type { V3QuoteComputeResponse } from "@/lib/types";
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
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { QuoteStatusBadge } from "@/components/QuoteStatusBadge";

const formatCurrency = (value: number, currency = "PGK") =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value || 0);

interface FxStatusData {
  rates: Array<{ currency: string; tt_buy: string; tt_sell: string }>;
  last_updated: string | null;
  source: string | null;
  is_stale: boolean;
  staleness_hours: number | null;
  staleness_warning: string | null;
}

export default function HomePage() {
  const { user } = useAuth();
  const { isFinance, canEditQuotes } = usePermissions();
  const [allQuotes, setAllQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [fxStatus, setFxStatus] = useState<FxStatusData | null>(null);
  const [fxLoading, setFxLoading] = useState(false);

  useEffect(() => {
    if (!user) {
      return;
    }
    const fetchQuotes = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await getQuotesV3();
        setAllQuotes(data.results);
      } catch (err: unknown) {
        const message =
          err instanceof Error ? err.message : "Unable to load quotes.";
        setError(message);
      } finally {
        setLoading(false);
      }
    };
    fetchQuotes();
  }, [user]);

  // Fetch FX status for Finance users
  useEffect(() => {
    if (!user || !isFinance) return;

    const fetchFxStatus = async () => {
      setFxLoading(true);
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
      } finally {
        setFxLoading(false);
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

  const recentQuotes = useMemo(() => allQuotes.slice(0, 5), [allQuotes]);

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
              <TableHead className="font-semibold">Quote #</TableHead>
              <TableHead className="font-semibold">Route</TableHead>
              <TableHead className="font-semibold">Status</TableHead>
              <TableHead className="text-right font-semibold">Total (inc. GST)</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {recentQuotes.map((quote) => (
              <TableRow
                key={quote.id}
                className="cursor-pointer hover:bg-primary/5 transition-colors"
                onClick={() => window.location.href = `/quotes/${quote.id}`}
              >
                <TableCell>
                  <span className="text-primary font-semibold hover:underline">
                    {quote.quote_number}
                  </span>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {quote.origin_location}
                  <span className="mx-2 text-muted-foreground/50">→</span>
                  {quote.destination_location}
                </TableCell>
                <TableCell>
                  <QuoteStatusBadge status={quote.status} />
                </TableCell>
                <TableCell className="text-right font-semibold tabular-nums">
                  {formatCurrency(
                    parseFloat(quote.latest_version.totals.total_sell_fcy_incl_gst || "0"),
                    quote.latest_version.totals.total_sell_fcy_currency,
                  )}
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

    // Helper to format route as "City (CODE)"
    const formatRoute = (location: string): string => {
      if (!location) return '';
      const match = location.match(/^([A-Z]{3})\s*-\s*(.+)$/);
      if (match) {
        const [, code, fullName] = match;
        const cityName = fullName.replace(/\s+(Airport|Intl|International|Jacksons|Terminal|Apt).*$/i, '').trim();
        return `${cityName} (${code})`;
      }
      return location;
    };

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

    // Helper to get customer name
    const getCustomerName = (customer: typeof allQuotes[0]['customer']): string => {
      if (typeof customer === 'string') return customer;
      return customer?.company_name || customer?.name || 'Unknown';
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
          <section className="rounded-2xl bg-slate-900 px-8 py-8">
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
              <Button size="default" className="bg-white text-slate-900 hover:bg-slate-100" asChild>
                <Link href="/quotes">View All Quotes</Link>
              </Button>
              <Button variant="outline" size="default" className="border-slate-600 text-slate-300 hover:bg-slate-800 hover:text-white" asChild>
                <Link href="/settings">Rate Controls</Link>
              </Button>
            </div>
          </section>

          {/* Finance KPI Widgets - No Icons, Text Only */}
          <section className="grid gap-6 md:grid-cols-3">
            {/* Widget A: Finalized Revenue (PGK) */}
            <Card className="border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Finalized Revenue (This Month)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  PGK {finalizedRevenuePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {finalizedThisMonth.length} finalized quotes
                </p>
              </CardContent>
            </Card>

            {/* Widget B: Pipeline Exposure (Draft Quotes in PGK) */}
            <Card className="border">
              <CardHeader className="pb-2">
                <CardTitle className="text-sm font-medium text-muted-foreground">
                  Pipeline Exposure (Drafts)
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  PGK {pipelinePGK.toLocaleString('en-US', { maximumFractionDigits: 0 })}
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  {draftQuotes.length} draft quotes in market
                </p>
              </CardContent>
            </Card>

            {/* Widget C: FX Rates - Text List */}
            <Card className="border">
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
          <Card className="border">
            <CardHeader className="border-b">
              <div className="flex items-center justify-between">
                <div>
                  <CardTitle>Recent Quote Activity</CardTitle>
                  <CardDescription>Latest quotes for audit and review</CardDescription>
                </div>
                <Button variant="outline" size="sm" asChild>
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
        {/* Sales Hero Section - Premium Gradient */}
        <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-900 via-primary/90 to-primary px-8 py-10 shadow-2xl">
          <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmZmZmYiIGZpbGwtb3BhY2l0eT0iMC4wMyI+PHBhdGggZD0iTTM2IDM0djItSDI0di0yaDEyek0zNiAyNHYySDI0di0yaDEyeiIvPjwvZz48L2c+PC9zdmc+')] opacity-50" />
          <div className="relative z-10">
            <span className="text-sm font-semibold uppercase tracking-wider text-primary-foreground/70">
              Welcome back, {displayName}
            </span>
            <h1 className="mt-2 text-4xl font-bold text-white tracking-tight">
              Your quoting control center
            </h1>
            <p className="mt-3 max-w-2xl text-lg text-primary-foreground/80">
              Monitor the pipeline, draft new quotes, and keep customers moving — all from one place.
            </p>
            <div className="mt-8 flex flex-wrap gap-4">
              {canEditQuotes && (
                <Button
                  size="lg"
                  className="bg-white text-primary hover:bg-white/90 shadow-lg"
                  asChild
                >
                  <Link href="/quotes/new">
                    <PlusCircle className="mr-2 h-4 w-4" />
                    New Quote
                  </Link>
                </Button>
              )}
              <Button
                variant="secondary"
                size="lg"
                className="bg-white/10 hover:bg-white/20 text-white border-white/20 backdrop-blur-sm"
                asChild
              >
                <Link href="/quotes">
                  View Quotes
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Link>
              </Button>
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
          <Card className="relative overflow-hidden border-0 bg-white shadow-lg">
            <div className="absolute top-0 right-0 w-32 h-32 bg-slate-100 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
              <CardTitle className="text-sm font-medium text-slate-600">Draft Quotes</CardTitle>
              <div className="p-2 bg-slate-100 rounded-lg">
                <FileText className="h-5 w-5 text-slate-500" />
              </div>
            </CardHeader>
            <CardContent className="relative">
              <div className="text-3xl font-bold tracking-tight">{metrics.draftCount}</div>
              <p className="text-sm text-muted-foreground mt-1">Quotes in progress</p>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-emerald-50 to-emerald-100/50 shadow-lg">
            <div className="absolute top-0 right-0 w-32 h-32 bg-emerald-200/30 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
              <CardTitle className="text-sm font-medium text-emerald-700">Finalized Quotes</CardTitle>
              <div className="p-2 bg-emerald-500/10 rounded-lg">
                <CheckCircle2 className="h-5 w-5 text-emerald-600" />
              </div>
            </CardHeader>
            <CardContent className="relative">
              <div className="text-3xl font-bold text-emerald-700 tracking-tight">{metrics.finalizedCount}</div>
              <p className="text-sm text-emerald-600/80 mt-1">Fully rated by engine</p>
            </CardContent>
          </Card>

          <Card className="relative overflow-hidden border-0 bg-gradient-to-br from-primary/5 to-primary/10 shadow-lg">
            <div className="absolute top-0 right-0 w-32 h-32 bg-primary/10 rounded-full blur-2xl -translate-y-1/2 translate-x-1/2" />
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2 relative">
              <CardTitle className="text-sm font-medium text-primary/80">Pipeline Value</CardTitle>
              <div className="p-2 bg-primary/10 rounded-lg">
                <DollarSign className="h-5 w-5 text-primary" />
              </div>
            </CardHeader>
            <CardContent className="relative">
              <div className="text-3xl font-bold text-primary tracking-tight">
                {formatCurrency(metrics.pipelineValue, metrics.currency)}
              </div>
              <p className="text-sm text-primary/60 mt-1">Total value (inc. GST)</p>
            </CardContent>
          </Card>
        </section>

        {/* Recent Activity - Premium Table */}
        <Card className="border-0 shadow-lg overflow-hidden">
          <CardHeader className="bg-slate-50/50 border-b">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-lg font-semibold">Recent Activity</CardTitle>
                <CardDescription className="mt-1">Latest quotes managed by you and your team</CardDescription>
              </div>
              <Button variant="outline" size="sm" asChild>
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
