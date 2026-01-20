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
import { spotFormSchema, type SpotFormValues } from "@/lib/schemas/spotSchema";
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

    // Determine visible buckets
    const visibleBuckets = useMemo(() => {
        const buckets = new Set<SPEChargeBucket>();
        const scope = serviceScope.toUpperCase();

        if (shipmentType === "IMPORT") {
            buckets.add("airfreight");
            if (scope.startsWith("D")) buckets.add("origin_charges");
        } else {
            if (scope.endsWith("D")) buckets.add("destination_charges");
        }
        // Always allow airfreight bucket for now as a fallback
        buckets.add("airfreight");

        return CHARGE_BUCKETS.filter(b => buckets.has(b.id));
    }, [shipmentType, serviceScope]);

    // Initial values
    const defaultValues: SpotFormValues = {
        charges: initialCharges.length > 0
            ? initialCharges.map(c => ({
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
    };

    const form = useForm<SpotFormValues>({
        resolver: zodResolver(spotFormSchema),
        defaultValues,
        mode: "onChange",
    });

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "charges",
    });

    const handleFormSubmit = async (data: SpotFormValues) => {
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
