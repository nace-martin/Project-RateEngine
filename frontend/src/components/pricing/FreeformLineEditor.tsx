"use client";

import React, { useState, useEffect } from "react";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from "@/components/ui/dialog";
import type {
    SpotChargeLine,
    SpotChargeBucket,
    SpotChargeUnitBasis,
    SpotChargePercentAppliesTo,
} from "@/lib/types";

const CURRENCIES = ["USD", "AUD", "SGD", "CNY", "EUR", "GBP", "NZD", "PGK"] as const;

// Removed PER_MAN as requested
const UNIT_BASIS_OPTIONS: { value: SpotChargeUnitBasis; label: string }[] = [
    { value: "PER_SHIPMENT", label: "Per Shipment" },
    { value: "PER_KG", label: "Per KG (rate × chargeable weight)" },
    { value: "PER_AWB", label: "Per AWB" },
    { value: "MINIMUM", label: "Minimum Charge" },
    { value: "PER_HOUR", label: "Per Hour" },
    { value: "PERCENTAGE", label: "Percentage (%)" },
    { value: "OTHER", label: "Other" },
];

const PERCENT_APPLIES_TO_OPTIONS: { value: SpotChargePercentAppliesTo; label: string }[] = [
    { value: "SPECIFIC_LINE", label: "Specific Charge Line" },
    { value: "BUCKET_ORIGIN", label: "Origin Bucket Total" },
    { value: "BUCKET_FREIGHT", label: "Freight Bucket Total" },
    { value: "BUCKET_DESTINATION", label: "Destination Bucket Total" },
    { value: "BUCKET_TOTAL", label: "All Buckets Total" },
];

// Banned generic patterns for description validation
const BANNED_PATTERNS = [
    /^fee$/i, /^fees$/i, /^cost$/i, /^costs$/i, /^charge$/i, /^charges$/i,
    /^ok$/i, /^-$/i, /^\.$/i, /^\?$/i, /^tbd$/i, /^n\/a$/i, /^na$/i,
];

// Description placeholder examples
const DESCRIPTION_PLACEHOLDER = "e.g., Sydney Agent Handling + Documentation";

// Get default currency based on destination country
export function getDefaultCurrencyForCountry(countryCode: string | undefined): string {
    if (!countryCode) return "USD";
    const code = countryCode.toUpperCase();
    switch (code) {
        case "AU": return "AUD";
        case "US": return "USD";
        case "CN": return "CNY";
        case "NZ": return "NZD";
        case "SG": return "SGD";
        case "GB": return "GBP";
        case "PG": return "PGK";
        default: return "USD";
    }
}

// Validate description
function validateDescription(desc: string): { valid: boolean; error?: string } {
    const trimmed = desc.trim();

    if (trimmed.length < 15) {
        return { valid: false, error: "Description too short — please enter at least 15 characters." };
    }

    // Check banned patterns
    for (const pattern of BANNED_PATTERNS) {
        if (pattern.test(trimmed)) {
            return { valid: false, error: "Description too vague — please enter what the agent actually wrote." };
        }
    }

    // Check for single word
    const words = trimmed.split(/\s+/).filter(w => w.length > 0);
    if (words.length < 2) {
        return { valid: false, error: "Please provide more detail — at least 2 words required." };
    }

    return { valid: true };
}

interface FreeformLineEditorProps {
    open: boolean;
    onClose: () => void;
    onSave: (line: SpotChargeLine) => void;
    bucket: SpotChargeBucket;
    existingLine?: SpotChargeLine | null;
    existingLines?: SpotChargeLine[];
    destinationCountryCode?: string;
}

