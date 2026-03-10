import React, { useEffect, useState } from "react";
import { Users, Repeat, TrendingUp, UserMinus } from "lucide-react"; // Icons
import { getTier1Stats } from "@/lib/api";
import type { Tier1Stats } from "@/lib/types";
import { KPICard } from "@/components/KPICard";
import { Skeleton } from "@/components/ui/skeleton";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardHeader } from "@/components/ui/card";

interface Tier1StatsRowProps {
    timeframe: "weekly" | "monthly" | "ytd";
}

export function Tier1StatsRow({ timeframe }: Tier1StatsRowProps) {
    const [stats, setStats] = useState<Tier1Stats | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        let isMounted = true;
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                // Calculate dates based on timeframe
                const today = new Date();
                const start = new Date(today);

                if (timeframe === 'weekly') {
                    start.setDate(today.getDate() - 6);
                } else if (timeframe === 'monthly') {
                    start.setDate(1); // 1st of current month
                } else if (timeframe === 'ytd') {
                    start.setMonth(0, 1); // Jan 1st
                }

                const startDateStr = start.toISOString().split('T')[0];
                const endDateStr = today.toISOString().split('T')[0];

                const data = await getTier1Stats(startDateStr, endDateStr);

                if (isMounted) {
                    setStats(data);
                }
            } catch (err) {
                if (isMounted) {
                    setError(err instanceof Error ? err.message : "Failed to load customer stats");
                }
            } finally {
                if (isMounted) {
                    setLoading(false);
                }
            }
        };

        fetchData();

        return () => {
            isMounted = false;
        };
    }, [timeframe]);


    if (error) {
        return (
            <Alert variant="destructive" className="mb-6">
                <AlertDescription>Error loading Tier-1 Stats: {error}</AlertDescription>
            </Alert>
        );
    }

    return (
        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {/* 1. Active Customers */}
            <KPICard
                title="Active Customers"
                value={loading ? <Skeleton className="h-9 w-16" /> : stats?.active_customers ?? 0}
                icon={Users}
                status="neutral"
                description={loading ? undefined : `${timeframe === 'ytd' ? 'Year to date' : timeframe === 'weekly' ? 'Last 7 days' : 'This month'}`}
            />

            {/* 2. Repeat Customers % */}
            <KPICard
                title="Repeat Customers"
                value={loading ? <Skeleton className="h-9 w-16" /> : `${stats?.repeat_customers_pct ?? 0}%`}
                icon={Repeat}
                status={stats && stats.repeat_customers_pct > 50 ? "success" : "neutral"}
                description="Customers with 2+ quotes"
            />

            {/* 3. Top 5 Pipeline (Not using KPICard, distinct list layout) */}
            <Card className="col-span-1 border-slate-200 bg-white border-l-4 border-l-blue-500 shadow-sm overflow-hidden">
                <CardHeader className="p-4 pb-2">
                    <div className="flex justify-between items-start">
                        <p className="text-sm font-medium text-slate-500 uppercase tracking-wider">
                            Top 5 Pipeline (MTD)
                        </p>
                        <div className="p-1.5 rounded-lg bg-blue-50 text-blue-600">
                            <TrendingUp className="h-4 w-4" />
                        </div>
                    </div>
                </CardHeader>
                <CardContent className="p-2 pt-0">
                    {loading ? (
                        <div className="space-y-2 p-2">
                            <Skeleton className="h-4 w-full" />
                            <Skeleton className="h-4 w-full" />
                            <Skeleton className="h-4 w-full" />
                        </div>
                    ) : (
                        <div className="divide-y divide-slate-100">
                            {stats?.top_customers.length === 0 ? (
                                <p className="text-sm text-slate-400 py-4 text-center">No active pipeline this month</p>
                            ) : (
                                stats?.top_customers.map((c, i) => (
                                    <div key={i} className="flex justify-between items-center py-2 px-2 hover:bg-slate-50 rounded text-sm">
                                        <span className="font-medium text-slate-700 truncate max-w-[120px]" title={c.name}>{c.name}</span>
                                        <span className="text-slate-500 font-mono">PGK {c.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
                                    </div>
                                ))
                            )}
                        </div>
                    )}
                </CardContent>
            </Card>

            {/* 4. Dormant Customers */}
            <KPICard
                title="Dormant Customers"
                value="" // Custom Content
                icon={UserMinus}
                status="warning"
                className="flex flex-col"
            >
                <div className="mt-[-1rem]">
                    {loading ? (
                        <div className="flex gap-2">
                            <Skeleton className="h-12 w-full" />
                        </div>
                    ) : (
                        <div className="grid grid-cols-3 gap-2 text-center">
                            <div className="bg-slate-50 rounded p-2 border border-slate-100">
                                <div className="text-xl font-bold text-slate-700">{stats?.dormant_customers["30d"] ?? 0}</div>
                                <div className="text-[10px] text-slate-500 uppercase font-medium">30 Days</div>
                            </div>
                            <div className="bg-amber-50 rounded p-2 border border-amber-100">
                                <div className="text-xl font-bold text-amber-700">{stats?.dormant_customers["60d"] ?? 0}</div>
                                <div className="text-[10px] text-amber-600 uppercase font-medium">60 Days</div>
                            </div>
                            <div className="bg-red-50 rounded p-2 border border-red-100">
                                <div className="text-xl font-bold text-red-700">{stats?.dormant_customers["90d"] ?? 0}</div>
                                <div className="text-[10px] text-red-600 uppercase font-medium">90+ Days</div>
                            </div>
                        </div>
                    )}
                </div>
            </KPICard>
        </div>
    );
}
