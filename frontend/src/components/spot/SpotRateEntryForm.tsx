"use client";

/**
 * SpotRateEntryForm - Form for entering SPOT rate charge lines
 * Refactored to use reusable components
 */

import { useState, useMemo, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Form } from "@/components/ui/form";

import type { SPEChargeLine, SPEChargeBucket, SPEChargeUnit, ExtractedAssertion } from "@/lib/spot-types";
import { spotFormSchema, type SpotFormInputValues, type SpotFormSubmitValues } from "@/lib/schemas/spotSchema";
import { ChargeBucketSection } from "./ChargeBucketSection";

interface SpotRateEntryFormProps {
    onSubmit: (charges: Omit<SPEChargeLine, 'id'>[]) => Promise<void>;
    isLoading?: boolean;
    initialCharges?: SPEChargeLine[];
    suggestedCharges?: ExtractedAssertion[];
    shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
    serviceScope?: string;
}

const CHARGE_BUCKETS: { id: SPEChargeBucket; label: string }[] = [
    { id: "airfreight", label: "Airfreight" },
    { id: "origin_charges", label: "Origin Charges" },
    { id: "destination_charges", label: "Agent Quoted Charges" },
];

type FormErrorWithMessage = { message?: string };

const getFormErrorMessage = (error: unknown) => {
    if (!error || Array.isArray(error)) return undefined;
    if (typeof error === "object" && "message" in error) {
        const message = (error as FormErrorWithMessage).message;
        return typeof message === "string" ? message : undefined;
    }
    return undefined;
};

