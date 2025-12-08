"use client";

import React, { useState, useEffect, useMemo } from "react";
import { Plane, Package, MapPin, Calculator, Loader2, CheckCircle, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { BucketChargeSection } from "@/components/pricing/BucketChargeSection";
import { FreeformLineEditor, getDefaultCurrencyForCountry } from "@/components/pricing/FreeformLineEditor";
import {
    getSpotChargesForQuote,
    saveSpotChargesForQuote,
    calculateSpotCharges,
} from "@/lib/api";
import type {
    SpotChargeLine,
    SpotChargeBucket,
    SpotChargesGrouped,
    SpotChargesCalculateResponse,
    V3QuoteComputeResponse,
} from "@/lib/types";

interface BucketSourcingViewProps {
    quote: V3QuoteComputeResponse;
    onFinalizeSuccess: () => void;
}

interface BucketConfig {
    bucket: SpotChargeBucket;
    title: string;
    icon: React.ReactNode;
    editable: boolean;
    subtotal?: string;
    subtotalNote?: string;
}

/**
 * Determine which buckets should be editable based on shipment context.
 * 
 * Rules:
 * | Direction | Scope | Payment | Buckets to Show |
 * |-----------|-------|---------|-----------------|
 * | Import | Any | Collect | Origin + Freight + Dest |
 * | Import | A2D | Prepaid | Dest only |
 * | Export | D2A | Prepaid | None (auto-rated) |
 * | Export | D2D (DAP) | Prepaid | Dest only |
 * | Export | D2A | Collect | Origin (if missing) |
 */
function getEditableBuckets(quote: V3QuoteComputeResponse): Set<SpotChargeBucket> {
    const direction = quote.shipment_type; // IMPORT or EXPORT
    const paymentTerm = quote.payment_term; // PREPAID or COLLECT
    const scope = quote.service_scope; // D2D, A2D, D2A

    if (direction === "IMPORT") {
        if (paymentTerm === "COLLECT") {
            // Import Collect - all buckets editable
            return new Set(["ORIGIN", "FREIGHT", "DESTINATION"]);
        }
        if (paymentTerm === "PREPAID" && scope === "A2D") {
            // Import Prepaid A2D - destination only
            return new Set(["DESTINATION"]);
        }
        // Default for other imports
        return new Set(["ORIGIN", "FREIGHT", "DESTINATION"]);
    }

    if (direction === "EXPORT") {
        if (paymentTerm === "PREPAID") {
            if (scope === "D2D") {
                // Export Prepaid D2D (DAP) - destination only
                return new Set(["DESTINATION"]);
            }
            if (scope === "D2A") {
                // Export Prepaid D2A - none (auto-rated)
                return new Set();
            }
        }
        if (paymentTerm === "COLLECT" && scope === "D2A") {
            // Export Collect D2A - origin only if missing
            return new Set(["ORIGIN"]);
        }
        // Default for other exports
        return new Set(["DESTINATION"]);
    }

    // Default fallback
    return new Set(["ORIGIN", "FREIGHT", "DESTINATION"]);
}

/**
 * Get subtotals for non-editable buckets from quote lines.
 */
function getBucketSubtotals(quote: V3QuoteComputeResponse): Record<SpotChargeBucket, { amount: string; currency: string }> {
    const lines = quote.latest_version?.lines || [];

    const totals: Record<SpotChargeBucket, { amount: number; currency: string }> = {
        ORIGIN: { amount: 0, currency: "PGK" },
        FREIGHT: { amount: 0, currency: "PGK" },
        DESTINATION: { amount: 0, currency: "PGK" },
    };

    for (const line of lines) {
        const leg = line.service_component?.leg;
        const sellPgk = parseFloat(line.sell_pgk) || 0;

        if (leg === "ORIGIN") {
            totals.ORIGIN.amount += sellPgk;
        } else if (leg === "MAIN" || leg === "FREIGHT") {
            totals.FREIGHT.amount += sellPgk;
        } else if (leg === "DESTINATION") {
            totals.DESTINATION.amount += sellPgk;
        }
    }

    return {
        ORIGIN: { amount: totals.ORIGIN.amount.toFixed(2), currency: "PGK" },
        FREIGHT: { amount: totals.FREIGHT.amount.toFixed(2), currency: "PGK" },
        DESTINATION: { amount: totals.DESTINATION.amount.toFixed(2), currency: "PGK" },
    };
}

/**
 * Extract destination country code from quote.
 * Handles formats like:
 * - "Brisbane (BNE), AU"
 * - "BNE"
 * - "Port Moresby (POM), PG"
 */
function getDestinationCountryCode(quote: V3QuoteComputeResponse): string | undefined {
    const destLocation = quote.destination_location;
    if (typeof destLocation !== "string" || !destLocation) return undefined;

    // Try to extract country code from end of string (e.g., ", AU" or ", PG")
    const countryMatch = destLocation.match(/,\s*([A-Z]{2})\s*$/i);
    if (countryMatch) {
        return countryMatch[1].toUpperCase();
    }

    // Try to extract IATA code in parentheses (e.g., "(BNE)")
    const iataMatch = destLocation.match(/\(([A-Z]{3})\)/i);
    const iataCode = iataMatch?.[1]?.toUpperCase();

    // Fallback: if the whole string is just an IATA code
    const plainIata = destLocation.length === 3 ? destLocation.toUpperCase() : iataCode;

    if (plainIata) {
        // Common airport codes to country mapping
        const airportCountryMap: Record<string, string> = {
            // Australia
            BNE: "AU", SYD: "AU", MEL: "AU", PER: "AU", ADL: "AU", CBR: "AU",
            DRW: "AU", CNS: "AU", OOL: "AU", HBA: "AU",
            // USA
            LAX: "US", JFK: "US", SFO: "US", ORD: "US", MIA: "US", DFW: "US",
            ATL: "US", SEA: "US", DEN: "US",
            // China
            PVG: "CN", PEK: "CN", CAN: "CN", SZX: "CN", CTU: "CN",
            // Hong Kong
            HKG: "HK",
            // Singapore
            SIN: "SG",
            // New Zealand
            AKL: "NZ", WLG: "NZ", CHC: "NZ",
            // UK
            LHR: "GB", LGW: "GB", MAN: "GB", STN: "GB",
            // PNG
            POM: "PG", LAE: "PG",
            // Japan
            NRT: "JP", HND: "JP", KIX: "JP",
            // South Korea
            ICN: "KR", GMP: "KR",
            // Thailand
            BKK: "TH", DMK: "TH",
            // Malaysia
            KUL: "MY",
            // Indonesia
            CGK: "ID", DPS: "ID",
            // Philippines
            MNL: "PH", CEB: "PH",
            // India
            DEL: "IN", BOM: "IN", BLR: "IN",
            // UAE
            DXB: "AE", AUH: "AE",
        };
        return airportCountryMap[plainIata];
    }

    return undefined;
}


export function BucketSourcingView({ quote, onFinalizeSuccess }: BucketSourcingViewProps) {
    const [charges, setCharges] = useState<SpotChargesGrouped>({
        ORIGIN: [],
        FREIGHT: [],
        DESTINATION: [],
    });
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [calculating, setCalculating] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [calcResult, setCalcResult] = useState<SpotChargesCalculateResponse | null>(null);
    const [editorOpen, setEditorOpen] = useState(false);
    const [editingBucket, setEditingBucket] = useState<SpotChargeBucket>("DESTINATION");
    const [editingLine, setEditingLine] = useState<SpotChargeLine | null>(null);

    // Determine which buckets are editable and auto-rated subtotals
    const editableBuckets = useMemo(() => getEditableBuckets(quote), [quote]);
    const bucketSubtotals = useMemo(() => getBucketSubtotals(quote), [quote]);
    const destinationCountryCode = useMemo(() => getDestinationCountryCode(quote), [quote]);

    // Build bucket config with visibility rules
    const bucketConfigs: BucketConfig[] = useMemo(() => {
        return [
            {
                bucket: "ORIGIN" as SpotChargeBucket,
                title: "Origin Charges",
                icon: <MapPin className="h-5 w-5" />,
                editable: editableBuckets.has("ORIGIN"),
                subtotal: bucketSubtotals.ORIGIN.amount,
                subtotalNote: editableBuckets.has("ORIGIN") ? undefined : "auto-rated",
            },
            {
                bucket: "FREIGHT" as SpotChargeBucket,
                title: "Freight",
                icon: <Plane className="h-5 w-5" />,
                editable: editableBuckets.has("FREIGHT"),
                subtotal: bucketSubtotals.FREIGHT.amount,
                subtotalNote: editableBuckets.has("FREIGHT") ? undefined : "auto-rated",
            },
            {
                bucket: "DESTINATION" as SpotChargeBucket,
                title: "Destination Charges",
                icon: <Package className="h-5 w-5" />,
                editable: editableBuckets.has("DESTINATION"),
                subtotal: bucketSubtotals.DESTINATION.amount,
                subtotalNote: editableBuckets.has("DESTINATION") ? undefined : "auto-rated",
            },
        ];
    }, [editableBuckets, bucketSubtotals]);

    // Flatten all lines for the editor's target line selection
    const allLines = useMemo(() => {
        return [...charges.ORIGIN, ...charges.FREIGHT, ...charges.DESTINATION];
    }, [charges]);

    // Only count editable bucket lines
    const editableLines = useMemo(() => {
        let lines: SpotChargeLine[] = [];
        if (editableBuckets.has("ORIGIN")) lines = [...lines, ...charges.ORIGIN];
        if (editableBuckets.has("FREIGHT")) lines = [...lines, ...charges.FREIGHT];
        if (editableBuckets.has("DESTINATION")) lines = [...lines, ...charges.DESTINATION];
        return lines;
    }, [charges, editableBuckets]);

    // Load existing spot charges
    useEffect(() => {
        const loadCharges = async () => {
            setLoading(true);
            try {
                const response = await getSpotChargesForQuote(quote.id);
                setCharges(response.charges);
            } catch (err) {
                console.error("Failed to load spot charges:", err);
                // Not an error - just means no charges yet
            } finally {
                setLoading(false);
            }
        };
        loadCharges();
    }, [quote.id]);

    const handleAddLine = (bucket: SpotChargeBucket) => {
        setEditingBucket(bucket);
        setEditingLine(null);
        setEditorOpen(true);
    };

    const handleEditLine = (line: SpotChargeLine) => {
        setEditingBucket(line.bucket);
        setEditingLine(line);
        setEditorOpen(true);
    };

    const handleDeleteLine = (bucket: SpotChargeBucket, lineId: string) => {
        setCharges((prev) => ({
            ...prev,
            [bucket]: prev[bucket].filter((l) => l.id !== lineId),
        }));
    };

    const handleSaveLine = (line: SpotChargeLine) => {
        setCharges((prev) => {
            const bucket = line.bucket;
            const existing = prev[bucket];

            if (line.id) {
                // Update existing line
                return {
                    ...prev,
                    [bucket]: existing.map((l) => (l.id === line.id ? line : l)),
                };
            } else {
                // Add new line with temporary ID
                const newLine = { ...line, id: `temp-${Date.now()}` };
                return {
                    ...prev,
                    [bucket]: [...existing, newLine],
                };
            }
        });
        setEditorOpen(false);
    };

    const handleSaveAndCalculate = async () => {
        setError(null);
        setSaving(true);

        try {
            // Flatten and save all charges
            const allCharges = [...charges.ORIGIN, ...charges.FREIGHT, ...charges.DESTINATION];
            await saveSpotChargesForQuote(quote.id, allCharges);

            // Now calculate
            setCalculating(true);
            const result = await calculateSpotCharges(quote.id);
            setCalcResult(result);

            // Notify parent of success
            onFinalizeSuccess();
        } catch (err) {
            const msg = err instanceof Error ? err.message : "Failed to calculate";
            setError(msg);
        } finally {
            setSaving(false);
            setCalculating(false);
        }
    };

    const hasCharges = editableLines.length > 0 || editableBuckets.size === 0;
    const noEditableBuckets = editableBuckets.size === 0;

    if (loading) {
        return (
            <Card>
                <CardContent className="flex items-center justify-center py-12">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                </CardContent>
            </Card>
        );
    }

    return (
        <div className="space-y-4">
            <Card className="border-amber-200 bg-amber-50/30">
                <CardHeader className="pb-3">
                    <div className="flex items-center gap-3">
                        <div className="p-2 bg-amber-100 rounded-full">
                            <Calculator className="h-5 w-5 text-amber-700" />
                        </div>
                        <div>
                            <CardTitle className="text-lg text-amber-800">
                                Enter Spot Rates by Bucket
                            </CardTitle>
                            <CardDescription>
                                {noEditableBuckets
                                    ? "All charges are auto-rated. Review and finalize."
                                    : "Add charges from the agent quote into the appropriate cost buckets."}
                            </CardDescription>
                        </div>
                    </div>
                </CardHeader>
            </Card>

            {/* Bucket Sections */}
            <div className="space-y-4">
                {bucketConfigs.map(({ bucket, title, icon, editable, subtotal, subtotalNote }) => (
                    editable ? (
                        <BucketChargeSection
                            key={bucket}
                            bucket={bucket}
                            title={title}
                            icon={icon}
                            lines={charges[bucket]}
                            onAddLine={() => handleAddLine(bucket)}
                            onEditLine={handleEditLine}
                            onDeleteLine={(lineId) => handleDeleteLine(bucket, lineId)}
                        />
                    ) : (
                        // Non-editable bucket - show subtotal only
                        <Card key={bucket} className="opacity-60">
                            <CardHeader className="py-3 px-4 flex flex-row items-center justify-between bg-muted/30">
                                <div className="flex items-center gap-3">
                                    <div className="p-1.5 rounded-md bg-muted text-muted-foreground">
                                        {icon}
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <h3 className="font-semibold text-muted-foreground">{title}</h3>
                                        <Lock className="h-3.5 w-3.5 text-muted-foreground" />
                                    </div>
                                </div>
                                <div className="flex items-center gap-2">
                                    <Badge variant="outline" className="bg-background">
                                        {subtotal} PGK
                                    </Badge>
                                    {subtotalNote && (
                                        <span className="text-xs text-muted-foreground">({subtotalNote})</span>
                                    )}
                                </div>
                            </CardHeader>
                        </Card>
                    )
                ))}
            </div>

            {/* Calculation Result */}
            {calcResult && (
                <Card className="border-emerald-200 bg-emerald-50/30">
                    <CardHeader className="pb-3">
                        <div className="flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-emerald-600" />
                            <CardTitle className="text-lg text-emerald-800">
                                Calculation Complete
                            </CardTitle>
                        </div>
                    </CardHeader>
                    <CardContent>
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                            <div>
                                <div className="text-xs text-muted-foreground uppercase">Origin</div>
                                <div className="font-mono font-semibold">
                                    {parseFloat(calcResult.totals.origin_sell_pgk).toFixed(2)} PGK
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground uppercase">Freight</div>
                                <div className="font-mono font-semibold">
                                    {parseFloat(calcResult.totals.freight_sell_pgk).toFixed(2)} PGK
                                </div>
                            </div>
                            <div>
                                <div className="text-xs text-muted-foreground uppercase">Destination</div>
                                <div className="font-mono font-semibold">
                                    {parseFloat(calcResult.totals.destination_sell_pgk).toFixed(2)} PGK
                                </div>
                            </div>
                            <div className="border-l pl-4">
                                <div className="text-xs text-muted-foreground uppercase">Grand Total</div>
                                <div className="font-mono font-bold text-lg">
                                    {parseFloat(calcResult.totals.grand_total_pgk).toFixed(2)} PGK
                                </div>
                                {calcResult.totals.grand_total_fcy && (
                                    <div className="font-mono text-sm text-muted-foreground">
                                        {parseFloat(calcResult.totals.grand_total_fcy).toFixed(2)} {calcResult.quoting_currency}
                                    </div>
                                )}
                            </div>
                        </div>
                        <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                            <Badge variant="outline">CW: {calcResult.chargeable_weight} kg</Badge>
                            <Badge variant="outline">Quote: {calcResult.quoting_currency}</Badge>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Error Alert */}
            {error && (
                <Alert variant="destructive">
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            )}

            {/* Action Buttons */}
            <Card>
                <CardContent className="p-4">
                    <div className="flex items-center justify-between">
                        <div className="text-sm text-muted-foreground">
                            {noEditableBuckets
                                ? "All charges auto-rated — ready to finalize"
                                : editableLines.length > 0
                                    ? `${editableLines.length} charge line${editableLines.length > 1 ? "s" : ""} ready`
                                    : "Add charges to calculate"}
                        </div>
                        <Button
                            size="lg"
                            disabled={(!hasCharges && editableBuckets.size > 0) || saving || calculating}
                            onClick={handleSaveAndCalculate}
                            className="shadow-md"
                        >
                            {(saving || calculating) && (
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                            )}
                            {saving ? "Saving..." : calculating ? "Calculating..." : "Calculate & Finalize"}
                        </Button>
                    </div>
                </CardContent>
            </Card>

            {/* Line Editor Dialog */}
            <FreeformLineEditor
                open={editorOpen}
                onClose={() => setEditorOpen(false)}
                onSave={handleSaveLine}
                bucket={editingBucket}
                existingLine={editingLine}
                existingLines={allLines}
                destinationCountryCode={destinationCountryCode}
            />
        </div>
    );
}
