"use client";

import React, { useState } from "react";
import { Trash2, Edit2, Plus, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { SpotChargeLine, SpotChargeBucket } from "@/lib/types";

interface BucketChargeSectionProps {
    bucket: SpotChargeBucket;
    title: string;
    icon: React.ReactNode;
    lines: SpotChargeLine[];
    onAddLine: () => void;
    onEditLine: (line: SpotChargeLine) => void;
    onDeleteLine: (lineId: string) => void;
    className?: string;
}

const BUCKET_COLORS: Record<SpotChargeBucket, { bg: string; border: string; text: string }> = {
    ORIGIN: { bg: "bg-blue-50", border: "border-blue-200", text: "text-blue-700" },
    FREIGHT: { bg: "bg-purple-50", border: "border-purple-200", text: "text-purple-700" },
    DESTINATION: { bg: "bg-green-50", border: "border-green-200", text: "text-green-700" },
};

const UNIT_BASIS_LABELS: Record<string, string> = {
    PER_KG: "/ kg",
    PER_SHIPMENT: "/ shipment",
    PER_AWB: "/ AWB",
    MINIMUM: "min",
    PER_HOUR: "/ hr",
    PER_MAN: "/ man",
    PERCENTAGE: "%",
    OTHER: "",
};

export function BucketChargeSection({
    bucket,
    title,
    icon,
    lines,
    onAddLine,
    onEditLine,
    onDeleteLine,
    className = "",
}: BucketChargeSectionProps) {
    const [isExpanded, setIsExpanded] = useState(true);
    const colors = BUCKET_COLORS[bucket];

    // Calculate bucket total (simple sum - PER_KG and PERCENTAGE calculated on backend)
    const hasDynamicLines = lines.some(
        (line) => line.unit_basis === "PERCENTAGE" || line.unit_basis === "PER_KG"
    );

    // Group by currency for display (exclude dynamic lines)
    const currencyTotals = lines.reduce<Record<string, number>>((acc, line) => {
        // Skip percentage and per-kg lines - they're calculated on backend
        if (line.unit_basis === "PERCENTAGE" || line.unit_basis === "PER_KG") return acc;
        const currency = line.currency || "PGK";
        acc[currency] = (acc[currency] || 0) + parseFloat(line.amount || "0");
        return acc;
    }, {});

    return (
        <Card className={`${colors.border} ${className}`}>
            <CardHeader
                className={`${colors.bg} cursor-pointer flex flex-row items-center justify-between py-3 px-4`}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex items-center gap-3">
                    <div className={`p-1.5 rounded-md ${colors.text} bg-white/50`}>
                        {icon}
                    </div>
                    <div>
                        <h3 className={`font-semibold ${colors.text}`}>{title}</h3>
                        <p className="text-xs text-muted-foreground">
                            {lines.length} {lines.length === 1 ? "charge" : "charges"}
                        </p>
                    </div>
                </div>
                <div className="flex items-center gap-3">
                    {Object.entries(currencyTotals).map(([currency, total]) => (
                        <Badge key={currency} variant="outline" className={`${colors.bg} ${colors.text}`}>
                            {total.toFixed(2)} {currency}
                        </Badge>
                    ))}
                    {hasDynamicLines && (
                        <span className="text-xs text-muted-foreground italic">
                            + per-kg/% lines
                        </span>
                    )}
                    {isExpanded ? (
                        <ChevronUp className="h-5 w-5 text-muted-foreground" />
                    ) : (
                        <ChevronDown className="h-5 w-5 text-muted-foreground" />
                    )}
                </div>
            </CardHeader>

            {isExpanded && (
                <CardContent className="p-4 space-y-3">
                    {lines.length === 0 ? (
                        <div className="text-center py-6 text-muted-foreground">
                            <p className="text-sm">No charges added yet</p>
                            <Button
                                variant="outline"
                                size="sm"
                                className="mt-2"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onAddLine();
                                }}
                            >
                                <Plus className="h-4 w-4 mr-1" />
                                Add Charge
                            </Button>
                        </div>
                    ) : (
                        <>
                            <div className="space-y-2">
                                {lines.map((line) => (
                                    <div
                                        key={line.id || line.description}
                                        className="flex items-center justify-between p-3 rounded-lg bg-muted/30 hover:bg-muted/50 transition-colors"
                                    >
                                        <div className="flex-1">
                                            <div className="font-medium text-sm">{line.description}</div>
                                            <div className="text-xs text-muted-foreground mt-0.5">
                                                {line.unit_basis === "PERCENTAGE" ? (
                                                    <span>
                                                        {line.percentage}% of{" "}
                                                        {line.percent_applies_to?.replace("BUCKET_", "").replace("_", " ").toLowerCase() ||
                                                            "specific line"}
                                                    </span>
                                                ) : (
                                                    <span>
                                                        {line.amount} {line.currency}{" "}
                                                        {UNIT_BASIS_LABELS[line.unit_basis] || ""}
                                                    </span>
                                                )}
                                                {line.notes && (
                                                    <span className="ml-2 italic">— {line.notes}</span>
                                                )}
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-1">
                                            <Badge variant="secondary" className="text-xs">
                                                {line.unit_basis === "PERCENTAGE"
                                                    ? `${line.percentage}%`
                                                    : `${line.amount} ${line.currency}`}
                                            </Badge>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-7 w-7 p-0"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onEditLine(line);
                                                }}
                                            >
                                                <Edit2 className="h-3.5 w-3.5" />
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    if (line.id) onDeleteLine(line.id);
                                                }}
                                            >
                                                <Trash2 className="h-3.5 w-3.5" />
                                            </Button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            <Button
                                variant="outline"
                                size="sm"
                                className="w-full mt-2"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    onAddLine();
                                }}
                            >
                                <Plus className="h-4 w-4 mr-1" />
                                Add Charge Line
                            </Button>
                        </>
                    )}
                </CardContent>
            )}
        </Card>
    );
}
