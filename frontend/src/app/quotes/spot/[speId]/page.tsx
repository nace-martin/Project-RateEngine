"use client";

/**
 * SPOT Rate Entry Page
 * 
 * Streamlined 2-step flow:
 * 1. Intake (Submit) - Paste agent reply, AI analysis
 * 2. Review (Confirm & Create) - Review charges and create quote
 */

import { useState, useEffect, useMemo, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useSpotMode } from "@/hooks/use-spot-mode";
import {
    ExpiredBanner,
    RejectedBanner,
    ReplyPasteCard,
} from "@/components/spot";
import { SpotRateEntryForm } from "@/components/spot/SpotRateEntryForm";
import type { SPEChargeLine, SPECommodity } from "@/lib/spot-types";
import type { ReplyAnalysisResult } from "@/lib/spot-types";
import { getSpotStandardCharges } from "@/lib/api";
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import PageBackButton from "@/components/navigation/PageBackButton";
import PageCancelButton from "@/components/navigation/PageCancelButton";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";

// Streamlined 2-step workflow
type Step = "intake" | "review";

const STEPS: { id: Step; label: string; description: string }[] = [
    { id: "intake", label: "1. Submit", description: "Paste agent reply" },
    { id: "review", label: "2. Confirm & Create", description: "Review charges & create quote" },
];

const EMPTY_COMPONENTS: string[] = [];
const EMPTY_CHARGES: SPEChargeLine[] = [];
const BUY_SIDE_SOURCE_MARKERS = ["COGS", "BUY"];

const isBuySideCharge = (charge: SPEChargeLine) => {
    const source = (charge.source_reference || "").toUpperCase();
    // Standard Rate charges are computed FROM COGS but are sell-side charges — don't filter them out
    if (source.startsWith("STANDARD RATE")) return false;
    // AI/Analysis suggestions are always user-facing
    if (source.includes("AI") || source.includes("ANALYSIS") || source.includes("AGENT REPLY")) return false;
    return BUY_SIDE_SOURCE_MARKERS.some((marker) => source.includes(marker));
};

const isStandardRateCharge = (charge: SPEChargeLine) =>
    (charge.source_reference || "").toUpperCase().startsWith("STANDARD RATE");

const componentToBucket = (component: string): SPEChargeLine["bucket"] | null => {
    const normalized = (component || "").toUpperCase();
    if (normalized === "FREIGHT") return "airfreight";
    if (normalized === "ORIGIN_LOCAL") return "origin_charges";
    if (normalized === "DESTINATION_LOCAL") return "destination_charges";
    return null;
};

const BUCKET_LABELS: Record<SPEChargeLine["bucket"], string> = {
    airfreight: "Freight",
    origin_charges: "Origin Charges",
    destination_charges: "Destination Charges",
};

type IntakeSourceSection = {
    id: SPEChargeLine["bucket"];
    title: string;
    description: string;
    sourceKind: "AIRLINE" | "AGENT" | "MANUAL" | "OTHER";
    sourceLabel: string;
};

const INTAKE_BUCKET_ORDER: SPEChargeLine["bucket"][] = [
    "airfreight",
    "origin_charges",
    "destination_charges",
];

const buildIntakeSections = (
    buckets: SPEChargeLine["bucket"][],
    shipmentType: "EXPORT" | "IMPORT" | "DOMESTIC"
): IntakeSourceSection[] => {
    return INTAKE_BUCKET_ORDER
        .filter((bucket) => buckets.includes(bucket))
        .map((bucket) => {
            if (bucket === "airfreight") {
                return {
                    id: bucket,
                    title: "Airline Freight Quote",
                    description: "Upload or paste the airline quote for the missing freight component.",
                    sourceKind: "AIRLINE",
                    sourceLabel: "Airline Freight Quote",
                };
            }

            if (bucket === "origin_charges") {
                return {
                    id: bucket,
                    title: shipmentType === "IMPORT" ? "Origin Agent Quote" : "Origin Charges Source",
                    description:
                        shipmentType === "IMPORT"
                            ? "Add the overseas origin charges that are not covered by standard rates."
                            : "Add the origin-side charges required for this SPOT quote.",
                    sourceKind: "AGENT",
                    sourceLabel: shipmentType === "IMPORT" ? "Origin Agent Quote" : "Origin Charges Source",
                };
            }

            return {
                id: bucket,
                title: shipmentType === "EXPORT" ? "Destination Agent Quote" : "Destination Charges Source",
                description:
                    shipmentType === "EXPORT"
                        ? "Add the overseas destination charges from the receiving agent."
                        : "Add the destination-side charges required for this SPOT quote.",
                sourceKind: "AGENT",
                sourceLabel: shipmentType === "EXPORT" ? "Destination Agent Quote" : "Destination Charges Source",
            };
        });
};

