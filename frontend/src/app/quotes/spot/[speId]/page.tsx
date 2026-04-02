"use client";

/**
 * SPOT Rate Entry Page
 * 
 * Streamlined 2-step flow:
 * 1. Intake (Submit) - Paste agent reply, AI analysis
 * 2. Review (Confirm & Create) - Review charges and create quote
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
    // Standard Rate charges are computed FROM COGS but are sell-side charges, so keep them visible.
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

const NON_ACTIONABLE_AI_WARNING_PATTERNS = [
    "validity not specified - assuming 72 hours",
    "routing not specified - may involve multiple legs",
    "space/acceptance not confirmed",
];

const sanitizeSummaryMessage = (message: string) =>
    message.replace(/^[^A-Za-z0-9]+/, "").trim();

const normalizeSummaryMessage = (message: string) => {
    const cleaned = sanitizeSummaryMessage(message);

    return cleaned
        .replace(/^AI:\s*/i, "")
        .replace(/^AI critic flagged possible missed charges:\s*/i, "Possible missed charges: ")
        .replace(/^AI critic flagged possible hallucinations:\s*/i, "Please verify these charges: ")
        .replace(/^AI returned unmapped charges requiring manual review:\s*/i, "Some imported charges need manual review: ")
        .replace(/^AI analysis failed:\s*/i, "Import check failed: ")
        .replace(/^AI intake did not produce any charge lines to review\.?$/i, "No charge lines were imported for review.")
        .replace(/^AI analysis is missing required rate or currency fields\.?$/i, "Some imported lines are missing rate or currency details.")
        .replace(/^(Line \d+): Low-confidence normalization for /i, "$1: Please verify the charge label for ");
};

const isActionableAiWarning = (warning: string) => {
    const normalized = normalizeSummaryMessage(warning).toLowerCase();
    return !NON_ACTIONABLE_AI_WARNING_PATTERNS.some((pattern) => normalized.includes(pattern));
};

const getSourceSummaryTitle = (label: string, targetBucket: SPEChargeLine["bucket"] | "mixed") => {
    const cleaned = label.replace(/\bAI\b/gi, "").replace(/\s{2,}/g, " ").trim();
    if (cleaned.toLowerCase() === "unified intake") return "Uploaded rates";
    if (cleaned) return cleaned;
    if (targetBucket === "mixed") return "Uploaded rates";
    return `${BUCKET_LABELS[targetBucket]} import`;
};

const getSourceSummarySubtitle = (bucket: SPEChargeLine["bucket"] | "mixed") => {
    if (bucket === "mixed") return "Imported lines are grouped for this quote";
    return `${BUCKET_LABELS[bucket]} lines are grouped for this quote`;
};

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