export function SpotRateEntryForm({
    onSubmit,
    isLoading,
    initialCharges = [],
    suggestedCharges = [],
    shipmentType = "EXPORT",
    serviceScope = "D2D",
}: SpotRateEntryFormProps) {
    const mapAssertionToCharge = (assertion: ExtractedAssertion): SPEChargeLine | null => {
        const category = assertion.category;
        let bucket: SPEChargeBucket | null = null;
        let code = "MISC";

        if (category === "rate") {
            bucket = "airfreight";
            code = "FREIGHT";
        } else if (category === "origin_charges") {
            bucket = "origin_charges";
            code = "ORIGIN_LOCAL";
        } else if (category === "dest_charges") {
            bucket = "destination_charges";
            code = "DESTINATION_LOCAL";
        }

        if (!bucket) return null;

        const unitRaw = (assertion.rate_unit || "").toLowerCase();
        const amountRaw = assertion.rate_per_unit ?? assertion.rate_amount ?? null;
        const currency = (assertion.rate_currency || "USD").toUpperCase() as SPEChargeLine["currency"];
        if (amountRaw == null) return null;

        let unit: SPEChargeUnit = "flat";
        let min_charge: string | undefined;
        if (unitRaw === "per_kg") unit = "per_kg";
        else if (unitRaw === "per_awb") unit = "per_awb";
        else if (unitRaw === "per_shipment" || unitRaw === "shipment") unit = "per_shipment";
        else if (unitRaw === "per_set") unit = "per_set";
        else if (unitRaw === "per_trip") unit = "per_trip";
        else if (unitRaw === "per_man") unit = "per_man";
        else if (unitRaw === "percentage") unit = "percentage";
        else if (unitRaw.startsWith("min_or_per_")) {
            unit = "min_or_per_kg";
            if (assertion.rate_amount != null) min_charge = String(assertion.rate_amount);
        }

        return {
            code,
            description: assertion.text,
            amount: String(amountRaw),
            currency,
            unit,
            bucket,
            is_primary_cost: bucket === "airfreight",
            conditional: assertion.status === "conditional",
            source_reference: "AI / Analysis Suggestion",
            min_charge,
        };
    };

    const mergedCharges = useMemo(() => {
        const merged: SPEChargeLine[] = [...initialCharges];
        const seen = new Set(
            merged.map((c) => `${c.bucket}|${(c.code || "").toUpperCase()}|${(c.description || "").trim().toUpperCase()}`)
        );

        for (const assertion of suggestedCharges) {
            const mapped = mapAssertionToCharge(assertion);
            if (!mapped) continue;
            const key = `${mapped.bucket}|${mapped.code.toUpperCase()}|${mapped.description.trim().toUpperCase()}`;
            if (seen.has(key)) continue;
            merged.push(mapped);
            seen.add(key);
        }
        return merged;
    }, [initialCharges, suggestedCharges]);

    const normalizeScope = (scope?: string) => {
        if (!scope) return "A2A";
        const normalized = scope.toUpperCase();
        return normalized === "P2P" ? "A2A" : normalized;
    };

    const getRequiredComponents = (
        shipment: "EXPORT" | "IMPORT" | "DOMESTIC",
        scope?: string,
    ) => {
        const normalizedScope = normalizeScope(scope);

        if (shipment === "DOMESTIC") {
            return ["FREIGHT"] as const;
        }

        if (normalizedScope === "A2A") return ["FREIGHT"] as const;
        if (normalizedScope === "D2A") return ["ORIGIN_LOCAL", "FREIGHT"] as const;
        if (normalizedScope === "A2D") return ["DESTINATION_LOCAL"] as const;
        if (normalizedScope === "D2D") return ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"] as const;

        return ["FREIGHT"] as const;
    };

    const componentToBucket = (component: string): SPEChargeBucket | null => {
        if (component === "FREIGHT") return "airfreight";
        if (component === "ORIGIN_LOCAL") return "origin_charges";
        if (component === "DESTINATION_LOCAL") return "destination_charges";
        return null;
    };

    const assertionToBucket = (assertion: ExtractedAssertion): SPEChargeBucket | null => {
        if (assertion.category === "rate") return "airfreight";
        if (assertion.category === "origin_charges") return "origin_charges";
        if (assertion.category === "dest_charges") return "destination_charges";
        return null;
    };

    // Determine visible buckets using REQUIRED COMPONENT model + existing data
    const visibleBuckets = useMemo(() => {
        const requiredComponents = getRequiredComponents(shipmentType, serviceScope);
        const requiredBuckets = requiredComponents
            .map(componentToBucket)
            .filter((bucket): bucket is SPEChargeBucket => bucket !== null);

        const buckets = new Set<SPEChargeBucket>(requiredBuckets);

        mergedCharges.forEach((charge) => buckets.add(charge.bucket));
        suggestedCharges.forEach((assertion) => {
            const bucket = assertionToBucket(assertion);
            if (bucket) buckets.add(bucket);
        });

        if (buckets.size === 0) {
            CHARGE_BUCKETS.forEach((bucket) => buckets.add(bucket.id));
        }

        return CHARGE_BUCKETS.filter(b => buckets.has(b.id));
    }, [shipmentType, serviceScope, mergedCharges, suggestedCharges]);

    // Initial values
    const defaultValues = useMemo<SpotFormInputValues>(() => ({
        charges: mergedCharges.length > 0
            ? mergedCharges.map(c => ({
                id: c.id,
                code: c.code,
                description: c.description,
                amount: c.amount,
                currency: c.currency,
                unit: c.unit,
                bucket: c.bucket,
                is_primary_cost: c.is_primary_cost,
                conditional: c.conditional,
                source_reference: c.source_reference,
                min_charge: c.min_charge ? c.min_charge.toString() : null,
                note: c.note || "",
            }))
            : []
    }), [mergedCharges]);

    const form = useForm<SpotFormInputValues, unknown, SpotFormSubmitValues>({
        resolver: zodResolver(spotFormSchema),
        defaultValues,
        mode: "onChange",
    });

    useEffect(() => {
        form.reset(defaultValues);
    }, [form, defaultValues]);

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "charges",
    });

    const handleFormSubmit = async (data: SpotFormSubmitValues) => {
        const charges: Omit<SPEChargeLine, 'id'>[] = data.charges.map(l => {
            const isWeightBased = l.unit === "min_or_per_kg" || l.unit === "per_kg";
            return {
                code: l.code || l.description.toUpperCase().replace(/\s+/g, "_").slice(0, 20),
                description: l.description,
                amount: l.amount,
                currency: l.currency,
                unit: isWeightBased ? "per_kg" : (l.unit as SPEChargeUnit),
                min_charge: isWeightBased && l.min_charge ? parseFloat(l.min_charge) : undefined,
                bucket: l.bucket,
                is_primary_cost: l.is_primary_cost,
                conditional: l.conditional,
                source_reference: l.source_reference,
                note: l.note,
            };
        });

        await onSubmit(charges);
    };

    // Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ctrl/Cmd + Enter to submit
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                e.preventDefault();
                form.handleSubmit(handleFormSubmit)();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [form, handleFormSubmit]);

    const addLine = (bucket: SPEChargeBucket) => {
        append({
            description: "",
            amount: "",
            currency: "USD",
            unit: bucket === "airfreight" ? "per_kg" : "flat",
            bucket,
            is_primary_cost: bucket === "airfreight",
            conditional: false,
            source_reference: "",
            min_charge: null,
        });
    };

    const getFieldsByBucket = (bucket: SPEChargeBucket) =>
        fields.map((field, index) => ({ field, index })).filter(item => item.field.bucket === bucket);

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-8">
                {getFormErrorMessage(form.formState.errors.charges) && (
                    <Alert variant="destructive">
                        <AlertDescription>{getFormErrorMessage(form.formState.errors.charges)}</AlertDescription>
                    </Alert>
                )}

                {visibleBuckets.map(bucket => {
                    const bucketItems = getFieldsByBucket(bucket.id);
                    return (
                        <ChargeBucketSection
                            key={bucket.id}
                            bucket={bucket}
                            control={form.control}
                            fields={bucketItems}
                            onAdd={() => addLine(bucket.id)}
                            onRemove={remove}
                        />
                    );
                })}

                <Button
                    type="submit"
                    disabled={isLoading}
                    size="lg"
                    className="w-full bg-primary hover:bg-primary/90 text-primary-foreground font-semibold"
                >
                    {isLoading ? "Saving..." : "Save & Proceed"}
                </Button>
            </form>
        </Form>
    );
}
