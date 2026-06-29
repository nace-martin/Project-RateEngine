"use client";

/**
 * SpotRateEntryForm - Form for entering SPOT rate charge lines
 * Refactored to use reusable components
 */

import { useMemo, useEffect, useRef, useState, useCallback } from "react";
import { useForm, useFieldArray, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";

import PageActionBar from "@/components/navigation/PageActionBar";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Form } from "@/components/ui/form";

import type { SPEChargeLine, SPEChargeBucket, SPEChargeUnit, ExtractedAssertion } from "@/lib/spot-types";
import { spotFormSchema, type SpotFormInputValues, type SpotFormSubmitValues } from "@/lib/schemas/spotSchema";
import { ChargeBucketSection } from "./ChargeBucketSection";
import { SpotChargeLineManualReviewSheet } from "./SpotChargeLineManualReviewSheet";
import { getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";
import { getSpotChargeFormDisabledReason } from "@/lib/spot-charge-readiness";
import {
    type CommercialBucket,
    COMMERCIAL_BUCKETS,
    inferCommercialBucket,
    getDuplicateChargeIndices
} from "@/lib/spot-commercial-buckets";

type ReviewRequest = {
    chargeLineId: string;
    openManualReview: boolean;
    requestKey: number;
};

interface SpotRateEntryFormProps {
    onSubmit: (charges: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>) => Promise<void>;
    isLoading?: boolean;
    initialCharges?: SPEChargeLine[];
    suggestedCharges?: ExtractedAssertion[];
    shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
    serviceScope?: string;
    missingComponents?: string[];
    submitLabel?: string;
    submitDisabled?: boolean;
    submitDisabledReason?: string | null;
    allowEmptySubmit?: boolean;
    onSaveDraft?: (charges: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>) => Promise<void>;
    onManualResolveChargeLine?: (
        chargeLineId: string,
        request: { manual_resolved_product_code_id: number | string }
    ) => Promise<SPEChargeLine | null>;
    productCodeDomain?: string;
    envelopeId?: string;
    reviewRequest?: ReviewRequest | null;
    filterType?: "all" | "matched" | "conditional";
}

const normalizeSourceReference = (value?: string | null) => {
    const text = String(value || "").trim();
    if (!text) return "";

    return text
        .replace(/\s*\(AI\)\s*/gi, "")
        .replace(/^AI\s*\/\s*Analysis Suggestion$/i, "Imported rates")
        .replace(/^Analysis Suggestion$/i, "Imported rates");
};

// Define bucket grouping list
const CHARGE_BUCKETS = COMMERCIAL_BUCKETS;

type FormErrorWithMessage = { message?: string };

const getFormErrorMessage = (error: unknown) => {
    if (!error || Array.isArray(error)) return undefined;
    if (typeof error === "object" && "message" in error) {
        const message = (error as FormErrorWithMessage).message;
        return typeof message === "string" ? message : undefined;
    }
    return undefined;
};

const getManualReviewErrorMessage = (error: unknown) => {
    if (!(error instanceof Error)) return "Manual charge review failed.";
    return error.message.replace(/^Manual charge review failed:\s*/i, "").trim() || "Manual charge review failed.";
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
    allowEmptySubmit = false,
    onSaveDraft,
    onManualResolveChargeLine,
    productCodeDomain,
    envelopeId,
    reviewRequest,
    filterType = "all",
}: SpotRateEntryFormProps) {
    const submitLockRef = useRef(false);
    const draftLockRef = useRef(false);
    const [isSavingDraft, setIsSavingDraft] = useState(false);
    const [manualReviewCharge, setManualReviewCharge] = useState<SPEChargeLine | null>(null);
    const [isSavingManualReview, setIsSavingManualReview] = useState(false);
    const [manualReviewError, setManualReviewError] = useState<string | null>(null);

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
            source_excerpt: assertion.source_excerpt || assertion.text,
            source_line_number: assertion.source_line ?? null,
            source_line_identity: assertion.source_line_identity || (
                assertion.source_line != null ? `assertion-line:${assertion.source_line}` : undefined
            ),
            min_charge,
            percentage_basis,
        };
    }, [missingComponents, shipmentType]);

    const mergedCharges = useMemo(() => {
        const merged: SPEChargeLine[] = [...initialCharges];
        const seen = new Set(
            merged.map((c) => `${c.bucket}|${(c.code || "").toUpperCase()}|${(c.description || "").trim().toUpperCase()}`)
        );

        if (initialCharges.length === 0) {
            for (const assertion of suggestedCharges) {
                const mapped = mapAssertionToCharge(assertion);
                if (!mapped) continue;
                const key = `${mapped.bucket}|${mapped.code.toUpperCase()}|${mapped.description.trim().toUpperCase()}`;
                if (seen.has(key)) continue;
                merged.push(mapped);
                seen.add(key);
            }
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
        const airfreightCount = filteredCharges.filter((charge) => charge.bucket === "airfreight").length;
        const hasExplicitPrimaryAirfreight = filteredCharges.some(
            (charge) => charge.bucket === "airfreight" && charge.is_primary_cost
        );

        return filteredCharges.map((charge) => ({
            // Omit charge.id because react-hook-form useFieldArray conflicts with existing 'id' fields
            charge_line_id: charge.id,
            code: charge.code,
            description: getSpotChargeDisplayLabel(charge, { includeProductCode: false }),
            amount: charge.amount ? String(charge.amount) : "",
            currency: charge.currency,
            unit: (charge.min_charge !== null && charge.min_charge !== undefined && charge.unit === 'per_kg') ? 'min_or_per_kg' : charge.unit,
            bucket: charge.bucket,
            is_primary_cost: charge.is_primary_cost || (charge.bucket === "airfreight" && airfreightCount === 1 && !hasExplicitPrimaryAirfreight),
            conditional: charge.conditional,
            conditional_acknowledged: charge.conditional_acknowledged,
            conditional_acknowledged_by: charge.conditional_acknowledged_by,
            conditional_acknowledged_at: charge.conditional_acknowledged_at,
            reviewed_bucket: (charge.reviewed_bucket || inferCommercialBucket(charge)) as unknown as SpotFormInputValues["charges"][number]["reviewed_bucket"],
            source_reference: normalizeSourceReference(charge.source_reference),
            source_excerpt: charge.source_excerpt || "",
            source_line_number: charge.source_line_number ?? null,
            source_line_identity: charge.source_line_identity || "",
            min_charge: charge.min_charge ? String(charge.min_charge) : null,
            note: charge.note || "",
            exclude_from_totals: charge.exclude_from_totals,
            percentage_basis: charge.percentage_basis || "",
            source_label: charge.source_label || "",
            normalized_label: charge.normalized_label || "",
            normalization_status: charge.normalization_status ?? null,
            normalization_method: charge.normalization_method ?? null,
            matched_alias_id: charge.matched_alias_id ?? null,
            resolved_product_code: charge.resolved_product_code ?? null,
            effective_resolved_product_code: charge.effective_resolved_product_code ?? null,
            effective_resolution_status: charge.effective_resolution_status ?? null,
            requires_review: charge.requires_review ?? undefined,
            manual_resolution_status: charge.manual_resolution_status ?? null,
            manual_resolved_product_code: charge.manual_resolved_product_code ?? null,
            manual_resolution_by_user_id: charge.manual_resolution_by_user_id ?? null,
            manual_resolution_by_username: charge.manual_resolution_by_username ?? null,
            manual_resolution_at: charge.manual_resolution_at ?? null,
            calculation_type: charge.calculation_type ?? null,
            percent: charge.percent != null ? String(charge.percent) : null,
            percent_basis: charge.percent_basis ?? null,
            min_amount: charge.min_amount != null ? String(charge.min_amount) : null,
            max_amount: charge.max_amount != null ? String(charge.max_amount) : null,
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
            // Keep preserving based on the underlying backend bucket
            return initialCharges.filter(c => !visibleBuckets.includes(c.bucket));
        },
        [initialCharges, visibleBuckets]
    );

    const { fields, append, remove } = useFieldArray({
        control: form.control,
        name: "charges",
    });
    const watchedFormCharges = useWatch({
        control: form.control,
        name: "charges",
    });
    const memoizedWatchedFormCharges = useMemo(() => watchedFormCharges || [], [watchedFormCharges]);

    const duplicateIndices = useMemo(() => {
        return getDuplicateChargeIndices(memoizedWatchedFormCharges);
    }, [memoizedWatchedFormCharges]);

    const mapEditableLineToSubmitCharge = (
        line: SpotFormSubmitValues["charges"][number]
    ): Omit<SPEChargeLine, 'id'> & { charge_line_id?: string } => {
        const isWeightBased = line.unit === "min_or_per_kg" || line.unit === "per_kg";
        return {
            charge_line_id: line.charge_line_id || undefined,
            code: line.code || line.description.toUpperCase().replace(/\s+/g, "_").slice(0, 20),
            description: line.description,
            amount: line.amount,
            currency: line.currency,
            unit: isWeightBased ? "per_kg" : (line.unit as SPEChargeUnit),
            min_charge: isWeightBased && line.min_charge ? parseFloat(line.min_charge) : undefined,
            bucket: line.bucket,
            is_primary_cost: line.is_primary_cost,
            conditional: line.conditional,
            conditional_acknowledged: line.conditional_acknowledged,
            conditional_acknowledged_by: line.conditional_acknowledged_by,
            conditional_acknowledged_at: line.conditional_acknowledged_at,
            source_reference: normalizeSourceReference(line.source_reference),
            source_label: line.source_label,
            normalized_label: line.normalized_label,
            normalization_status: line.normalization_status,
            normalization_method: line.normalization_method,
            matched_alias_id: line.matched_alias_id,
            resolved_product_code: line.resolved_product_code,
            effective_resolved_product_code: line.effective_resolved_product_code,
            effective_resolution_status: line.effective_resolution_status,
            requires_review: line.requires_review,
            manual_resolution_status: line.manual_resolution_status,
            manual_resolved_product_code: line.manual_resolved_product_code,
            manual_resolution_by_user_id: line.manual_resolution_by_user_id,
            manual_resolution_by_username: line.manual_resolution_by_username,
            manual_resolution_at: line.manual_resolution_at,
            source_excerpt: line.source_excerpt,
            source_line_number: line.source_line_number,
            source_line_identity: line.source_line_identity,
            note: line.note,
            exclude_from_totals: line.exclude_from_totals,
            percentage_basis: line.percentage_basis || undefined,
            calculation_type: line.unit === "percentage" ? "percent_of" : (line.calculation_type || (line.unit === "min_or_per_kg" ? "min_or_per_unit" : "flat")),
            percent: line.unit === "percentage" && line.percent ? parseFloat(line.percent) : undefined,
            percent_basis: line.unit === "percentage" ? (line.percent_basis || undefined) : undefined,
            min_amount: line.min_amount ? parseFloat(line.min_amount) : undefined,
            max_amount: line.max_amount ? parseFloat(line.max_amount) : undefined,
        };
    };

    const mapHiddenChargeToSubmitCharge = (charge: SPEChargeLine): Omit<SPEChargeLine, 'id'> & { charge_line_id?: string } => ({
        charge_line_id: charge.id,
        code: charge.code,
        description: charge.description,
        amount: String(charge.amount),
        currency: charge.currency,
        unit: charge.unit,
        bucket: charge.bucket,
        is_primary_cost: charge.is_primary_cost,
        conditional: charge.conditional,
        conditional_acknowledged: charge.conditional_acknowledged,
        conditional_acknowledged_by: charge.conditional_acknowledged_by,
        conditional_acknowledged_at: charge.conditional_acknowledged_at,
        source_reference: normalizeSourceReference(charge.source_reference),
        source_label: charge.source_label,
        normalized_label: charge.normalized_label,
        normalization_status: charge.normalization_status,
        normalization_method: charge.normalization_method,
        matched_alias_id: charge.matched_alias_id,
        resolved_product_code: charge.resolved_product_code,
        effective_resolved_product_code: charge.effective_resolved_product_code,
        effective_resolution_status: charge.effective_resolution_status,
        requires_review: charge.requires_review,
        manual_resolution_status: charge.manual_resolution_status,
        manual_resolved_product_code: charge.manual_resolved_product_code,
        manual_resolution_by_user_id: charge.manual_resolution_by_user_id,
        manual_resolution_by_username: charge.manual_resolution_by_username,
        manual_resolution_at: charge.manual_resolution_at,
        source_excerpt: charge.source_excerpt,
        source_line_number: charge.source_line_number,
        source_line_identity: charge.source_line_identity,
        min_charge: charge.min_charge,
        note: charge.note,
        exclude_from_totals: charge.exclude_from_totals,
        percentage_basis: charge.percentage_basis,
        calculation_type: charge.calculation_type,
        percent: charge.percent,
        percent_basis: charge.percent_basis,
        min_amount: charge.min_amount,
        max_amount: charge.max_amount,
    });

    const handleFormSubmit = async (data: SpotFormSubmitValues) => {
        if (submitLockRef.current) return;
        submitLockRef.current = true;

        const editableCharges = data.charges.map(mapEditableLineToSubmitCharge);
        const preservedHiddenCharges = hiddenExistingCharges.map(mapHiddenChargeToSubmitCharge);
        const charges: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }> = [
            ...preservedHiddenCharges,
            ...editableCharges,
        ];

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

    const isSubmitBusy = Boolean(isLoading || form.formState.isSubmitting || isSavingDraft);
    const formDisabledReason = getSpotChargeFormDisabledReason({
        charges: watchedFormCharges,
        isFormValid: form.formState.isValid,
    });
    const effectiveSubmitDisabledReason = submitDisabledReason || formDisabledReason;
    const editableChargeCount = fields.length;
    const canSubmitEmpty = editableChargeCount === 0 && allowEmptySubmit && !submitDisabled;
    const canSubmit = !effectiveSubmitDisabledReason && !isSubmitBusy && !submitDisabled;

    const handleEmptySubmitClick = () => {
        if (!canSubmitEmpty || !canSubmit || submitLockRef.current) return;
        void handleFormSubmit({ charges: [] });
    };

    // Keyboard Shortcuts
    useEffect(() => {
        const handleKeyDown = (e: KeyboardEvent) => {
            // Ctrl/Cmd + Enter to submit
            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                if (!canSubmit) return;
                e.preventDefault();
                if (canSubmitEmpty) {
                    void handleFormSubmitRef.current({ charges: [] });
                    return;
                }
                form.handleSubmit((data) => handleFormSubmitRef.current(data))();
            }
        };

        window.addEventListener('keydown', handleKeyDown);
        return () => window.removeEventListener('keydown', handleKeyDown);
    }, [canSubmit, canSubmitEmpty, form]);

    const addLine = (bucket: SPEChargeBucket) => {
        append({
            description: "",
            amount: "",
            currency: "USD",
            unit: bucket === "airfreight" ? "per_kg" : "flat",
            bucket,
            charge_line_id: undefined,
            is_primary_cost: bucket === "airfreight",
            conditional: false,
            conditional_acknowledged: false,
            conditional_acknowledged_by: null,
            conditional_acknowledged_at: null,
            source_reference: "Manual entry",
            source_excerpt: "",
            source_line_number: null,
            source_line_identity: "",
            min_charge: null,
            exclude_from_totals: false,
            reviewed_bucket: bucket === "airfreight" ? "freight" : (bucket === "origin_charges" ? "origin" : "destination"),
            source_label: "",
            normalized_label: "",
            normalization_status: null,
            normalization_method: null,
            matched_alias_id: null,
            resolved_product_code: null,
            effective_resolved_product_code: null,
            effective_resolution_status: null,
            requires_review: undefined,
            manual_resolution_status: null,
            manual_resolved_product_code: null,
            manual_resolution_by_user_id: null,
            manual_resolution_by_username: null,
            manual_resolution_at: null,
        });
    };

    const handleOpenManualReview = useCallback((line: SpotFormInputValues["charges"][number]) => {
        if (!line.charge_line_id) return;
        setManualReviewError(null);
        setManualReviewCharge({
            id: line.charge_line_id,
            code: line.code || "",
            description: line.description,
            amount: line.amount,
            currency: line.currency,
            unit: line.unit as SPEChargeUnit,
            bucket: line.bucket,
            is_primary_cost: line.is_primary_cost,
            conditional: line.conditional,
            conditional_acknowledged: line.conditional_acknowledged,
            conditional_acknowledged_by: line.conditional_acknowledged_by,
            conditional_acknowledged_at: line.conditional_acknowledged_at,
            source_reference: line.source_reference,
            source_excerpt: line.source_excerpt,
            source_line_number: line.source_line_number,
            source_line_identity: line.source_line_identity,
            min_charge: line.min_charge || undefined,
            note: line.note || undefined,
            exclude_from_totals: line.exclude_from_totals,
            percentage_basis: line.percentage_basis || undefined,
            reviewed_bucket: (line.reviewed_bucket || inferCommercialBucket({ bucket: line.bucket, description: line.description, code: line.code })) as unknown as SpotFormInputValues["charges"][number]["reviewed_bucket"],
            source_label: line.source_label || undefined,
            normalized_label: line.normalized_label || undefined,
            normalization_status: line.normalization_status ?? null,
            normalization_method: line.normalization_method ?? null,
            matched_alias_id: line.matched_alias_id ?? null,
            resolved_product_code: line.resolved_product_code ?? null,
            effective_resolved_product_code: line.effective_resolved_product_code ?? null,
            effective_resolution_status: line.effective_resolution_status ?? null,
            requires_review: line.requires_review ?? undefined,
            manual_resolution_status: line.manual_resolution_status ?? null,
            manual_resolved_product_code: line.manual_resolved_product_code ?? null,
            manual_resolution_by_user_id: line.manual_resolution_by_user_id ?? null,
            manual_resolution_by_username: line.manual_resolution_by_username ?? null,
            manual_resolution_at: line.manual_resolution_at ?? null,
            calculation_type: line.calculation_type ?? null,
            percent: line.percent != null ? String(line.percent) : null,
            percent_basis: line.percent_basis ?? null,
            min_amount: line.min_amount != null ? String(line.min_amount) : null,
            max_amount: line.max_amount != null ? String(line.max_amount) : null,
        });
    }, []);

    useEffect(() => {
        if (!reviewRequest?.chargeLineId) return;

        const targetLine = form
            .getValues("charges")
            .find((line) => line.charge_line_id === reviewRequest.chargeLineId);

        const targetRow = document.getElementById(`charge-line-${reviewRequest.chargeLineId}`);
        if (targetRow) {
            targetRow.scrollIntoView({ behavior: "smooth", block: "center" });
        }

        if (reviewRequest.openManualReview && targetLine) {
            const canOpenManualReview =
                targetLine.manual_resolution_status !== "RESOLVED" &&
                (targetLine.normalization_status === "UNMAPPED" ||
                    targetLine.normalization_status === "AMBIGUOUS" ||
                    targetLine.normalization_status === "MATCHED");
            if (canOpenManualReview) {
                handleOpenManualReview(targetLine);
            }
        }
    }, [form, handleOpenManualReview, reviewRequest]);

    const handleManualReviewSave = useCallback(async (productCodeId: string) => {
        if (!manualReviewCharge?.id || !onManualResolveChargeLine) return;

        setIsSavingManualReview(true);
        setManualReviewError(null);
        try {
            const updatedCharge = await onManualResolveChargeLine(manualReviewCharge.id, {
                manual_resolved_product_code_id: productCodeId,
            });
            if (!updatedCharge) return;
            setManualReviewCharge(null);
        } catch (error) {
            setManualReviewError(getManualReviewErrorMessage(error));
        } finally {
            setIsSavingManualReview(false);
        }
    }, [manualReviewCharge, onManualResolveChargeLine]);

    const getFieldsByBucket = (bucketId: CommercialBucket) => {
        return fields
            .map((field, index) => ({ field, index }))
            .filter((item) => {
                const chargeLine = watchedFormCharges[item.index];
                if (!chargeLine) return false;
                
                const currentReviewedBucket = chargeLine.reviewed_bucket || inferCommercialBucket({
                    bucket: chargeLine.bucket,
                    description: chargeLine.description,
                    code: chargeLine.code
                });
                
                if (currentReviewedBucket !== bucketId) return false;
                if (!filterType || filterType === "all") return true;

                if (filterType === "matched") {
                    return (
                        chargeLine.manual_resolution_status === "RESOLVED" ||
                        chargeLine.normalization_status === "MATCHED"
                    );
                }
                if (filterType === "conditional") {
                    return Boolean(chargeLine.conditional);
                }
                return true;
            });
    };

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(handleFormSubmit)} className="space-y-8">
                {getFormErrorMessage(form.formState.errors.charges) && (
                    <Alert variant="destructive">
                        <AlertDescription>{getFormErrorMessage(form.formState.errors.charges)}</AlertDescription>
                    </Alert>
                )}

                {effectiveSubmitDisabledReason && (
                    <Alert>
                        <AlertDescription>{effectiveSubmitDisabledReason}</AlertDescription>
                    </Alert>
                )}

                {CHARGE_BUCKETS.map(bucket => {
                    const bucketItems = getFieldsByBucket(bucket.id);
                    // Map commercial bucket default backend category for item addition
                    const defaultBackendBucketMap: Record<CommercialBucket, SPEChargeBucket> = {
                        freight: "airfreight",
                        origin: "origin_charges",
                        destination: "destination_charges",
                        security: "origin_charges",
                        customs: "origin_charges",
                        transport: "origin_charges",
                        other: "origin_charges"
                    };
                    const targetBackendBucket = defaultBackendBucketMap[bucket.id];
                    return (
                        <ChargeBucketSection
                            key={bucket.id}
                            bucket={bucket}
                            control={form.control}
                            fields={bucketItems}
                            onAdd={() => addLine(targetBackendBucket)}
                            onRemove={remove}
                            onOpenManualReview={handleOpenManualReview}
                            activeChargeLineId={reviewRequest?.chargeLineId ?? null}
                            duplicateIndices={duplicateIndices}
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
                        type={canSubmitEmpty ? "button" : "submit"}
                        onClick={canSubmitEmpty ? handleEmptySubmitClick : undefined}
                        disabled={!canSubmit}
                        size="lg"
                        loading={Boolean(isLoading || form.formState.isSubmitting)}
                        loadingText="Saving changes..."
                    >
                        {submitLabel || "Save & Proceed"}
                    </Button>
                </PageActionBar>
            </form>
            <SpotChargeLineManualReviewSheet
                open={Boolean(manualReviewCharge)}
                onOpenChange={(open) => {
                    if (!open) {
                        setManualReviewCharge(null);
                        setManualReviewError(null);
                    }
                }}
                chargeLine={manualReviewCharge}
                envelopeId={envelopeId}
                productDomain={productCodeDomain}
                isSaving={isSavingManualReview}
                saveError={manualReviewError}
                onSave={handleManualReviewSave}
            />
        </Form>
    );
}
