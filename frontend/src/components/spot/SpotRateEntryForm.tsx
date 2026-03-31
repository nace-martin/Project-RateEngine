"use client";

/**
 * SpotRateEntryForm - Form for entering SPOT rate charge lines
 * Refactored to use reusable components
 */

import { useMemo, useEffect, useRef, useState, useCallback } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageActionBar from "@/components/navigation/PageActionBar";
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
    missingComponents?: string[];
    submitLabel?: string;
    submitDisabled?: boolean;
    submitDisabledReason?: string | null;
    onSaveDraft?: (charges: Omit<SPEChargeLine, 'id'>[]) => Promise<void>;
}

const normalizeSourceReference = (value?: string | null) => {
    const text = String(value || "").trim();
    if (!text) return "";

    return text
        .replace(/\s*\(AI\)\s*/gi, "")
        .replace(/^AI\s*\/\s*Analysis Suggestion$/i, "Imported rates")
        .replace(/^Analysis Suggestion$/i, "Imported rates");
};

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

export function SpotRateEntryForm({
    onSubmit,
    isLoading,
    initialCharges = [],
    suggestedCharges = [],
    shipmentType = "EXPORT",
    serviceScope = "D2D",
    missingComponents = [],
    submitLabel,
    submitDisabled = false,
    submitDisabledReason = null,
    onSaveDraft,
}: SpotRateEntryFormProps) {
    const submitLockRef = useRef(false);
    const draftLockRef = useRef(false);
    const [isSavingDraft, setIsSavingDraft] = useState(false);

    const mapAssertionToCharge = useCallback((assertion: ExtractedAssertion): SPEChargeLine | null => {
        let category = assertion.category;
        let bucket: SPEChargeBucket | null = null;
        let code = "MISC";

        // Re-bucketing heuristic (mirrors backend spot_services.py):
        // When only one local side is missing, bias local-charge assertions to that missing side.
        const missingSet = new Set(missingComponents.map(c => c.toUpperCase()));
        if (shipmentType === "EXPORT") {
            if (
                category === "origin_charges" &&
                missingSet.has("DESTINATION_LOCAL") &&
                !missingSet.has("ORIGIN_LOCAL")
            ) {
                category = "dest_charges";
            }
        } else if (shipmentType === "IMPORT") {
            if (
                category === "dest_charges" &&
                missingSet.has("ORIGIN_LOCAL") &&
                !missingSet.has("DESTINATION_LOCAL")
            ) {
                category = "origin_charges";
            }
        }

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
        if (amountRaw == null || Number(amountRaw) <= 0) return null;

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

        let percentage_basis: string | undefined;
        if (unitRaw === "percentage" && assertion.percentage_basis) {
            percentage_basis = assertion.percentage_basis;
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
            source_reference: "Imported rates",
            min_charge,
            percentage_basis,
        };
    }, [missingComponents, shipmentType]);

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
    }, [initialCharges, suggestedCharges, mapAssertionToCharge]);

    // Determine visible buckets:
    // - If missing components are explicitly provided, show ONLY those buckets.
    // - Otherwise (legacy fallback), include required buckets plus any data buckets.
    const visibleBuckets = useMemo(() => {
        const missingBuckets = missingComponents.length > 0
            ? missingComponents
                .map(componentToBucket)
                .filter((bucket): bucket is SPEChargeBucket => bucket !== null)
            : getRequiredComponents(shipmentType, serviceScope)
                .map(componentToBucket)
                .filter((bucket): bucket is SPEChargeBucket => bucket !== null);

        const orderedBuckets: SPEChargeBucket[] = ["airfreight", "origin_charges", "destination_charges"];
        if (missingComponents.length > 0) {
            const bucketSet = new Set(missingBuckets);
            return orderedBuckets.filter(b => bucketSet.has(b));
        }

        const bucketSet = new Set(missingBuckets);
        for (const charge of mergedCharges) {
            if (charge.bucket) bucketSet.add(charge.bucket);
        }
        return orderedBuckets.filter(b => bucketSet.has(b));
    }, [shipmentType, serviceScope, missingComponents, mergedCharges]);

    // Initial values
    const defaultValues = useMemo<SpotFormInputValues>(() => ({
        charges: []
    }), []);

    const form = useForm<SpotFormInputValues, unknown, SpotFormSubmitValues>({
        resolver: zodResolver(spotFormSchema),
        defaultValues,
        mode: "onChange",
    });

    const formattedVisibleCharges = useMemo<SpotFormInputValues["charges"]>(() => {
        // Only visible buckets are editable in this form.
        const filteredCharges = mergedCharges.filter(c => visibleBuckets.includes(c.bucket));

        return filteredCharges.map((charge) => ({
            // Omit charge.id because react-hook-form useFieldArray conflicts with existing 'id' fields
            code: charge.code,
            description: charge.description,
            amount: charge.amount ? String(charge.amount) : "",
            currency: charge.currency,
            unit: (charge.min_charge !== null && charge.min_charge !== undefined && charge.unit === 'per_kg') ? 'min_or_per_kg' : charge.unit,
            bucket: charge.bucket,
            is_primary_cost: charge.is_primary_cost,
            conditional: charge.conditional,
            source_reference: normalizeSourceReference(charge.source_reference),
            min_charge: charge.min_charge ? String(charge.min_charge) : null,
            note: charge.note || "",
            exclude_from_totals: charge.exclude_from_totals,
            percentage_basis: charge.percentage_basis || "",
        }));
    }, [mergedCharges, visibleBuckets]);

    const resetSignature = useMemo(
        () => JSON.stringify(formattedVisibleCharges),
        [formattedVisibleCharges]
    );
    const lastResetSignatureRef = useRef<string>("");

    useEffect(() => {
        if (lastResetSignatureRef.current === resetSignature) {
            return;
        }
        lastResetSignatureRef.current = resetSignature;
        form.reset({ charges: formattedVisibleCharges });
    }, [form, resetSignature, formattedVisibleCharges]);

    const hiddenExistingCharges = useMemo(
        () => {
            // In strict missing-components mode, keep non-visible buckets out of SPE submit payload.
            if (missingComponents.length > 0) return [];
            return initialCharges.filter(c => !visibleBuckets.includes(c.bucket));
        },
        [initialCharges, visibleBuckets, missingComponents.length]
    );

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "charges",
    });

    const mapEditableLineToSubmitCharge = (line: SpotFormSubmitValues["charges"][number]): Omit<SPEChargeLine, 'id'> => {
        const isWeightBased = line.unit === "min_or_per_kg" || line.unit === "per_kg";
        return {
            code: line.code || line.description.toUpperCase().replace(/\s+/g, "_").slice(0, 20),
            description: line.description,
            amount: line.amount,
            currency: line.currency,
            unit: isWeightBased ? "per_kg" : (line.unit as SPEChargeUnit),
            min_charge: isWeightBased && line.min_charge ? parseFloat(line.min_charge) : undefined,
            bucket: line.bucket,
            is_primary_cost: line.is_primary_cost,
            conditional: line.conditional,
            source_reference: normalizeSourceReference(line.source_reference),
            note: line.note,
            exclude_from_totals: line.exclude_from_totals,
            percentage_basis: line.percentage_basis || undefined,
        };
    };

    const mapHiddenChargeToSubmitCharge = (charge: SPEChargeLine): Omit<SPEChargeLine, 'id'> => ({
        code: charge.code,
        description: charge.description,
        amount: String(charge.amount),
        currency: charge.currency,
        unit: charge.unit,
        bucket: charge.bucket,
        is_primary_cost: charge.is_primary_cost,
        conditional: charge.conditional,
        source_reference: normalizeSourceReference(charge.source_reference),
        min_charge: charge.min_charge,
        note: charge.note,
        exclude_from_totals: charge.exclude_from_totals,
        percentage_basis: charge.percentage_basis,
    });

    const handleFormSubmit = async (data: SpotFormSubmitValues) => {
        if (submitLockRef.current) return;
        submitLockRef.current = true;

        const editableCharges = data.charges.map(mapEditableLineToSubmitCharge);
        const preservedHiddenCharges = hiddenExistingCharges.map(mapHiddenChargeToSubmitCharge);
        const charges: Omit<SPEChargeLine, 'id'>[] = [...preservedHiddenCharges, ...editableCharges];

        try {
            await onSubmit(charges);
        } finally {
            submitLockRef.current = false;
        }
    };
    const handleFormSubmitRef = useRef(handleFormSubmit);
    handleFormSubmitRef.current = handleFormSubmit;

    const handleSaveDraft = async () => {
        if (!onSaveDraft || draftLockRef.current) return;
        draftLockRef.current = true;
        setIsSavingDraft(true);

        try {
            const data = form.getValues();
            const editableCharges = data.charges.map((line) =>
                mapEditableLineToSubmitCharge(line as SpotFormSubmitValues["charges"][number])
            );
            const preservedHiddenCharges = hiddenExistingCharges.map(mapHiddenChargeToSubmitCharge);
            await onSaveDraft([...preservedHiddenCharges, ...editableCharges]);
        } finally {
            setIsSavingDraft(false);
            draftLockRef.current = false;
        }
    };

    // Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ctrl/Cmd + Enter to submit
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                if (form.formState.isSubmitting || isLoading || isSavingDraft) return;
                e.preventDefault();
                form.handleSubmit((data) => handleFormSubmitRef.current(data))();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [form, isLoading, isSavingDraft]);

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
            exclude_from_totals: false,
        });
    };

    const getFieldsByBucket = (bucket: SPEChargeBucket) =>
        fields.map((field, index) => ({ field, index })).filter(item => item.field.bucket === bucket);

    const isSubmitBusy = Boolean(isLoading || form.formState.isSubmitting || isSavingDraft);
    const canSubmit = form.formState.isValid && !isSubmitBusy && !submitDisabled;

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-8">
                {getFormErrorMessage(form.formState.errors.charges) && (
                    <Alert variant="destructive">
                        <AlertDescription>{getFormErrorMessage(form.formState.errors.charges)}</AlertDescription>
                    </Alert>
                )}

                {submitDisabledReason && (
                    <Alert>
                        <AlertDescription>{submitDisabledReason}</AlertDescription>
                    </Alert>
                )}

                {visibleBuckets.map(bucketId => {
                    const bucket = CHARGE_BUCKETS.find(b => b.id === bucketId);
                    if (!bucket) return null;
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

                <PageActionBar className="border-0 bg-transparent p-0 shadow-none">
                    {onSaveDraft && (
                        <Button
                            type="button"
                            variant="outline"
                            disabled={isSubmitBusy || !form.formState.isValid}
                            size="lg"
                            onClick={handleSaveDraft}
                            loading={isSavingDraft}
                            loadingText="Saving draft..."
                        >
                            Save Draft
                        </Button>
                    )}
                    <Button
                        type="submit"
                        disabled={!canSubmit}
                        size="lg"
                        loading={Boolean(isLoading || form.formState.isSubmitting)}
                        loadingText="Saving changes..."
                    >
                        {submitLabel || "Save & Proceed"}
                    </Button>
                </PageActionBar>
            </form>
        </Form>
    );
}