export function FreeformLineEditor({
    open,
    onClose,
    onSave,
    bucket,
    existingLine,
    existingLines = [],
    destinationCountryCode,
}: FreeformLineEditorProps) {
    const isEditing = !!existingLine;

    // Get default currency based on destination
    const defaultCurrency = getDefaultCurrencyForCountry(destinationCountryCode);

    const [description, setDescription] = useState("");
    const [amount, setAmount] = useState("");
    const [minCharge, setMinCharge] = useState("");
    const [currency, setCurrency] = useState<string>(defaultCurrency);
    const [unitBasis, setUnitBasis] = useState<SpotChargeUnitBasis>("PER_SHIPMENT");
    const [percentage, setPercentage] = useState("");
    const [percentAppliesTo, setPercentAppliesTo] = useState<SpotChargePercentAppliesTo>("BUCKET_FREIGHT");
    const [targetLineId, setTargetLineId] = useState<string>("");
    const [notes, setNotes] = useState("");
    const [descriptionError, setDescriptionError] = useState<string | null>(null);

    const isPerKg = unitBasis === "PER_KG";

    // Check if currency is unusual for destination
    const isUnusualCurrency = currency !== defaultCurrency && currency !== "PGK";

    // Reset form when dialog opens/closes or existing line changes
    useEffect(() => {
        if (existingLine) {
            setDescription(existingLine.description);
            setAmount(existingLine.amount || "");
            setMinCharge(existingLine.min_charge || "");
            setCurrency(existingLine.currency);
            setUnitBasis(existingLine.unit_basis);
            setPercentage(existingLine.percentage || "");
            setPercentAppliesTo(existingLine.percent_applies_to || "BUCKET_FREIGHT");
            setTargetLineId(existingLine.target_line_id || "");
            setNotes(existingLine.notes || "");
            setDescriptionError(null);
        } else {
            setDescription("");
            setAmount("");
            setMinCharge("");
            setCurrency(defaultCurrency);
            setUnitBasis("PER_SHIPMENT");
            setPercentage("");
            setPercentAppliesTo("BUCKET_FREIGHT");
            setTargetLineId("");
            setNotes("");
            setDescriptionError(null);
        }
    }, [existingLine, open, defaultCurrency]);

    const isPercentage = unitBasis === "PERCENTAGE";
    const requiresTargetLine = isPercentage && percentAppliesTo === "SPECIFIC_LINE";

    // Available lines for specific line targeting (exclude self if editing)
    const availableTargetLines = existingLines.filter(
        (l) => l.unit_basis !== "PERCENTAGE" && l.id !== existingLine?.id
    );

    const handleDescriptionBlur = () => {
        const result = validateDescription(description);
        setDescriptionError(result.valid ? null : result.error || null);
    };

    const handleSave = () => {
        // Final validation check
        const descResult = validateDescription(description);
        if (!descResult.valid) {
            setDescriptionError(descResult.error || "Invalid description");
            return;
        }

        const line: SpotChargeLine = {
            id: existingLine?.id,
            bucket,
            description,
            amount: isPercentage ? null : amount,
            currency,
            unit_basis: unitBasis,
            min_charge: isPerKg && minCharge ? minCharge : null,
            percentage: isPercentage ? percentage : null,
            percent_applies_to: isPercentage ? percentAppliesTo : null,
            target_line_id: requiresTargetLine ? targetLineId : null,
            notes,
        };
        onSave(line);
        onClose();
    };

    const isValid = () => {
        const descResult = validateDescription(description);
        if (!descResult.valid) return false;

        if (isPercentage) {
            if (!percentage || parseFloat(percentage) <= 0) return false;
            if (requiresTargetLine && !targetLineId) return false;
        } else {
            if (!amount || parseFloat(amount) < 0) return false;
        }
        return true;
    };

    return (
        <Dialog open={open} onOpenChange={onClose}>
            <DialogContent className="sm:max-w-[500px]">
                <DialogHeader>
                    <DialogTitle>
                        {isEditing ? "Edit Charge Line" : "Add Charge Line"}
                    </DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    {/* Description */}
                    <div className="space-y-2">
                        <Label htmlFor="description">Description *</Label>
                        <Input
                            id="description"
                            placeholder={DESCRIPTION_PLACEHOLDER}
                            value={description}
                            onChange={(e) => {
                                setDescription(e.target.value);
                                if (descriptionError) setDescriptionError(null);
                            }}
                            onBlur={handleDescriptionBlur}
                            className={descriptionError ? "border-destructive" : ""}
                        />
                        {descriptionError && (
                            <p className="text-sm text-destructive">{descriptionError}</p>
                        )}
                        <p className="text-xs text-muted-foreground">
                            Examples: &quot;Brisbane Delivery to 4000 CBD&quot;, &quot;Destination Terminal Fee (DXB)&quot;
                        </p>
                    </div>

                    {/* Unit Basis */}
                    <div className="space-y-2">
                        <Label>Unit Basis *</Label>
                        <Select value={unitBasis} onValueChange={(v) => setUnitBasis(v as SpotChargeUnitBasis)}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {UNIT_BASIS_OPTIONS.map((opt) => (
                                    <SelectItem key={opt.value} value={opt.value}>
                                        {opt.label}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Amount + Currency (for non-percentage) */}
                    {!isPercentage && (
                        <div className="grid grid-cols-2 gap-3">
                            <div className="space-y-2">
                                <Label htmlFor="amount">Amount *</Label>
                                <Input
                                    id="amount"
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    placeholder="0.00"
                                    value={amount}
                                    onChange={(e) => setAmount(e.target.value)}
                                />
                            </div>
                            <div className="space-y-2">
                                <Label className="flex items-center gap-1">
                                    Currency
                                    {isUnusualCurrency && (
                                        <AlertTriangle className="h-3.5 w-3.5 text-amber-500" />
                                    )}
                                </Label>
                                <Select value={currency} onValueChange={setCurrency}>
                                    <SelectTrigger className={isUnusualCurrency ? "border-amber-400" : ""}>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {CURRENCIES.map((c) => (
                                            <SelectItem key={c} value={c}>
                                                {c}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                                {isUnusualCurrency && (
                                    <p className="text-xs text-amber-600 flex items-center gap-1">
                                        <AlertTriangle className="h-3 w-3" />
                                        Unusual for this destination
                                    </p>
                                )}
                            </div>
                        </div>
                    )}

                    {/* Minimum Charge (for PER_KG only) */}
                    {isPerKg && !isPercentage && (
                        <div className="space-y-2">
                            <Label htmlFor="minCharge">Minimum Charge (optional)</Label>
                            <div className="flex items-center gap-2">
                                <Input
                                    id="minCharge"
                                    type="number"
                                    step="0.01"
                                    min="0"
                                    placeholder="e.g., 50.00"
                                    value={minCharge}
                                    onChange={(e) => setMinCharge(e.target.value)}
                                    className="flex-1"
                                />
                                <span className="text-sm text-muted-foreground">{currency}</span>
                            </div>
                            <p className="text-xs text-muted-foreground">
                                If rate × weight is less than this, the minimum will apply.
                            </p>
                        </div>
                    )}

                    {/* Percentage fields */}
                    {isPercentage && (
                        <>
                            <div className="grid grid-cols-2 gap-3">
                                <div className="space-y-2">
                                    <Label htmlFor="percentage">Percentage *</Label>
                                    <div className="relative">
                                        <Input
                                            id="percentage"
                                            type="number"
                                            step="0.01"
                                            min="0"
                                            placeholder="20"
                                            value={percentage}
                                            onChange={(e) => setPercentage(e.target.value)}
                                        />
                                        <span className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground">
                                            %
                                        </span>
                                    </div>
                                </div>
                                <div className="space-y-2">
                                    <Label>Applies To *</Label>
                                    <Select
                                        value={percentAppliesTo}
                                        onValueChange={(v) => setPercentAppliesTo(v as SpotChargePercentAppliesTo)}
                                    >
                                        <SelectTrigger>
                                            <SelectValue />
                                        </SelectTrigger>
                                        <SelectContent>
                                            {PERCENT_APPLIES_TO_OPTIONS.map((opt) => (
                                                <SelectItem key={opt.value} value={opt.value}>
                                                    {opt.label}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                </div>
                            </div>

                            {/* Target Line Selector */}
                            {requiresTargetLine && (
                                <div className="space-y-2">
                                    <Label>Target Charge Line *</Label>
                                    {availableTargetLines.length === 0 ? (
                                        <p className="text-sm text-amber-600">
                                            No charge lines available. Add a non-percentage charge first.
                                        </p>
                                    ) : (
                                        <Select value={targetLineId} onValueChange={setTargetLineId}>
                                            <SelectTrigger>
                                                <SelectValue placeholder="Select a charge line..." />
                                            </SelectTrigger>
                                            <SelectContent>
                                                {availableTargetLines.map((l) => (
                                                    <SelectItem key={l.id} value={l.id || ""}>
                                                        {l.description} ({l.amount} {l.currency})
                                                    </SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                    )}
                                </div>
                            )}
                        </>
                    )}

                    {/* Notes */}
                    <div className="space-y-2">
                        <Label htmlFor="notes">Notes (optional)</Label>
                        <Textarea
                            id="notes"
                            placeholder="Any additional notes about this charge..."
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            rows={2}
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>
                        Cancel
                    </Button>
                    <Button onClick={handleSave} disabled={!isValid()}>
                        {isEditing ? "Update" : "Add"} Charge
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
