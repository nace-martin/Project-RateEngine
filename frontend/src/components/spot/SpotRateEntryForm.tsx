"use client";

/**
 * SpotRateEntryForm - Form for entering SPOT rate charge lines
 * 
 * Features:
 * - Bucket-based organization (Airfreight, Origin, Destination)
 * - Primary airfreight line enforcement
 * - Source reference required per line
 */

import { useState } from "react";
import { Plus, Trash2, AlertTriangle, DollarSign } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { SPEChargeLine, SPEChargeBucket, SPEChargeUnit } from "@/lib/spot-types";

interface SpotRateEntryFormProps {
    onSubmit: (charges: Omit<SPEChargeLine, 'id'>[]) => Promise<void>;
    isLoading?: boolean;
    initialCharges?: SPEChargeLine[];
}

interface ChargeLineInput {
    tempId: string;
    code: string;
    description: string;
    amount: string;
    currency: "USD" | "AUD" | "PGK";
    unit: SPEChargeUnit;
    bucket: SPEChargeBucket;
    is_primary_cost: boolean;
    conditional: boolean;
    source_reference: string;
}

const CHARGE_BUCKETS: { id: SPEChargeBucket; label: string; color: string }[] = [
    { id: "airfreight", label: "Airfreight", color: "bg-blue-50 border-blue-200" },
    { id: "origin_charges", label: "Origin Charges", color: "bg-emerald-50 border-emerald-200" },
    { id: "destination_charges", label: "Destination Charges", color: "bg-amber-50 border-amber-200" },
];

const CHARGE_UNITS: { value: SPEChargeUnit; label: string }[] = [
    { value: "per_kg", label: "Per KG" },
    { value: "flat", label: "Flat" },
    { value: "per_awb", label: "Per AWB" },
    { value: "per_shipment", label: "Per Shipment" },
    { value: "percentage", label: "Percentage" },
];

const createEmptyLine = (bucket: SPEChargeBucket): ChargeLineInput => ({
    tempId: `temp-${Date.now()}-${Math.random()}`,
    code: "",
    description: "",
    amount: "",
    currency: "USD",
    unit: bucket === "airfreight" ? "per_kg" : "flat",
    bucket,
    is_primary_cost: bucket === "airfreight",
    conditional: false,
    source_reference: "",
});