export default function SpotRateEntryPage() {
    const params = useParams();
    const router = useRouter();
    const searchParams = useSearchParams();

    const speId = params.speId as string;
    const isNew = speId === "new";

    // Get shipment context from URL params (for new SPE)
    const originCode = searchParams.get("origin_code") || "";
    const destCode = searchParams.get("dest_code") || "";
    const commodity = (searchParams.get("commodity") || "GCR") as SPECommodity;
    const weight = parseFloat(searchParams.get("weight") || "0");
    const pieces = parseInt(searchParams.get("pieces") || "1");
    const originCountryParam = searchParams.get("origin_country") || "";
    const destCountryParam = searchParams.get("dest_country") || "";
    const triggerCode = searchParams.get("trigger_code") || "";
    const triggerText = searchParams.get("trigger_text") || "";
    const serviceScope = searchParams.get("service_scope") || "";
    const paymentTerm = searchParams.get("payment_term") || "PREPAID";
    const customerIdParam = searchParams.get("customer_id") || "";
    const customerNameParam = searchParams.get("customer_name") || "";
    const outputCurrency = searchParams.get("output_currency") || "PGK";
    const shipmentTypeParam = searchParams.get("shipment_type") as "EXPORT" | "IMPORT" | "DOMESTIC" | null;
    const returnTo = searchParams.get("returnTo");

    const { state, actions } = useSpotMode();
    const missingComponentsParam = searchParams.get("missing_components");
    const missingComponentsFromQuery = useMemo(() => {
        if (!missingComponentsParam) return null;
        return missingComponentsParam
            .split(",")
            .map((component) => component.trim())
            .filter(Boolean);
    }, [missingComponentsParam]);
    const missingComponents = useMemo(
        () => missingComponentsFromQuery || state.spe?.shipment.missing_components || EMPTY_COMPONENTS,
        [missingComponentsFromQuery, state.spe?.shipment.missing_components]
    );
    const editableBuckets = useMemo(
        () =>
            Array.from(
                new Set(
                    missingComponents
                        .map(componentToBucket)
                        .filter((bucket): bucket is SPEChargeLine["bucket"] => bucket !== null)
                )
            ),
        [missingComponents]
    );
    const { loadSPE } = actions;
    const [currentStep, setCurrentStep] = useState<Step>("intake");
    const [analysisResult, setAnalysisResult] = useState<ReplyAnalysisResult | null>(null);
    const [primarySourceBatchId, setPrimarySourceBatchId] = useState<string | null>(null);
    const [sectionBatchIds, setSectionBatchIds] = useState<Record<string, string>>({});
    const [intakeDirtyMap, setIntakeDirtyMap] = useState<Record<string, boolean>>({});
    const [standardPrefillCharges, setStandardPrefillCharges] = useState<SPEChargeLine[]>([]);
    // Guard ref: prevents the auto-detection useEffect from overriding
    // an explicit step transition (e.g. after analysis completes).
    const userAdvancedToReviewRef = useRef(false);

    const inferShipmentType = (originCountry?: string, destinationCountry?: string): "EXPORT" | "IMPORT" | "DOMESTIC" => {
        if ((originCountry || "").toUpperCase() === "PG" && (destinationCountry || "").toUpperCase() === "PG") {
            return "DOMESTIC";
        }
        if ((originCountry || "").toUpperCase() === "PG") {
            return "EXPORT";
        }
        return "IMPORT";
    };

    const resolvedShipmentType =
        shipmentTypeParam ||
        (state.spe?.shipment
            ? inferShipmentType(state.spe.shipment.origin_country, state.spe.shipment.destination_country)
            : inferShipmentType(originCountryParam, destCountryParam));
    const isMultiSourceIntake = editableBuckets.length > 1;
    const intakeSections = useMemo(
        () => (isMultiSourceIntake ? buildIntakeSections(editableBuckets, resolvedShipmentType) : []),
        [editableBuckets, isMultiSourceIntake, resolvedShipmentType]
    );
    const hasIntakeDrafts = useMemo(
        () => Object.values(intakeDirtyMap).some(Boolean),
        [intakeDirtyMap]
    );
    const hasPendingUnsavedWork =
        hasIntakeDrafts || Boolean(analysisResult) || (currentStep === "review" && !state.quoteResult);
    const confirmLeave = useUnsavedChangesGuard(hasPendingUnsavedWork);

    const formatMissingComponents = (components?: string[]) => {
        if (!components || components.length === 0) return null;
        const friendly = components.map((component) => {
            const normalized = component.toUpperCase();
            if (normalized === "DESTINATION_LOCAL") return "Destination Charges";
            if (normalized === "ORIGIN_LOCAL") return "Origin Charges";
            if (normalized === "FREIGHT") return "Freight Rate";
            return component.replace(/_/g, " ");
        });
        return Array.from(new Set(friendly));
    };

    const displayCustomerName = useMemo(() => {
        const candidate = (
            state.spe?.customer_name ||
            state.spe?.shipment?.customer_name ||
            customerNameParam ||
            ""
        ).trim();
        return candidate || "Spot Request";
    }, [state.spe?.customer_name, state.spe?.shipment?.customer_name, customerNameParam]);

    const displayServiceScope = useMemo(() => {
        const scope = String(state.spe?.shipment.service_scope || serviceScope || "D2D").toUpperCase();
        return scope || "N/A";
    }, [state.spe?.shipment.service_scope, serviceScope]);

    const displayPaymentTerm = useMemo(() => {
        const rawTerm = String(state.spe?.shipment.payment_term || paymentTerm || "PREPAID").toUpperCase();
        if (rawTerm === "COLLECT") return "Collect";
        if (rawTerm === "PREPAID") return "Prepaid";
        return rawTerm || "N/A";
    }, [state.spe?.shipment.payment_term, paymentTerm]);

    const importedSpotBuckets = useMemo(() => {
        const buckets = new Set<SPEChargeLine["bucket"]>();
        for (const charge of state.spe?.charges || EMPTY_CHARGES) {
            if (!isBuySideCharge(charge) && !isStandardRateCharge(charge)) {
                buckets.add(charge.bucket);
            }
        }
        return buckets;
    }, [state.spe?.charges]);

    const allMultiSourceSectionsReady = useMemo(
        () => intakeSections.every((section) => importedSpotBuckets.has(section.id)),
        [importedSpotBuckets, intakeSections]
    );

    // Load existing SPE
    useEffect(() => {
        if (speId && !isNew) {
            loadSPE(speId);
        }
    }, [isNew, speId, loadSPE]);

    // Determine current step from SPE state (only for initial load, not after explicit transitions)
    useEffect(() => {
        // If the user has explicitly advanced to review (e.g. via Analyze Reply),
        // do NOT let this effect reset back to intake.
        if (userAdvancedToReviewRef.current) return;

        if (state.spe) {
            if (isMultiSourceIntake && !allMultiSourceSectionsReady) {
                setCurrentStep("intake");
            } else if (state.spe.charges.length > 0) {
                // If we have charges, go to review step
                setCurrentStep(prev => prev === "review" ? prev : "review");
            } else {
                // Initial state - intake
                setCurrentStep("intake");
            }
        }
    }, [allMultiSourceSectionsReady, isMultiSourceIntake, state.spe, state.flowState]);

    useEffect(() => {
        const sources = state.spe?.sources || [];
        if (!sources.length) {
            return;
        }
        setSectionBatchIds((prev) => {
            const next = { ...prev };
            let changed = false;
            for (const source of sources) {
                if (source.target_bucket !== "mixed" && !next[source.target_bucket]) {
                    next[source.target_bucket] = source.id;
                    changed = true;
                }
            }
            return changed ? next : prev;
        });
        if (!primarySourceBatchId) {
            const primarySource =
                sources.find((source) => source.target_bucket === "mixed") || sources[0];
            if (primarySource) {
                setPrimarySourceBatchId(primarySource.id);
            }
        }
    }, [primarySourceBatchId, state.spe?.sources]);

    // Load hybrid standard DB charges (origin/freight/destination where coverage exists)
    useEffect(() => {
        const shipment = state.spe?.shipment;
        if (!shipment || !state.spe?.id) return;

        let cancelled = false;
        const run = async () => {
            try {
                const rawPaymentTerm =
                    (shipment.payment_term || paymentTerm || "PREPAID").toUpperCase();
                const normalizedPaymentTerm: "PREPAID" | "COLLECT" =
                    rawPaymentTerm === "COLLECT" ? "COLLECT" : "PREPAID";

                const charges = await getSpotStandardCharges({
                    origin_code: shipment.origin_code,
                    destination_code: shipment.destination_code,
                    direction: resolvedShipmentType,
                    service_scope: shipment.service_scope || serviceScope || "D2D",
                    payment_term: normalizedPaymentTerm,
                    weight_kg: shipment.total_weight_kg || weight || 100,
                    commodity: shipment.commodity || commodity || "GCR",
                });

                if (!cancelled) {
                    // Review step must only show/edit components that are actually missing.
                    if (editableBuckets.length > 0) {
                        const editableBucketSet = new Set(editableBuckets);
                        setStandardPrefillCharges(charges.filter((charge) => editableBucketSet.has(charge.bucket)));
                    } else {
                        setStandardPrefillCharges(charges);
                    }
                }
            } catch (err) {
                console.error("Failed to load standard SPOT charges:", err);
                if (!cancelled) setStandardPrefillCharges([]);
            }
        };

        run();
        return () => {
            cancelled = true;
        };
    }, [state.spe, serviceScope, paymentTerm, weight, commodity, resolvedShipmentType, editableBuckets]);

    const mergedFormCharges = useMemo(() => {
        const speCharges = state.spe?.charges || EMPTY_CHARGES;
        if (!standardPrefillCharges.length) return speCharges;

        const keyFor = (c: SPEChargeLine) =>
            `${c.bucket}|${(c.code || "").toUpperCase()}|${(c.description || "").trim().toUpperCase()}`;
        const mergedMap = new Map<string, SPEChargeLine>();

        for (const charge of speCharges) {
            mergedMap.set(keyFor(charge), charge);
        }

        for (const c of standardPrefillCharges) {
            const key = keyFor(c);
            const existing = mergedMap.get(key);
            if (!existing || isStandardRateCharge(existing)) {
                // Prefer fresh standard-prefill values for standard lines (e.g. stale envelopes
                // may contain older COGS-based values for these same charges).
                mergedMap.set(key, c);
            }
        }

        return Array.from(mergedMap.values());
    }, [state.spe?.charges, standardPrefillCharges]);

    const reviewFormCharges = useMemo(() => {
        // Review form should only contain SPOT-entered/manual rates.
        // Exclude any DB standard-rate lines from the editable SPE payload.
        const candidateCharges = mergedFormCharges.filter(
            (charge) => !isBuySideCharge(charge) && !isStandardRateCharge(charge)
        );
        if (editableBuckets.length === 0) return candidateCharges;
        const editableBucketSet = new Set(editableBuckets);
        return candidateCharges.filter((charge) => editableBucketSet.has(charge.bucket));
    }, [mergedFormCharges, editableBuckets]);

    const sourceReviewSummaries = useMemo(() => {
        const charges = (state.spe?.charges || EMPTY_CHARGES).filter(
            (charge) => !isBuySideCharge(charge) && !isStandardRateCharge(charge)
        );
        return (state.spe?.sources || []).map((source) => {
            const sourceCharges = charges.filter((charge) => charge.source_batch_id === source.id);
            const currencies = Array.from(new Set(sourceCharges.map((charge) => charge.currency)));
            const buckets = Array.from(new Set(sourceCharges.map((charge) => charge.bucket)));
            return {
                id: source.id,
                label: source.label,
                targetBucket: source.target_bucket,
                sourceKind: source.source_kind,
                lineCount: sourceCharges.length,
                currencies,
                buckets,
            };
        });
    }, [state.spe?.charges, state.spe?.sources]);

    const overlapWarnings = useMemo(() => {
        const warnings = new Set<string>();
        const missingBucketSet = new Set(editableBuckets);

        for (const summary of sourceReviewSummaries) {
            if (summary.currencies.length > 1) {
                warnings.add(
                    `${summary.label} contains multiple currencies (${summary.currencies.join(", ")}). Review the FX treatment before confirming the quote.`
                );
            }

            if (summary.targetBucket !== "mixed") {
                const unexpectedBuckets = summary.buckets.filter((bucket) => bucket !== summary.targetBucket);
                if (unexpectedBuckets.length > 0) {
                    warnings.add(
                        `${summary.label} imported ${unexpectedBuckets.map((bucket) => BUCKET_LABELS[bucket]).join(", ")} as well as its expected bucket. Check for overlap before confirming.`
                    );
                }
            }

            for (const bucket of summary.buckets) {
                if (missingBucketSet.size > 0 && !missingBucketSet.has(bucket)) {
                    warnings.add(
                        `${summary.label} includes ${BUCKET_LABELS[bucket]}, but that bucket is already covered by standard pricing for this lane. Remove duplicates before confirming.`
                    );
                }
            }
        }

        return Array.from(warnings);
    }, [editableBuckets, sourceReviewSummaries]);

    // Handle saving charges, acknowledging, and creating the final quote in one flow
    const handleSaveAndCreateQuote = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        if (state.spe) {
            // 1. Update charges
            const spe = await actions.updateSPE(state.spe.id, {
                charges,
                conditions: {
                    space_not_confirmed: true,
                    airline_acceptance_not_confirmed: true,
                    rate_validity_hours: 72,
                    conditional_charges_present: charges.some(c => c.conditional),
                }
            });

            if (spe) {
                // 2. Auto-acknowledge
                const success = await actions.submitAcknowledgement();
                if (success) {
                    // 3. Create the quote directly (backend handles compute internally)
                    const resolvedScope = serviceScope || "D2D";
                    const resolvedPaymentTerm = paymentTerm || "PREPAID";
                    const resolvedOutputCurrency = outputCurrency || "PGK";

                    const result = await actions.createQuote({
                        payment_term: resolvedPaymentTerm,
                        service_scope: resolvedScope,
                        output_currency: resolvedOutputCurrency,
                        customer_id: customerIdParam || undefined,
                    });

                    if (result?.success && result.quote_id) {
                        router.push(`/quotes/${result.quote_id}`);
                    }
                }
            }
        }
    };

    // Handle saving draft without creating quote
    const handleSaveDraft = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        if (state.spe) {
            await actions.updateSPE(state.spe.id, {
                charges,
                conditions: {
                    space_not_confirmed: true,
                    airline_acceptance_not_confirmed: true,
                    rate_validity_hours: 72,
                    conditional_charges_present: charges.some(c => c.conditional),
                }
            });
            router.push("/quotes");
        }
    };

    // Handle analysis complete from intake step - move directly to review
    const handleAnalysisComplete = async (
        result: ReplyAnalysisResult,
        targetBucket: SPEChargeLine["bucket"] | "mixed" = "mixed"
    ) => {
        setAnalysisResult(result);
        if (result.source_batch_id) {
            if (targetBucket === "mixed") {
                setPrimarySourceBatchId(result.source_batch_id);
            } else {
                setSectionBatchIds((prev) => ({
                    ...prev,
                    [targetBucket]: result.source_batch_id!,
                }));
            }
        }
        // Set the guard BEFORE the async reload so the useEffect doesn't fight us.
        // Multi-source intake stays on the intake step until the user explicitly continues.
        userAdvancedToReviewRef.current = !isMultiSourceIntake;
        if (speId && !isNew) {
            // Backend persists auto-populated charges (AI + standard DB suggestions) into the SPE.
            // Reload before entering review so the form displays the latest draft charges.
            await loadSPE(speId);
        }
        if (!isMultiSourceIntake) {
            setCurrentStep("review");
        }
    };

    const getSourceStatusText = (section: IntakeSourceSection) => {
        const imported = reviewFormCharges.filter((charge) => charge.bucket === section.id).length;
        if (imported > 0) {
            return `${imported} charge line${imported === 1 ? "" : "s"} imported`;
        }
        if (sectionBatchIds[section.id]) {
            return "Source ready for re-analysis";
        }
        return "Awaiting source";
    };

    const getSourceStatusClasses = (section: IntakeSourceSection) => {
        if (importedSpotBuckets.has(section.id)) {
            return "border-emerald-200 bg-emerald-50 text-emerald-800";
        }
        if (sectionBatchIds[section.id]) {
            return "border-amber-200 bg-amber-50 text-amber-800";
        }
        return "border-slate-200 bg-slate-50 text-slate-700";
    };

    const setIntakeDirty = (key: string, isDirty: boolean) => {
        setIntakeDirtyMap((prev) => {
            if (prev[key] === isDirty) {
                return prev;
            }

            return {
                ...prev,
                [key]: isDirty,
            };
        });
    };



    // Render step progress - clean, minimal design
    const renderProgress = () => (
        <div className="flex items-center justify-center gap-8 mb-8">
            {STEPS.map((step, index) => {
                const stepIndex = STEPS.findIndex(s => s.id === currentStep);
                const isCompleted = index < stepIndex;
                const isCurrent = step.id === currentStep;

                return (
                    <div key={step.id} className="flex items-center">
                        <div className={`
                            flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold
                            ${isCompleted ? "bg-emerald-600 text-white" :
                                isCurrent ? "bg-slate-900 text-white" :
                                    "bg-slate-200 text-slate-500"}
                        `}>
                            {isCompleted ? "✓" : index + 1}
                        </div>
                        <span className={`ml-2 text-sm ${isCurrent ? "font-semibold text-slate-900" : "text-slate-500"}`}>
                            {step.label}
                        </span>
                        {index < STEPS.length - 1 && (
                            <div className={`w-16 h-0.5 mx-6 ${isCompleted ? "bg-emerald-600" : "bg-slate-200"}`} />
                        )}
                    </div>
                );
            })}
        </div>
    );

    // Handle flow state banners
    if (state.flowState === "EXPIRED" && state.spe) {
        return (
            <div className="container mx-auto max-w-4xl p-6">
                <ExpiredBanner
                    expiresAt={state.spe.expires_at}
                    onClone={() => router.push("/quotes/new")}
                />
            </div>
        );
    }

    if (state.spe?.status === "rejected") {
        return (
            <div className="container mx-auto max-w-4xl p-6">
                <RejectedBanner
                    comment={state.spe?.manager_approval?.comment}
                    onRevise={() => router.push("/quotes/new")}
                />
            </div>
        );
    }

    return (
        <div className="container mx-auto max-w-5xl space-y-6 p-6">
            {/* Context Header - Clean notification */}
            {isNew && triggerCode && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <p className="text-sm font-medium text-amber-900">
                        {triggerText || "This shipment requires manual rate sourcing from agents."}
                    </p>
                </div>
            )}

            {/* Header - Clean and minimal */}
            <div className="mb-6 space-y-4">
                <PageBackButton
                    fallbackHref="/quotes"
                    returnTo={returnTo}
                    isDirty={hasPendingUnsavedWork}
                    confirmLeave={confirmLeave}
                />
                <Breadcrumb>
                    <BreadcrumbList>
                        <BreadcrumbItem>
                            <BreadcrumbLink href="/dashboard">Dashboard</BreadcrumbLink>
                        </BreadcrumbItem>
                        <BreadcrumbSeparator />
                        <BreadcrumbItem>
                            <BreadcrumbLink href="/quotes">Quotes</BreadcrumbLink>
                        </BreadcrumbItem>
                        <BreadcrumbSeparator />
                        <BreadcrumbItem>
                            <BreadcrumbPage>{isNew ? "New SPOT" : "SPOT Quote"}</BreadcrumbPage>
                        </BreadcrumbItem>
                    </BreadcrumbList>
                </Breadcrumb>

                <div className="ml-1 flex items-start justify-between gap-4">
                    <div>
                        <h1 className="text-2xl font-bold text-slate-900">
                            {isNew ? "New SPOT Quote" : "SPOT Quote"}
                        </h1>
                        {currentStep === "intake" && (
                            <p className="mt-1 text-sm text-slate-600">
                                Add the missing rates needed to complete this quote.
                            </p>
                        )}
                    </div>
                    <PageCancelButton
                        href="/quotes"
                        isDirty={hasPendingUnsavedWork}
                        confirmMessage="Discard quote changes?"
                        label="Cancel Quote"
                        className="shrink-0"
                    />
                </div>
            </div>

            {/* Progress */}
            {renderProgress()}

            {/* Shipment Summary (Always visible) */}
            <Card className="mb-6">
                <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">Shipment Summary</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4 xl:grid-cols-7">
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Customer</span>
                            <span className="font-bold text-slate-900">{displayCustomerName}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Route</span>
                            <span className="font-bold text-slate-900">
                                {originCode || state.spe?.shipment.origin_code} → {destCode || state.spe?.shipment.destination_code}
                            </span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Commodity</span>
                            <span className="font-bold text-slate-900">{commodity || state.spe?.shipment.commodity}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Weight</span>
                            <span className="font-bold text-slate-900">{weight || state.spe?.shipment.total_weight_kg} kg</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Pieces</span>
                            <span className="font-bold text-slate-900">{pieces || state.spe?.shipment.pieces}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Service Scope</span>
                            <span className="font-bold text-slate-900">{displayServiceScope}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Payment Terms</span>
                            <span className="font-bold text-slate-900">{displayPaymentTerm}</span>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Error display */}
            {state.error && (
                <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4">
                    <p className="text-sm font-medium text-red-800">{state.error}</p>
                    {state.quoteResult?.has_missing_rates && (
                        <div className="mt-2 text-sm text-red-700">
                            {formatMissingComponents(state.quoteResult.missing_components)?.length ? (
                                <p>
                                    Missing required components:{" "}
                                    <span className="font-semibold">
                                        {formatMissingComponents(state.quoteResult.missing_components)?.join(", ")}
                                    </span>
                                </p>
                            ) : null}
                            {state.quoteResult.completeness_notes && (
                                <p className="mt-1">{state.quoteResult.completeness_notes}</p>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Step Content */}

            {/* Step 1: Intake - Paste agent reply, AI analysis */}
            {currentStep === "intake" && !isMultiSourceIntake && (
                <ReplyPasteCard
                    speId={speId as string}
                    missingComponents={missingComponents}
                    sourceBatchId={primarySourceBatchId}
                    onAnalysisComplete={(result) => handleAnalysisComplete(result, "mixed")}
                    onDirtyChange={(isDirty) => setIntakeDirty("mixed", isDirty)}
                />
            )}

            {currentStep === "intake" && isMultiSourceIntake && (
                <div className="space-y-6">
                    <Card className="border-slate-200">
                        <CardHeader className="pb-3">
                            <CardTitle className="text-base font-semibold">Missing Source Intake</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-3 text-sm text-slate-700">
                            <p>
                                This quote needs multiple external inputs. Add each missing source below, then continue to review once all required sections are imported.
                            </p>
                            <div className="grid gap-3 md:grid-cols-3">
                                {intakeSections.map((section) => (
                                    <div
                                        key={section.id}
                                        className={`rounded-md border px-3 py-2 ${getSourceStatusClasses(section)}`}
                                    >
                                        <div className="font-medium">
                                            {section.title}
                                        </div>
                                        <div className="mt-1 text-xs">
                                            {getSourceStatusText(section)}
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </CardContent>
                    </Card>

                    {intakeSections.map((section) => (
                        <ReplyPasteCard
                            key={section.id}
                            speId={speId as string}
                            sourceBatchId={sectionBatchIds[section.id] || null}
                            title={section.title}
                            description={section.description}
                            sourceKind={section.sourceKind}
                            targetBucket={section.id}
                            sourceLabel={section.sourceLabel}
                            hideMissingMessage
                            onAnalysisComplete={(result) => handleAnalysisComplete(result, section.id)}
                            onDirtyChange={(isDirty) => setIntakeDirty(section.id, isDirty)}
                        />
                    ))}

                    <div className="flex justify-end">
                        <Button
                            onClick={() => {
                                userAdvancedToReviewRef.current = true;
                                setCurrentStep("review");
                            }}
                            disabled={!allMultiSourceSectionsReady}
                        >
                            Continue to Review
                        </Button>
                    </div>
                </div>
            )}

            {/* Step 2: Review - Rate entry form with AI suggestions */}
            {currentStep === "review" && (
                <div className="space-y-6">
                    {/* Back button */}
                    <Button
                        variant="outline"
                        onClick={() => {
                            userAdvancedToReviewRef.current = false;
                            setCurrentStep("intake");
                        }}
                        className="mb-4"
                    >
                        ← Back to Intake
                    </Button>

                    {sourceReviewSummaries.length > 0 && (
                        <Card className="border-slate-200">
                            <CardHeader className="pb-3">
                                <CardTitle className="text-base font-semibold">Imported Source Summary</CardTitle>
                            </CardHeader>
                            <CardContent className="space-y-4">
                                <div className="grid gap-3 md:grid-cols-2">
                                    {sourceReviewSummaries.map((summary) => (
                                        <div key={summary.id} className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
                                            <div className="flex items-start justify-between gap-3">
                                                <div>
                                                    <div className="font-medium text-slate-900">{summary.label}</div>
                                                    <div className="mt-1 text-sm text-slate-600">
                                                        {summary.sourceKind} source
                                                    </div>
                                                </div>
                                                <div className="rounded-full border border-slate-300 px-2 py-1 text-xs font-medium text-slate-700">
                                                    {summary.targetBucket === "mixed" ? "Mixed" : BUCKET_LABELS[summary.targetBucket]}
                                                </div>
                                            </div>
                                            <div className="mt-3 grid gap-2 text-sm text-slate-700 sm:grid-cols-3">
                                                <div>
                                                    <div className="text-xs uppercase tracking-wide text-slate-500">Lines</div>
                                                    <div className="font-medium">{summary.lineCount}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs uppercase tracking-wide text-slate-500">Currencies</div>
                                                    <div className="font-medium">{summary.currencies.join(", ") || "None"}</div>
                                                </div>
                                                <div>
                                                    <div className="text-xs uppercase tracking-wide text-slate-500">Buckets</div>
                                                    <div className="font-medium">
                                                        {summary.buckets.map((bucket) => BUCKET_LABELS[bucket]).join(", ") || "None"}
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    ))}
                                </div>

                                {overlapWarnings.length > 0 ? (
                                    <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
                                        <div className="text-sm font-medium text-amber-900">Review Warnings</div>
                                        <ul className="mt-2 space-y-2 text-sm text-amber-900">
                                            {overlapWarnings.map((warning) => (
                                                <li key={warning}>• {warning}</li>
                                            ))}
                                        </ul>
                                    </div>
                                ) : (
                                    <div className="rounded-md border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                                        Imported source batches align with the missing quote buckets. Review the lines below and confirm the final charge mix.
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Rate Entry Form with AI-suggested charges */}
                    <SpotRateEntryForm
                        onSubmit={handleSaveAndCreateQuote}
                        isLoading={state.isLoading}
                        initialCharges={reviewFormCharges}
                        suggestedCharges={analysisResult?.assertions || []}
                        shipmentType={resolvedShipmentType}
                        serviceScope={serviceScope}
                        missingComponents={missingComponents}
                        submitLabel="Confirm & Create Quote"
                        onSaveDraft={handleSaveDraft}
                    />

                    {/* Static disclaimer (acknowledgement is recorded on submit in backend flow) */}
                    <Card className="border-amber-200 bg-amber-50/60">
                        <CardContent className="pt-4">
                            <p className="text-sm text-amber-900">
                                Conditional SPOT disclaimer: rates are not guaranteed until carrier and space are confirmed.
                            </p>
                        </CardContent>
                    </Card>
                </div>
            )}


        </div >
    );
}

