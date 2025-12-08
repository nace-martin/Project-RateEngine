"use client";

import React, { useEffect, useState } from "react";
import { Loader2, CheckCircle, Plane, Package, MapPin, Lock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { calculateSpotCharges, getQuoteCompute } from "@/lib/api";
import type { SpotChargesCalculateResponse, V3QuoteComputeResponse, QuoteComputeResult } from "@/lib/types";

interface SpotChargeResultDisplayProps {
    quote: V3QuoteComputeResponse;
}

/**
 * Get auto-rated bucket totals from the main pricing engine.
 * This extracts Origin/Freight/Destination totals from rate card charges.
 */
function getAutoRatedBucketTotals(computeResult: QuoteComputeResult | null): {
    origin: number;
    freight: number;
    destination: number;
} {
    if (!computeResult?.sell_lines) {
        return { origin: 0, freight: 0, destination: 0 };
    }

    let origin = 0;
    let freight = 0;
    let destination = 0;

    for (const line of computeResult.sell_lines) {
        const sellPgk = parseFloat(line.sell_pgk || "0");
        const leg = line.leg?.toUpperCase();

        if (leg === "ORIGIN") {
            origin += sellPgk;
        } else if (leg === "MAIN" || leg === "FREIGHT") {
            freight += sellPgk;
        } else if (leg === "DESTINATION") {
            destination += sellPgk;
        }
    }

    return { origin, freight, destination };
}

/**
 * Display component for quotes that have spot charges calculated.
 * Merges spot charges with auto-rated charges from the main pricing engine.
 */
export function SpotChargeResultDisplay({ quote }: SpotChargeResultDisplayProps) {
    const [spotResult, setSpotResult] = useState<SpotChargesCalculateResponse | null>(null);
    const [computeResult, setComputeResult] = useState<QuoteComputeResult | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        const fetchResults = async () => {
            setLoading(true);
            try {
                // Fetch both spot charges and auto-rated charges in parallel
                const [spotCalc, compute] = await Promise.all([
                    calculateSpotCharges(quote.id).catch(() => null),
                    getQuoteCompute(quote.id).catch(() => null),
                ]);
                setSpotResult(spotCalc);
                setComputeResult(compute);
            } catch (err) {
                console.error("Failed to fetch charge results:", err);
                setError("Failed to load charge calculation");
            } finally {
                setLoading(false);
            }
        };
        fetchResults();
    }, [quote.id]);

    if (loading) {
        return (
            <Card>
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                    <span className="ml-2 text-muted-foreground">Loading quote totals...</span>
                </CardContent>
            </Card>
        );
    }

    if (error || (!spotResult && !computeResult)) {
        return (
            <Card className="border-destructive/20">
                <CardContent className="p-6 text-center text-destructive">
                    {error || "No calculation found"}
                </CardContent>
            </Card>
        );
    }

    // Get auto-rated totals from main pricing engine
    const autoRated = getAutoRatedBucketTotals(computeResult);

    // Get spot charge totals (if any)
    const spotOrigin = spotResult ? parseFloat(spotResult.totals.origin_sell_pgk) : 0;
    const spotFreight = spotResult ? parseFloat(spotResult.totals.freight_sell_pgk) : 0;
    const spotDest = spotResult ? parseFloat(spotResult.totals.destination_sell_pgk) : 0;

    // Merge: Use spot if > 0, otherwise use auto-rated
    // For scenarios where user entered spot charges for a bucket, those override auto-rated
    const originTotal = spotOrigin > 0 ? spotOrigin : autoRated.origin;
    const freightTotal = spotFreight > 0 ? spotFreight : autoRated.freight;
    const destTotal = spotDest > 0 ? spotDest : autoRated.destination;

    const grandTotal = originTotal + freightTotal + destTotal;

    // Determine which buckets are from spot vs auto
    const originSource = spotOrigin > 0 ? "spot" : "auto";
    const freightSource = spotFreight > 0 ? "spot" : "auto";
    const destSource = spotDest > 0 ? "spot" : "auto";

    const buckets = [
        {
            key: "origin",
            title: "Origin Charges",
            icon: <MapPin className="h-5 w-5" />,
            color: "text-blue-700",
            bgColor: originSource === "auto" ? "bg-blue-50/50" : "bg-blue-50",
            sellPgk: originTotal,
            source: originSource,
        },
        {
            key: "freight",
            title: "Freight",
            icon: <Plane className="h-5 w-5" />,
            color: "text-purple-700",
            bgColor: freightSource === "auto" ? "bg-purple-50/50" : "bg-purple-50",
            sellPgk: freightTotal,
            source: freightSource,
        },
        {
            key: "destination",
            title: "Destination Charges",
            icon: <Package className="h-5 w-5" />,
            color: "text-green-700",
            bgColor: destSource === "auto" ? "bg-green-50/50" : "bg-green-50",
            sellPgk: destTotal,
            source: destSource,
        },
    ];

    const chargeableWeight = spotResult?.chargeable_weight || "0";
    const quotingCurrency = spotResult?.quoting_currency || computeResult?.totals?.currency || "PGK";

    return (
        <div className="space-y-4">
            {/* Bucket Breakdown */}
            <Card>
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-2">
                        <CheckCircle className="h-5 w-5 text-emerald-600" />
                        <CardTitle className="text-lg">Quote Calculation</CardTitle>
                    </div>
                </CardHeader>
                <CardContent className="space-y-4">
                    {/* Bucket Totals */}
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {buckets.map((bucket) => (
                            <div
                                key={bucket.key}
                                className={`${bucket.bgColor} rounded-lg p-4 border`}
                            >
                                <div className="flex items-center justify-between mb-2">
                                    <div className="flex items-center gap-2">
                                        <span className={bucket.color}>{bucket.icon}</span>
                                        <span className={`font-semibold text-sm ${bucket.color}`}>
                                            {bucket.title}
                                        </span>
                                    </div>
                                    {bucket.source === "auto" && (
                                        <Badge variant="outline" className="text-xs gap-1">
                                            <Lock className="h-3 w-3" />
                                            Auto
                                        </Badge>
                                    )}
                                </div>
                                <div className="font-mono text-xl font-bold">
                                    {bucket.sellPgk.toLocaleString("en-US", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })}{" "}
                                    PGK
                                </div>
                            </div>
                        ))}
                    </div>

                    {/* Grand Total */}
                    <div className="border-t pt-4 mt-4">
                        <div className="flex items-center justify-between">
                            <div>
                                <div className="text-sm text-muted-foreground">Grand Total (PGK)</div>
                                <div className="font-mono text-2xl font-bold text-emerald-700">
                                    {grandTotal.toLocaleString("en-US", {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })}{" "}
                                    PGK
                                </div>
                            </div>
                            {spotResult?.totals.grand_total_fcy && quotingCurrency !== "PGK" && (
                                <div className="text-right">
                                    <div className="text-sm text-muted-foreground">
                                        Quote Currency ({quotingCurrency})
                                    </div>
                                    <div className="font-mono text-xl font-semibold">
                                        {parseFloat(spotResult.totals.grand_total_fcy).toLocaleString("en-US", {
                                            minimumFractionDigits: 2,
                                            maximumFractionDigits: 2,
                                        })}{" "}
                                        {quotingCurrency}
                                    </div>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Metadata */}
                    <div className="flex items-center gap-3 text-xs text-muted-foreground pt-2">
                        <Badge variant="outline">CW: {chargeableWeight} kg</Badge>
                        <Badge variant="outline">Quote Currency: {quotingCurrency}</Badge>
                    </div>
                </CardContent>
            </Card>
        </div>
    );
}