export function SpotRateEntryForm({ onSubmit, isLoading, initialCharges = [] }: SpotRateEntryFormProps) {
    const [lines, setLines] = useState<ChargeLineInput[]>(() => {
        if (initialCharges.length > 0) {
            return initialCharges.map(c => ({
                tempId: c.id || `temp-${Date.now()}-${Math.random()}`,
                code: c.code,
                description: c.description,
                amount: c.amount,
                currency: c.currency,
                unit: c.unit,
                bucket: c.bucket,
                is_primary_cost: c.is_primary_cost,
                conditional: c.conditional,
                source_reference: c.source_reference,
            }));
        }
        // Start with one empty airfreight line
        return [createEmptyLine("airfreight")];
    });

    const [validationError, setValidationError] = useState<string | null>(null);

    // Add new charge line
    const addLine = (bucket: SPEChargeBucket) => {
        setLines([...lines, createEmptyLine(bucket)]);
    };

    // Remove charge line
    const removeLine = (tempId: string) => {
        setLines(lines.filter(l => l.tempId !== tempId));
    };

    // Update charge line field
    const updateLine = (tempId: string, field: keyof ChargeLineInput, value: string | boolean) => {
        setLines(lines.map(l =>
            l.tempId === tempId ? { ...l, [field]: value } : l
        ));
    };

    // Validate and submit
    const handleSubmit = async () => {
        setValidationError(null);

        // Validation 1: At least one line
        if (lines.length === 0) {
            setValidationError("At least one charge line is required.");
            return;
        }

        // Validation 2: Exactly one primary airfreight
        const primaryCount = lines.filter(l => l.is_primary_cost && l.bucket === "airfreight").length;
        if (primaryCount === 0) {
            setValidationError("Exactly one primary airfreight charge is required.");
            return;
        }
        if (primaryCount > 1) {
            setValidationError("Only one primary airfreight charge is allowed.");
            return;
        }

        // Validation 3: All lines have source reference
        const missingSource = lines.find(l => !l.source_reference.trim());
        if (missingSource) {
            setValidationError(`Source reference is required for "${missingSource.description || 'all charges'}".`);
            return;
        }

        // Validation 4: All lines have amount for non-percentage
        const missingAmount = lines.find(l => l.unit !== "percentage" && (!l.amount || parseFloat(l.amount) <= 0));
        if (missingAmount) {
            setValidationError(`Amount is required for "${missingAmount.description || 'all charges'}".`);
            return;
        }

        // Validation 5: All lines have description
        const missingDesc = lines.find(l => !l.description.trim());
        if (missingDesc) {
            setValidationError("Description is required for all charges.");
            return;
        }

        // Convert to API format
        const charges: Omit<SPEChargeLine, 'id'>[] = lines.map(l => ({
            code: l.code || l.description.toUpperCase().replace(/\s+/g, "_").slice(0, 20),
            description: l.description,
            amount: l.amount,
            currency: l.currency,
            unit: l.unit,
            bucket: l.bucket,
            is_primary_cost: l.is_primary_cost,
            conditional: l.conditional,
            source_reference: l.source_reference,
        }));

        await onSubmit(charges);
    };

    // Group lines by bucket
    const getLinesByBucket = (bucket: SPEChargeBucket) =>
        lines.filter(l => l.bucket === bucket);

    return (
        <div className="space-y-6">
            {validationError && (
                <Alert variant="destructive">
                    <AlertTriangle className="h-4 w-4" />
                    <AlertDescription>{validationError}</AlertDescription>
                </Alert>
            )}

            {CHARGE_BUCKETS.map(bucket => (
                <Card key={bucket.id} className={bucket.color}>
                    <CardHeader className="pb-3">
                        <CardTitle className="text-lg flex items-center gap-2">
                            <DollarSign className="h-5 w-5" />
                            {bucket.label}
                        </CardTitle>
                        <CardDescription>
                            {bucket.id === "airfreight" && "Primary cost line required"}
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {getLinesByBucket(bucket.id).map((line) => (
                            <div key={line.tempId} className="p-4 bg-white rounded-lg border space-y-3">
                                <div className="grid grid-cols-12 gap-3">
                                    {/* Description */}
                                    <div className="col-span-4">
                                        <Label className="text-xs">Description</Label>
                                        <Input
                                            placeholder="e.g., Airfreight SYD-POM"
                                            value={line.description}
                                            onChange={(e) => updateLine(line.tempId, "description", e.target.value)}
                                        />
                                    </div>

                                    {/* Amount */}
                                    <div className="col-span-2">
                                        <Label className="text-xs">Amount</Label>
                                        <Input
                                            type="number"
                                            step="0.01"
                                            placeholder="0.00"
                                            value={line.amount}
                                            onChange={(e) => updateLine(line.tempId, "amount", e.target.value)}
                                        />
                                    </div>

                                    {/* Currency */}
                                    <div className="col-span-2">
                                        <Label className="text-xs">Currency</Label>
                                        <Select
                                            value={line.currency}
                                            onValueChange={(v) => updateLine(line.tempId, "currency", v)}
                                        >
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                <SelectItem value="USD">USD</SelectItem>
                                                <SelectItem value="AUD">AUD</SelectItem>
                                                <SelectItem value="PGK">PGK</SelectItem>
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Unit */}
                                    <div className="col-span-2">
                                        <Label className="text-xs">Unit</Label>
                                        <Select
                                            value={line.unit}
                                            onValueChange={(v) => updateLine(line.tempId, "unit", v)}
                                        >
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {CHARGE_UNITS.map(u => (
                                                    <SelectItem key={u.value} value={u.value}>{u.label}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    </div>

                                    {/* Remove */}
                                    <div className="col-span-2 flex items-end">
                                        <Button
                                            variant="ghost"
                                            size="icon"
                                            onClick={() => removeLine(line.tempId)}
                                            className="text-red-500 hover:text-red-700"
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>

                                <div className="grid grid-cols-12 gap-3">
                                    {/* Source Reference */}
                                    <div className="col-span-6">
                                        <Label className="text-xs">Source Reference (required)</Label>
                                        <Input
                                            placeholder="e.g., Email from Cathay 19/12"
                                            value={line.source_reference}
                                            onChange={(e) => updateLine(line.tempId, "source_reference", e.target.value)}
                                        />
                                    </div>

                                    {/* Flags */}
                                    <div className="col-span-6 flex items-end gap-4">
                                        {bucket.id === "airfreight" && (
                                            <div className="flex items-center gap-2">
                                                <Checkbox
                                                    id={`${line.tempId}-primary`}
                                                    checked={line.is_primary_cost}
                                                    onCheckedChange={(v) => updateLine(line.tempId, "is_primary_cost", v === true)}
                                                />
                                                <Label htmlFor={`${line.tempId}-primary`} className="text-xs">
                                                    Primary Cost
                                                </Label>
                                            </div>
                                        )}
                                        <div className="flex items-center gap-2">
                                            <Checkbox
                                                id={`${line.tempId}-conditional`}
                                                checked={line.conditional}
                                                onCheckedChange={(v) => updateLine(line.tempId, "conditional", v === true)}
                                            />
                                            <Label htmlFor={`${line.tempId}-conditional`} className="text-xs">
                                                Conditional
                                            </Label>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        ))}

                        <Button
                            variant="outline"
                            size="sm"
                            onClick={() => addLine(bucket.id)}
                            className="w-full"
                        >
                            <Plus className="h-4 w-4 mr-2" />
                            Add {bucket.label.slice(0, -1)}
                        </Button>
                    </CardContent>
                </Card>
            ))}

            {/* Submit */}
            <Button
                onClick={handleSubmit}
                disabled={isLoading}
                size="lg"
                className="w-full bg-amber-600 hover:bg-amber-700"
            >
                {isLoading ? "Creating..." : "Create SPOT Envelope"}
            </Button>
        </div>
    );
}
