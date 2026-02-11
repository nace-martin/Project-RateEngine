"use client";
import { CheckCircle, Plane, Package, MapPin, Lock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { V3QuoteComputeResponse } from "@/lib/types";

interface SpotChargeResultDisplayProps {
    quote: V3QuoteComputeResponse;
}

/**
 * Display component for quotes that have spot charges calculated.
 * Merges spot charges with auto-rated charges from the main pricing engine.
 */
export function SpotChargeResultDisplay({ quote }: SpotChargeResultDisplayProps) {
    const lines = quote.latest_version?.lines || [];
    if (!lines.length) {
        return (
            <Card className="border-destructive/20">
                <CardContent className="p-6 text-center text-destructive">
                    No calculation found
                </CardContent>
            </Card>
        );
    }

    let originTotal = 0;
    let freightTotal = 0;
    let destTotal = 0;

    let originHasSpot = false;
    let freightHasSpot = false;
    let destHasSpot = false;

    for (const line of lines) {
        const sellPgk = parseFloat(line.sell_pgk || "0");
        const leg = line.leg?.toUpperCase();
        const isSpot = !!quote.spot_negotiation?.id && (
            line.cost_source === "SPOT Envelope" || !!line.cost_source_description
        );

        if (leg === "ORIGIN") {
            originTotal += sellPgk;
            originHasSpot = originHasSpot || isSpot;
        } else if (leg === "MAIN" || leg === "FREIGHT") {
            freightTotal += sellPgk;
            freightHasSpot = freightHasSpot || isSpot;
        } else if (leg === "DESTINATION") {
            destTotal += sellPgk;
            destHasSpot = destHasSpot || isSpot;
        }
    }

    const grandTotal = originTotal + freightTotal + destTotal;

    const originSource = originHasSpot ? "spot" : "auto";
    const freightSource = freightHasSpot ? "spot" : "auto";
    const destSource = destHasSpot ? "spot" : "auto";

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

    const quotingCurrency = quote.latest_version?.totals?.currency || "PGK";
    const chargeableWeight = quote.latest_version?.total_weight_kg?.toString() || "0";

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
                            {quote.latest_version?.totals?.total_sell_fcy && quotingCurrency !== "PGK" && (
                                <div className="text-right">
                                    <div className="text-sm text-muted-foreground">
                                        Quote Currency ({quotingCurrency})
                                    </div>
                                    <div className="font-mono text-xl font-semibold">
                                        {parseFloat(quote.latest_version.totals.total_sell_fcy).toLocaleString("en-US", {
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