const formatListWithAnd = (items: string[]) => {
    if (items.length <= 1) return items[0] || "";
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
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
    const hasIntakeDrafts = useMemo(
        () => Object.values(intakeDirtyMap).some(Boolean),
        [intakeDirtyMap]
    );
    const hasPendingUnsavedWork =
        hasIntakeDrafts || Boolean(analysisResult) || (currentStep === "review" && !state.quoteResult);
    const confirmLeave = useUnsavedChangesGuard(hasPendingUnsavedWork);

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

    const missingRateLabels = useMemo(
        () => formatMissingComponents(missingComponents) || EMPTY_COMPONENTS,
        [missingComponents]
    );
    const intakeDescription = useMemo(() => {
        const autoSplitTargets = missingRateLabels.length
            ? formatListWithAnd(missingRateLabels)
            : "the right quote components";
        return `Paste email replies, upload PDFs, or enter all external rate details once. They will be sorted into ${autoSplitTargets}.`;
    }, [missingRateLabels]);

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
            if (state.spe.charges.length > 0) {
                // If we have charges, go to review step
                setCurrentStep(prev => prev === "review" ? prev : "review");
            } else {
                // Initial state - intake
                setCurrentStep("intake");
            }
        }
    }, [state.spe, state.flowState]);

    useEffect(() => {
        const sources = state.spe?.sources || [];
        if (!sources.length) {
            return;
        }
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

    const allReviewFormCharges = useMemo(() => {
        // Review form should only contain SPOT-entered/manual rates.
        // Exclude any DB standard-rate lines from the editable SPE payload.
        const candidateCharges = mergedFormCharges.filter(
            (charge) => !isBuySideCharge(charge) && !isStandardRateCharge(charge)
        );
        return candidateCharges;
    }, [mergedFormCharges]);

    const visibleReviewFormCharges = useMemo(() => {
        if (editableBuckets.length === 0) return allReviewFormCharges;
        const editableBucketSet = new Set(editableBuckets);
        return allReviewFormCharges.filter((charge) => editableBucketSet.has(charge.bucket));
    }, [allReviewFormCharges, editableBuckets]);

    const sourceReviewSummaries = useMemo(() => {
        const charges = (state.spe?.charges || EMPTY_CHARGES).filter(
            (charge) => !isBuySideCharge(charge) && !isStandardRateCharge(charge)
        );
        const visibleImportedCharges = visibleReviewFormCharges.filter(
            (charge) => !isBuySideCharge(charge) && !isStandardRateCharge(charge)
        );
        return (state.spe?.sources || []).map((source) => {
            const sourceCharges = charges.filter((charge) => charge.source_batch_id === source.id);
            const fallbackVisibleCharges =
                sourceCharges.length > 0
                    ? sourceCharges
                    : source.target_bucket === "mixed" && (state.spe?.sources?.length || 0) === 1
                        ? visibleImportedCharges
                        : [];
            const sourceCurrencies = Array.from(
                new Set((fallbackVisibleCharges.length > 0 ? fallbackVisibleCharges : sourceCharges).map((charge) => charge.currency))
            );
            const currencies = source.detected_currencies?.length
                ? source.detected_currencies
                : sourceCurrencies;
            const buckets = Array.from(
                new Set((fallbackVisibleCharges.length > 0 ? fallbackVisibleCharges : sourceCharges).map((charge) => charge.bucket))
            );
            const resolvedBuckets =
                buckets.length > 0
                    ? buckets
                    : source.target_bucket === "mixed"
                        ? editableBuckets
                        : [source.target_bucket];
            const actionableWarnings = (source.warnings || [])
                .map(normalizeSummaryMessage)
                .filter(isActionableAiWarning);
            const attentionItems = Array.from(
                new Set([
                    ...actionableWarnings,
                    ...(source.blocking_reasons || []).map(normalizeSummaryMessage),
                ])
            );
            return {
                id: source.id,
                label: getSourceSummaryTitle(source.label, source.target_bucket),
                targetBucket: source.target_bucket,
                lineCount: fallbackVisibleCharges.length || sourceCharges.length || source.charge_count || 0,
                currencies,
                buckets: resolvedBuckets,
                subtitle: getSourceSummarySubtitle(source.target_bucket),
                attentionItems,
                needsAttention: attentionItems.length > 0,
            };
        });
    }, [editableBuckets, state.spe?.charges, state.spe?.sources, visibleReviewFormCharges]);

    const intakeSafety = state.spe?.intake_safety;
    const quoteCreationBlocked = Boolean(intakeSafety && !intakeSafety.is_safe_to_quote);
    const hasAttentionItems = sourceReviewSummaries.some((summary) => summary.needsAttention);
    const totalAttentionItems = sourceReviewSummaries.reduce(
        (count, summary) => count + summary.attentionItems.length,
        0
    );
    const totalImportedLines = sourceReviewSummaries.reduce((count, summary) => count + summary.lineCount, 0);

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
    const speAlreadyReady = state.spe?.status === "ready" || Boolean(state.spe?.acknowledgement);

    // Handle saving charges, acknowledging, and creating the final quote in one flow
    const handleSaveAndCreateQuote = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        if (state.spe) {
            if (quoteCreationBlocked) {
                return;
            }
            if (!speAlreadyReady) {
                const spe = await actions.updateSPE(state.spe.id, {
                    charges,
                    conditions: {
                        space_not_confirmed: true,
                        airline_acceptance_not_confirmed: true,
                        rate_validity_hours: 72,
                        conditional_charges_present: charges.some(c => c.conditional),
                    }
                });

                if (!spe) {
                    return;
                }

                const success = await actions.submitAcknowledgement();
                if (!success) {
                    return;
                }
            }

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
        if (result.source_batch_id && targetBucket === "mixed") {
            setPrimarySourceBatchId(result.source_batch_id);
        }
        // Set the guard BEFORE the async reload so the useEffect doesn't fight us.
        userAdvancedToReviewRef.current = true;
        if (speId && !isNew) {
            // Backend persists auto-populated charges (AI + standard DB suggestions) into the SPE.
            // Reload before entering review so the form displays the latest draft charges.
            await loadSPE(speId);
        }
        setCurrentStep("review");
    };

    const setIntakeDirty = useCallback((key: string, isDirty: boolean) => {
        setIntakeDirtyMap((prev) => {
            if (prev[key] === isDirty) {
                return prev;
            }

            return {
                ...prev,
                [key]: isDirty,
            };
        });
    }, []);

    const handleMixedIntakeDirtyChange = useCallback(
        (isDirty: boolean) => {
            setIntakeDirty("mixed", isDirty);
        },
        [setIntakeDirty],
    );



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
                                Add all missing external rate inputs once. They will be split into the right charge sections.
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
                                {originCode || state.spe?.shipment.origin_code} {"->"} {destCode || state.spe?.shipment.destination_code}
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
            {currentStep === "intake" && (
                <ReplyPasteCard
                    speId={speId as string}
                    missingComponents={missingComponents}
                    sourceBatchId={primarySourceBatchId}
                    title="Rate Intake"
                    description={intakeDescription}
                    sourceKind="OTHER"
                    targetBucket="mixed"
                    sourceLabel="Uploaded rates"
                    onAnalysisComplete={(result) => handleAnalysisComplete(result, "mixed")}
                    onDirtyChange={handleMixedIntakeDirtyChange}
                />
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
                        {"<-"} Back to Intake
                    </Button>

                    {sourceReviewSummaries.length > 0 && (
                        <Card className="overflow-hidden border-slate-200/80 bg-white shadow-[0_22px_70px_-38px_rgba(15,23,42,0.35)]">
                            <CardHeader className="border-b border-slate-200 bg-[linear-gradient(135deg,#f8fafc_0%,#eef6ff_45%,#f7fffb_100%)] pb-6">
                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                    <div className="max-w-3xl">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-sky-700">
                                            Imported rates
                                        </div>
                                        <CardTitle className="mt-2 text-2xl font-semibold text-slate-950">
                                            Imported quote inputs are organized
                                        </CardTitle>
                                        <p className="mt-2 text-sm leading-6 text-slate-600">
                                            Review the imported lines below. Only items that still need a decision are highlighted.
                                        </p>
                                    </div>
                                    <div className="grid gap-3 rounded-3xl border border-white/70 bg-white/85 p-4 shadow-sm backdrop-blur sm:grid-cols-3 lg:min-w-[360px]">
                                        <div>
                                            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                Sources
                                            </div>
                                            <div className="mt-2 text-2xl font-semibold text-slate-950">
                                                {sourceReviewSummaries.length}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                Imported lines
                                            </div>
                                            <div className="mt-2 text-2xl font-semibold text-slate-950">
                                                {totalImportedLines}
                                            </div>
                                        </div>
                                        <div>
                                            <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                Needs check
                                            </div>
                                            <div className={`mt-2 text-2xl font-semibold ${hasAttentionItems ? "text-amber-700" : "text-emerald-700"}`}>
                                                {hasAttentionItems ? totalAttentionItems : 0}
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            </CardHeader>
                            <CardContent className="space-y-5 p-6">
                                <div className="grid gap-4">
                                    {sourceReviewSummaries.map((summary) => (
                                        <section
                                            key={summary.id}
                                            className="grid gap-5 rounded-[28px] border border-slate-200 bg-white p-5 shadow-[0_18px_50px_-40px_rgba(15,23,42,0.45)] lg:grid-cols-[minmax(0,1.35fr)_minmax(280px,0.8fr)]"
                                        >
                                            <div className="space-y-5">
                                                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                                                    <div>
                                                        <div className="font-semibold text-slate-950">{summary.label}</div>
                                                        <div className="mt-1 text-sm leading-6 text-slate-600">
                                                            {summary.subtitle}
                                                        </div>
                                                    </div>
                                                    <div className="flex flex-wrap gap-2">
                                                        <div className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">
                                                            {summary.targetBucket === "mixed" ? "Mixed input" : BUCKET_LABELS[summary.targetBucket]}
                                                        </div>
                                                        <div
                                                            className={`rounded-full px-3 py-1 text-xs font-semibold ${
                                                                summary.needsAttention
                                                                    ? "border border-amber-200 bg-amber-50 text-amber-800"
                                                                    : "border border-emerald-200 bg-emerald-50 text-emerald-800"
                                                            }`}
                                                        >
                                                            {summary.needsAttention
                                                                ? `${summary.attentionItems.length} item${summary.attentionItems.length === 1 ? "" : "s"} to check`
                                                                : "Ready to confirm"}
                                                        </div>
                                                    </div>
                                                </div>
                                                <div className="grid gap-3 sm:grid-cols-3">
                                                    <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
                                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                            Lines
                                                        </div>
                                                        <div className="mt-2 text-2xl font-semibold text-slate-950">{summary.lineCount}</div>
                                                    </div>
                                                    <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
                                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                            Currency
                                                        </div>
                                                        <div className="mt-2 text-lg font-semibold text-slate-950">
                                                            {summary.currencies.join(", ") || "None"}
                                                        </div>
                                                    </div>
                                                    <div className="rounded-2xl border border-slate-200 bg-slate-50/80 px-4 py-3">
                                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-slate-500">
                                                            Applied to
                                                        </div>
                                                        <div className="mt-2 text-lg font-semibold text-slate-950">
                                                            {summary.buckets.map((bucket) => BUCKET_LABELS[bucket]).join(", ") || "None"}
                                                        </div>
                                                    </div>
                                                </div>
                                            </div>
                                            <aside
                                                className={`rounded-[24px] border px-4 py-4 ${
                                                    summary.attentionItems.length > 0
                                                        ? "border-amber-200 bg-[linear-gradient(180deg,#fff8eb_0%,#fffdf8_100%)]"
                                                        : "border-emerald-200 bg-[linear-gradient(180deg,#edfcf4_0%,#f7fffb_100%)]"
                                                }`}
                                            >
                                                <div className={`text-[11px] font-semibold uppercase tracking-[0.24em] ${summary.attentionItems.length > 0 ? "text-amber-800" : "text-emerald-800"}`}>
                                                    {summary.attentionItems.length > 0 ? "Check before sending" : "Ready to send"}
                                                </div>
                                                <p className={`mt-3 text-sm leading-6 ${summary.attentionItems.length > 0 ? "text-amber-950" : "text-emerald-950"}`}>
                                                    {summary.attentionItems.length > 0
                                                        ? "These are the only imported items that still need your attention before you send the quote."
                                                        : "This imported source is already organized and ready to be included in the final quote."}
                                                </p>
                                                {summary.attentionItems.length > 0 ? (
                                                    <ul className="mt-4 space-y-3 text-sm leading-6 text-amber-950">
                                                        {summary.attentionItems.map((item) => (
                                                            <li key={`${summary.id}-${item}`} className="flex gap-3">
                                                                <span className="mt-2 h-1.5 w-1.5 rounded-full bg-amber-500" />
                                                                <span>{item}</span>
                                                            </li>
                                                        ))}
                                                    </ul>
                                                ) : (
                                                    <div className="mt-4 rounded-2xl border border-emerald-200/80 bg-white/70 px-4 py-3 text-sm text-emerald-900">
                                                        No issues need review for this import.
                                                    </div>
                                                )}
                                            </aside>
                                        </section>
                                    ))}
                                </div>

                                {overlapWarnings.length > 0 ? (
                                    <div className="rounded-[24px] border border-amber-200 bg-[linear-gradient(135deg,#fff8eb_0%,#fffdf8_100%)] px-5 py-4">
                                        <div className="text-sm font-semibold text-amber-900">Check pricing mix</div>
                                        <p className="mt-1 text-sm text-amber-900">
                                            Some imported lines overlap with existing quote charges. Pick the final mix below before confirming.
                                        </p>
                                        <ul className="mt-3 space-y-2 text-sm text-amber-900">
                                            {overlapWarnings.map((warning) => (
                                                <li key={warning} className="flex gap-3">
                                                    <span className="mt-2 h-1.5 w-1.5 rounded-full bg-amber-500" />
                                                    <span>{warning}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                ) : hasAttentionItems ? (
                                    <div className="rounded-[24px] border border-sky-200 bg-[linear-gradient(135deg,#f5fbff_0%,#f8fcff_100%)] px-5 py-4 text-sm text-sky-950">
                                        The imported lines are already assigned to the right quote sections. Review the highlighted items below, then confirm the quote.
                                    </div>
                                ) : (
                                    <div className="rounded-[24px] border border-emerald-200 bg-[linear-gradient(135deg,#edfcf4_0%,#f8fffb_100%)] px-5 py-4 text-sm text-emerald-900">
                                        Imported charges match the missing parts of this quote and are ready to confirm.
                                    </div>
                                )}
                            </CardContent>
                        </Card>
                    )}

                    {/* Rate Entry Form with AI-suggested charges */}
                    <SpotRateEntryForm
                        onSubmit={handleSaveAndCreateQuote}
                        isLoading={state.isLoading}
                        initialCharges={allReviewFormCharges}
                        suggestedCharges={analysisResult?.assertions || []}
                        shipmentType={resolvedShipmentType}
                        serviceScope={serviceScope}
                        missingComponents={missingComponents}
                        submitLabel={speAlreadyReady ? "Create Quote" : "Confirm & Create Quote"}
                        submitLoadingText={speAlreadyReady ? "Creating quote..." : "Confirming and creating quote..."}
                        submitDisabled={quoteCreationBlocked}
                        submitDisabledReason={quoteCreationBlocked ? "Quote creation is temporarily unavailable." : null}
                        onSaveDraft={speAlreadyReady ? undefined : handleSaveDraft}
                    />

                    {/* Static disclaimer (acknowledgement is recorded on submit in backend flow) */}
                    <Card className="border-amber-200 bg-amber-50/60">
                        <CardContent className="pt-4">
                            <p className="text-sm text-amber-900">
                                {speAlreadyReady
                                    ? "This SPOT acknowledgement is already recorded. Creating the quote will use the locked imported charges."
                                    : "Final submission records the SPOT acknowledgement and creates the quote from the imported charges. Rates are still conditional until carrier and space are confirmed."}
                            </p>
                        </CardContent>
                    </Card>
                </div>
            )}


        </div >
    );
}


