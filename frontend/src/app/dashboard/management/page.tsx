"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import {
    getDashboardReports,
    getSalesPerformanceReports,
    DashboardReportData,
    SalesPerformanceData
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
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Loader2, TrendingUp, BarChart3, Users, DollarSign, ArrowLeft } from "lucide-react";

export default function ManagementDashboardPage() {
    const { user } = useAuth();
    const { isManager, isAdmin, isFinance } = usePermissions();
    const router = useRouter();

    const [reportData, setReportData] = useState<DashboardReportData | null>(null);
    const [performanceData, setPerformanceData] = useState<SalesPerformanceData[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const hasAccess = isManager || isAdmin || isFinance;

    useEffect(() => {
        if (!user) return;

        if (!hasAccess) {
            // Optional: Redirect or just show unauthorized message
            // router.push('/dashboard'); 
            return;
        }

        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [dashData, perfData] = await Promise.all([
                    getDashboardReports(),
                    getSalesPerformanceReports(),
                ]);
                setReportData(dashData);
                setPerformanceData(perfData);
            } catch (err: unknown) {
                const message = err instanceof Error ? err.message : "Failed to load reports.";
                setError(message);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [user, hasAccess]);

    if (!user) return null; // or loading

    if (!hasAccess) {
        return (
            <div className="container mx-auto p-8">
                <Alert variant="destructive">
                    <AlertTitle>Access Denied</AlertTitle>
                    <AlertDescription>You do not have permission to view this page.</AlertDescription>
                </Alert>
                <Button className="mt-4" onClick={() => router.push('/dashboard')}>
                    Back to Dashboard
                </Button>
            </div>
        );
    }

    if (loading) {
        return (
            <div className="flex items-center justify-center p-12">
                <Loader2 className="mr-2 h-8 w-8 animate-spin" />
                <span>Loading management reports...</span>
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

    // Helper to format currency
    const formatCurrency = (amount: number) => {
        return new Intl.NumberFormat('en-PG', { style: 'currency', currency: 'PGK', maximumFractionDigits: 0 }).format(amount);
    };

    return (
        <div className="container mx-auto p-4 max-w-7xl space-y-8">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-3xl font-bold tracking-tight">Management Overview</h1>
                    <p className="text-muted-foreground">High-level insights on revenue, volume, and team performance.</p>
                </div>
                <Button variant="outline" onClick={() => router.push('/dashboard')}>
                    <ArrowLeft className="mr-2 h-4 w-4" />
                    Back to Dashboard
                </Button>
            </div>

            {/* Top Cards */}
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Revenue</CardTitle>
                        <DollarSign className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{formatCurrency(reportData?.total_revenue || 0)}</div>
                        <p className="text-xs text-muted-foreground">Accepted & Finalized Quotes</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Total Quotes</CardTitle>
                        <BarChart3 className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{reportData?.conversion.total}</div>
                        <p className="text-xs text-muted-foreground">All time volume</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Drafts (Pipeline)</CardTitle>
                        <TrendingUp className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">{reportData?.conversion.drafts}</div>
                        <p className="text-xs text-muted-foreground">Currently active in pipeline</p>
                    </CardContent>
                </Card>
                <Card>
                    <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                        <CardTitle className="text-sm font-medium">Conversion Rate</CardTitle>
                        <Users className="h-4 w-4 text-muted-foreground" />
                    </CardHeader>
                    <CardContent>
                        <div className="text-2xl font-bold">
                            {reportData?.conversion.total ?
                                ((reportData.conversion.finalized / reportData.conversion.total) * 100).toFixed(1)
                                : 0}%
                        </div>
                        <p className="text-xs text-muted-foreground">Finalized/Total</p>
                    </CardContent>
                </Card>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-7">
                {/* Sales Performance */}
                <Card className="col-span-4">
                    <CardHeader>
                        <CardTitle>Sales Performance</CardTitle>
                        <CardDescription>User performance based on revenue generation.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>User</TableHead>
                                    <TableHead className="text-right">Total Quotes</TableHead>
                                    <TableHead className="text-right">Converted</TableHead>
                                    <TableHead className="text-right">Revenue (PGK)</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {performanceData.map((userPerf) => (
                                    <TableRow key={userPerf.created_by__username}>
                                        <TableCell className="font-medium">
                                            {userPerf.created_by__first_name} {userPerf.created_by__last_name}
                                            <span className="text-xs text-muted-foreground ml-1">({userPerf.created_by__username})</span>
                                        </TableCell>
                                        <TableCell className="text-right">{userPerf.total_quotes}</TableCell>
                                        <TableCell className="text-right">{userPerf.converted_quotes}</TableCell>
                                        <TableCell className="text-right">{formatCurrency(userPerf.total_revenue || 0)}</TableCell>
                                    </TableRow>
                                ))}
                                {performanceData.length === 0 && (
                                    <TableRow>
                                        <TableCell colSpan={4} className="text-center text-muted-foreground">No data available.</TableCell>
                                    </TableRow>
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                {/* Volume by Mode */}
                <Card className="col-span-3">
                    <CardHeader>
                        <CardTitle>Volume by Mode</CardTitle>
                        <CardDescription>Distribution of quotes across transport modes.</CardDescription>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Mode</TableHead>
                                    <TableHead className="text-right">Count</TableHead>
                                    <TableHead className="text-right">Revenue</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {reportData?.volume_by_mode.map((modeData) => (
                                    <TableRow key={modeData.mode}>
                                        <TableCell className="font-medium">{modeData.mode}</TableCell>
                                        <TableCell className="text-right">{modeData.count}</TableCell>
                                        <TableCell className="text-right">{formatCurrency(modeData.revenue || 0)}</TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>
            </div>
        </div>
    );
}
