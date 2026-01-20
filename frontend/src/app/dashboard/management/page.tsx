"use client";

import { useEffect, useState, useMemo } from "react";
import { useRouter } from "next/navigation";
import { format, startOfMonth } from "date-fns";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import {
    getFunnelMetrics,
    getRevenueMargin,
    getUserPerformance,
    exportReportData,
    FunnelMetricsData,
    RevenueMarginData,
    UserPerformanceData,
    UserPerformanceItem,
    ReportFilters,
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { DateRangePicker, DateRange } from "@/components/ui/date-range-picker";
import {
    Loader2,
    TrendingUp,
    DollarSign,
    ArrowLeft,
    Download,
    Users,
    Clock,
    Target,
    BarChart3,
    ArrowUpDown,
} from "lucide-react";
import {
    BarChart,
    Bar,
    XAxis,
    YAxis,
    CartesianGrid,
    Tooltip,
    ResponsiveContainer,
    Cell,
} from "recharts";

type SortKey = keyof UserPerformanceItem;
type SortDirection = "asc" | "desc";

export default function CommercialPerformancePage() {
    const { user } = useAuth();
    const { isManager, isAdmin, isFinance } = usePermissions();
    const router = useRouter();

    // Filter state
    const [dateRange, setDateRange] = useState<DateRange | undefined>(() => {
        const now = new Date();
        return {
            from: startOfMonth(now),
            to: now,
        };
    });
    const [selectedMode, setSelectedMode] = useState<"ALL" | "AIR" | "SEA">("ALL");

    // Data state
    const [funnelData, setFunnelData] = useState<FunnelMetricsData | null>(null);
    const [marginData, setMarginData] = useState<RevenueMarginData | null>(null);
    const [performanceData, setPerformanceData] = useState<UserPerformanceData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [exporting, setExporting] = useState(false);

    // Sorting state for team table
    const [sortKey, setSortKey] = useState<SortKey>("total_gp");
    const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

    const hasAccess = isManager || isAdmin || isFinance;

    // Build filters object
    const filters: ReportFilters = useMemo(() => ({
        start_date: dateRange?.from ? format(dateRange.from, "yyyy-MM-dd") : undefined,
        end_date: dateRange?.to ? format(dateRange.to, "yyyy-MM-dd") : undefined,
        mode: selectedMode === "ALL" ? undefined : selectedMode,
    }), [dateRange, selectedMode]);

    // Fetch all data
    useEffect(() => {
        if (!user || !hasAccess) return;

        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [funnel, margin, performance] = await Promise.all([
                    getFunnelMetrics(filters),
                    getRevenueMargin(filters),
                    getUserPerformance(filters),
                ]);
                setFunnelData(funnel);
                setMarginData(margin);
                setPerformanceData(performance);
            } catch (err: unknown) {
                const message = err instanceof Error ? err.message : "Failed to load reports.";
                setError(message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [user, hasAccess, filters]);

    // Handle CSV export
    const handleExport = async () => {
        setExporting(true);
        try {
            const blob = await exportReportData(filters);
            const url = window.URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.download = `commercial_report_${format(new Date(), "yyyy-MM-dd")}.csv`;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        } catch (err) {
            console.error("Export failed:", err);
        } finally {
            setExporting(false);
        }
    };

    // Sort users
    const sortedUsers = useMemo(() => {
        if (!performanceData?.users) return [];
        return [...performanceData.users].sort((a, b) => {
            const aVal = a[sortKey];
            const bVal = b[sortKey];
            if (typeof aVal === "number" && typeof bVal === "number") {
                return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
            }
            return 0;
        });
    }, [performanceData, sortKey, sortDirection]);

    const handleSort = (key: SortKey) => {
        if (sortKey === key) {
            setSortDirection(sortDirection === "asc" ? "desc" : "asc");
        } else {
            setSortKey(key);
            setSortDirection("desc");
        }
    };

    // Funnel chart data
    const funnelChartData = useMemo(() => {
        if (!funnelData) return [];
        return [
            { name: "Created", value: funnelData.quotes_created, fill: "#6366f1" },
            { name: "Sent", value: funnelData.quotes_sent, fill: "#3b82f6" },
            { name: "Won", value: funnelData.quotes_accepted, fill: "#22c55e" },
        ];
    }, [funnelData]);

    // Helper functions
    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat("en-PG", {
            style: "currency",
            currency: "PGK",
            maximumFractionDigits: 0,
        }).format(amount);
    };

    const formatTimeToQuote = (minutes: number | null) => {
        if (minutes === null) return "—";
        const hours = Math.floor(minutes / 60);
        const mins = Math.round(minutes % 60);
        if (hours > 0) return `${hours}h ${mins}m`;
        return `${mins}m`;
    };

    if (!user) return null;

    if (!hasAccess) {
        return (
            <div className="container mx-auto p-8">
                <Alert variant="destructive">
                    <AlertTitle>Access Denied</AlertTitle>
                    <AlertDescription>You do not have permission to view this page.</AlertDescription>
                </Alert>
                <Button className="mt-4" onClick={() => router.push("/dashboard")}>
                    Back to Dashboard
                </Button>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center p-12">
                <Loader2 className="mr-2 h-8 w-8 animate-spin" />
                <span>Loading commercial reports...</span>
            </div>
        );
    }

    if (error) {
        return (
            <div className="container mx-auto p-8">
                <Alert variant="destructive">
                    <AlertTitle>Error</AlertTitle>
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            </div>
        );
    }

    return (
        <div className="container mx-auto p-4 max-w-7xl space-y-6">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Commercial Performance</h1>
                    <p className="text-muted-foreground">Quote funnel, revenue, and team performance analysis.</p>
                </div>
                <Button variant="outline" onClick={() => router.push("/dashboard")}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to Dashboard
                </Button>
            </div>

            {/* Global Filters Bar */}
            <div className="flex flex-wrap items-center gap-4 p-4 bg-muted/50 rounded-lg border">
                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">Date Range:</span>
                    <DateRangePicker value={dateRange} onChange={setDateRange} />
                </div>

                <div className="flex items-center gap-2">
                    <span className="text-sm font-medium">Mode:</span>
                    <Select value={selectedMode} onValueChange={(v) => setSelectedMode(v as "ALL" | "AIR" | "SEA")}>
                        <SelectTrigger className="w-[120px]">
                            <SelectValue placeholder="All" />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ALL">All</SelectItem>
                            <SelectItem value="AIR">Air</SelectItem>
                            <SelectItem value="SEA">Sea</SelectItem>
                        </SelectContent>
                    </Select>
                </div>

                <div className="flex-1" />

                <Button onClick={handleExport} disabled={exporting}>
                    {exporting ? (
                        <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    ) : (
                        <Download className="mr-2 h-4 w-4" />
                    )}
                    Export to CSV
                </Button>
            </div>

            {/* Tabs */}
            <Tabs defaultValue="funnel" className="space-y-4">
                <TabsList>
                    <TabsTrigger value="funnel">Funnel & Efficiency</TabsTrigger>
                    <TabsTrigger value="financials">Financials</TabsTrigger>
                    <TabsTrigger value="team">Team Performance</TabsTrigger>
                </TabsList>

                {/* Funnel & Efficiency Tab */}
                <TabsContent value="funnel" className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Quotes Created</CardTitle>
                                <BarChart3 className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{funnelData?.quotes_created ?? 0}</div>
                                <p className="text-xs text-muted-foreground">In selected period</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Avg Time to Quote</CardTitle>
                                <Clock className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">
                                    {formatTimeToQuote(funnelData?.avg_time_to_quote_minutes ?? null)}
                                </div>
                                <p className="text-xs text-muted-foreground">Created to Sent</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Win Rate</CardTitle>
                                <Target className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-green-600">
                                    {funnelData?.conversion_rate ?? 0}%
                                </div>
                                <p className="text-xs text-muted-foreground">
                                    {funnelData?.quotes_accepted ?? 0} won / {funnelData?.quotes_sent ?? 0} sent
                                </p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Lost</CardTitle>
                                <TrendingUp className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-red-600">{funnelData?.quotes_lost ?? 0}</div>
                                <p className="text-xs text-muted-foreground">Quotes lost</p>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Funnel Chart */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Quote Funnel</CardTitle>
                            <CardDescription>Progression from creation to conversion</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <div className="h-[300px]">
                                <ResponsiveContainer width="100%" height="100%">
                                    <BarChart data={funnelChartData} layout="vertical">
                                        <CartesianGrid strokeDasharray="3 3" horizontal={false} />
                                        <XAxis type="number" />
                                        <YAxis type="category" dataKey="name" width={80} />
                                        <Tooltip
                                            formatter={(value) => [value, "Quotes"]}
                                            contentStyle={{ borderRadius: "8px" }}
                                        />
                                        <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                                            {funnelChartData.map((entry, index) => (
                                                <Cell key={`cell-${index}`} fill={entry.fill} />
                                            ))}
                                        </Bar>
                                    </BarChart>
                                </ResponsiveContainer>
                            </div>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Financials Tab */}
                <TabsContent value="financials" className="space-y-4">
                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
                                <DollarSign className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{formatCurrency(marginData?.total_revenue ?? 0)}</div>
                                <p className="text-xs text-muted-foreground">Finalized quotes</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Total Cost</CardTitle>
                                <DollarSign className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{formatCurrency(marginData?.total_cost ?? 0)}</div>
                                <p className="text-xs text-muted-foreground">COGS</p>
                            </CardContent>
                        </Card>

                        <Card className="border-green-200 bg-green-50/50">
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Gross Profit</CardTitle>
                                <TrendingUp className="h-4 w-4 text-green-600" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold text-green-700">
                                    {formatCurrency(marginData?.total_gross_profit ?? 0)}
                                </div>
                                <p className="text-xs text-muted-foreground">Revenue - Cost</p>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                                <CardTitle className="text-sm font-medium">Avg Margin</CardTitle>
                                <Target className="h-4 w-4 text-muted-foreground" />
                            </CardHeader>
                            <CardContent>
                                <div className="text-2xl font-bold">{marginData?.avg_margin_percent ?? 0}%</div>
                                <p className="text-xs text-muted-foreground">Margin percentage</p>
                            </CardContent>
                        </Card>
                    </div>

                    {/* Margin by Mode Table */}
                    <Card>
                        <CardHeader>
                            <CardTitle>Margin by Mode</CardTitle>
                            <CardDescription>Financial breakdown by transport mode</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Mode</TableHead>
                                        <TableHead className="text-right">Revenue</TableHead>
                                        <TableHead className="text-right">Cost</TableHead>
                                        <TableHead className="text-right">GP</TableHead>
                                        <TableHead className="text-right">Margin %</TableHead>
                                        <TableHead className="text-right">Quotes</TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {marginData?.by_mode.map((item) => (
                                        <TableRow key={item.mode}>
                                            <TableCell className="font-medium">{item.mode}</TableCell>
                                            <TableCell className="text-right font-mono">{formatCurrency(item.revenue)}</TableCell>
                                            <TableCell className="text-right font-mono">{formatCurrency(item.cost)}</TableCell>
                                            <TableCell className="text-right font-mono text-green-700">
                                                {formatCurrency(item.gross_profit)}
                                            </TableCell>
                                            <TableCell className="text-right font-mono">{item.margin_percent}%</TableCell>
                                            <TableCell className="text-right">{item.count}</TableCell>
                                        </TableRow>
                                    ))}
                                    {(!marginData?.by_mode || marginData.by_mode.length === 0) && (
                                        <TableRow>
                                            <TableCell colSpan={6} className="text-center text-muted-foreground">
                                                No data available for the selected period.
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>

                {/* Team Performance Tab */}
                <TabsContent value="team" className="space-y-4">
                    <Card>
                        <CardHeader>
                            <CardTitle className="flex items-center gap-2">
                                <Users className="h-5 w-5" />
                                Team Performance
                            </CardTitle>
                            <CardDescription>Individual sales performance metrics. Click column headers to sort.</CardDescription>
                        </CardHeader>
                        <CardContent>
                            <Table>
                                <TableHeader>
                                    <TableRow>
                                        <TableHead>Sales User</TableHead>
                                        <TableHead
                                            className="text-right cursor-pointer hover:bg-muted/50"
                                            onClick={() => handleSort("quotes_sent")}
                                        >
                                            <div className="flex items-center justify-end gap-1">
                                                Quotes Sent
                                                <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </TableHead>
                                        <TableHead
                                            className="text-right cursor-pointer hover:bg-muted/50"
                                            onClick={() => handleSort("quotes_won")}
                                        >
                                            <div className="flex items-center justify-end gap-1">
                                                Wins
                                                <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </TableHead>
                                        <TableHead
                                            className="text-right cursor-pointer hover:bg-muted/50"
                                            onClick={() => handleSort("conversion_rate")}
                                        >
                                            <div className="flex items-center justify-end gap-1">
                                                Win Rate
                                                <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </TableHead>
                                        <TableHead
                                            className="text-right cursor-pointer hover:bg-muted/50 bg-green-50"
                                            onClick={() => handleSort("total_gp")}
                                        >
                                            <div className="flex items-center justify-end gap-1 font-semibold text-green-700">
                                                Total GP
                                                <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </TableHead>
                                        <TableHead
                                            className="text-right cursor-pointer hover:bg-muted/50"
                                            onClick={() => handleSort("avg_margin")}
                                        >
                                            <div className="flex items-center justify-end gap-1">
                                                Avg Margin
                                                <ArrowUpDown className="h-3 w-3" />
                                            </div>
                                        </TableHead>
                                    </TableRow>
                                </TableHeader>
                                <TableBody>
                                    {sortedUsers.map((user) => (
                                        <TableRow key={user.user_id}>
                                            <TableCell className="font-medium">
                                                {user.full_name || user.username}
                                                {user.full_name && (
                                                    <span className="text-xs text-muted-foreground ml-1">({user.username})</span>
                                                )}
                                            </TableCell>
                                            <TableCell className="text-right">{user.quotes_sent}</TableCell>
                                            <TableCell className="text-right">{user.quotes_won}</TableCell>
                                            <TableCell className="text-right">{user.conversion_rate}%</TableCell>
                                            <TableCell className="text-right font-mono font-semibold text-green-700 bg-green-50/50">
                                                {formatCurrency(user.total_gp)}
                                            </TableCell>
                                            <TableCell className="text-right">{user.avg_margin}%</TableCell>
                                        </TableRow>
                                    ))}
                                    {sortedUsers.length === 0 && (
                                        <TableRow>
                                            <TableCell colSpan={6} className="text-center text-muted-foreground">
                                                No data available for the selected period.
                                            </TableCell>
                                        </TableRow>
                                    )}
                                </TableBody>
                            </Table>
                        </CardContent>
                    </Card>
                </TabsContent>
            </Tabs>
        </div>
    );
}
