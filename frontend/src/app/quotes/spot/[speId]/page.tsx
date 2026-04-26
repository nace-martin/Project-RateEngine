"use client";

/**
 * SPOT Rate Entry Page
 * 
 * SPOT workflow:
 * 1. Import - Paste agent reply or upload source data
 * 2. Review - Resolve imported-rate exceptions
 * 3. Confirm - Create quote from reviewed charges
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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
import { getEffectiveProductCode, getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";
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

type Step = "intake" | "review";
type DisplayStep = Step | "confirm";

const STEPS: { id: DisplayStep; label: string; description: string }[] = [
    { id: "intake", label: "1. Import", description: "Paste or upload rates" },
    { id: "review", label: "2. Review", description: "Resolve exceptions" },
    { id: "confirm", label: "3. Confirm", description: "Create quote" },
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

type ReviewIssueKind = "unmapped" | "ambiguous" | "lowConfidence" | "conditional";
type ReviewMode = "issues" | "allCharges";

type SourceLineIssue = {
    key: string;
    label: string;
    issueKinds: ReviewIssueKind[];
    bucketLabels: string[];
    sourceLabels: string[];
    details: string[];
    occurrenceCount: number;
};

type ImportedReviewLine = {
    key: string;
    chargeLineId?: string;
    label: string;
    amountDisplay: string;
    unitLabel: string;
    bucketLabel: string;
    sourceLabel: string;
    issueKinds: ReviewIssueKind[];
    details: string[];
    canReviewInSheet: boolean;
    charge: SPEChargeLine;
};

type SourceReviewSummary = {
    id: string;
    label: string;
    targetBucket: SPEChargeLine["bucket"] | "mixed";
    lineCount: number;
    currencies: string[];
    buckets: SPEChargeLine["bucket"][];
    subtitle: string;
    counts: {
        unmapped: number;
        lowConfidence: number;
        conditional: number;
    };
    lineIssues: SourceLineIssue[];
    generalChecks: string[];
};

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

const getAnalysisSignalCount = (source: { analysis_summary_json?: Record<string, unknown> }, key: string) => {
    const value = source.analysis_summary_json?.[key];
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
};

const normalizeIssueLabel = (label: string) => sanitizeSummaryMessage(label).replace(/^['"]|['"]$/g, "").trim();

const LOW_CONFIDENCE_WARNING_PATTERN =
    /^Line \d+:\s+(?:Please verify the charge label for|Low-confidence normalization for)\s+'([^']+)'/i;
const UNMAPPED_WARNING_PATTERN = /^Line \d+:\s+Unmapped charge\s+'([^']+)'/i;
const MANUAL_REVIEW_WARNING_PATTERN = /^Some imported charges need manual review:\s*(.+)$/i;
const COUNT_ONLY_WARNING_PATTERNS = [
    /^\d+\s+extracted charge\(s\) could not be mapped cleanly\.?$/i,
    /^\d+\s+extracted charge line\(s\) were low-confidence\.?$/i,
    /^\d+\s+extracted charge line\(s\) are conditional\.?$/i,
    /^Some imported charges need manual review:\s*/i,
    /^Line \d+:/i,
];

const isCountOnlySummaryWarning = (warning: string) =>
    COUNT_ONLY_WARNING_PATTERNS.some((pattern) => pattern.test(warning));

const parseLineIssueWarning = (warning: string) => {
    const lowConfidenceMatch = warning.match(LOW_CONFIDENCE_WARNING_PATTERN);
    if (lowConfidenceMatch) {
        return {
            labels: [normalizeIssueLabel(lowConfidenceMatch[1] || "")],
            kind: "lowConfidence" as const,
            detail: warning,
        };
    }

    const unmappedMatch = warning.match(UNMAPPED_WARNING_PATTERN);
    if (unmappedMatch) {
        return {
            labels: [normalizeIssueLabel(unmappedMatch[1] || "")],
            kind: "unmapped" as const,
            detail: "Needs manual product mapping.",
        };
    }

    const manualReviewMatch = warning.match(MANUAL_REVIEW_WARNING_PATTERN);
    if (manualReviewMatch) {
        return {
            labels: manualReviewMatch[1]
                .split(",")
                .map((label) => normalizeIssueLabel(label))
                .filter(Boolean),
            kind: "unmapped" as const,
            detail: "Needs manual product mapping.",
        };
    }

    return null;
};

const issueKindMeta: Record<ReviewIssueKind, { label: string; className: string }> = {
    unmapped: {
        label: "Needs review",
        className: "border-amber-200 bg-amber-50 text-amber-800",
    },
    ambiguous: {
        label: "Ambiguous",
        className: "border-rose-200 bg-rose-50 text-rose-800",
    },
    lowConfidence: {
        label: "Low confidence",
        className: "border-sky-200 bg-sky-50 text-sky-800",
    },
    conditional: {
        label: "Conditional",
        className: "border-slate-200 bg-slate-50 text-slate-700",
    },
};

const issueKindPriority: Record<ReviewIssueKind, number> = {
    unmapped: 0,
    ambiguous: 1,
    lowConfidence: 2,
    conditional: 3,
};

const getPrimaryIssueKind = (issueKinds: ReviewIssueKind[]) =>
    [...issueKinds].sort((left, right) => issueKindPriority[left] - issueKindPriority[right])[0] || "conditional";

const getIssueProblemMessage = (issueKinds: ReviewIssueKind[]) => {
    const primaryIssue = getPrimaryIssueKind(issueKinds);
    if (primaryIssue === "unmapped") {
        return "Choose the correct ProductCode before creating the quote.";
    }
    if (primaryIssue === "ambiguous") {
        return "Multiple ProductCodes matched. Confirm the correct one.";
    }
    if (primaryIssue === "lowConfidence") {
        return "Check the normalized charge label before confirming.";
    }
    return "Confirm whether this conditional charge should stay in the quote.";
};

const humanizeEnum = (value?: string | null) => {
    const normalized = String(value || "").trim();
    if (!normalized) return "Not recorded";
    return normalized
        .split("_")
        .filter(Boolean)
        .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
        .join(" ");
};

const formatProductCodeSummary = (productCode?: SPEChargeLine["resolved_product_code"] | null) => {
    if (!productCode?.code) return "Not recorded";
    return productCode.description ? `${productCode.code} - ${productCode.description}` : productCode.code;
};

const getChargeStatusLabel = (charge: SPEChargeLine) => {
    if (charge.manual_resolution_status === "RESOLVED") return "Manually resolved";
    if (charge.normalization_status === "MATCHED") return "Matched";
    if (charge.normalization_status === "AMBIGUOUS") return "Ambiguous";
    if (charge.normalization_status === "UNMAPPED") return "Needs review";
    return "Not normalized";
};

const chargeUnitLabel = (unit?: SPEChargeLine["unit"]) => {
    if (unit === "per_kg") return "Per KG";
    if (unit === "flat") return "Flat";
    if (unit === "per_awb") return "Per AWB";
    if (unit === "per_shipment") return "Per shipment";
    if (unit === "percentage") return "Percentage";
    if (unit === "per_trip") return "Per trip";
    if (unit === "per_set") return "Per set";
    if (unit === "per_man") return "Per man";
    if (unit === "min_or_per_kg") return "Min or per KG";
    return "Unit";
};

const formatChargeAmount = (charge: SPEChargeLine) => {
    const amount = String(charge.amount || "").trim();
    if (!amount) return charge.currency || "";
    return `${amount} ${charge.currency || ""}`.trim();
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

    const sourceReviewSummaries = useMemo<SourceReviewSummary[]>(() => {
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
            const displayCharges = fallbackVisibleCharges.length > 0 ? fallbackVisibleCharges : sourceCharges;
            const lineIssueMap = new Map<
                string,
                {
                    label: string;
                    issueKinds: Set<ReviewIssueKind>;
                    bucketLabels: Set<string>;
                    sourceLabels: Set<string>;
                    details: Set<string>;
                    occurrenceCount: number;
                }
            >();
            const addLineIssue = (
                rawLabel: string,
                issueKind: ReviewIssueKind,
                detail: string,
                bucket?: SPEChargeLine["bucket"]
            ) => {
                const label = normalizeIssueLabel(rawLabel);
                if (!label) return;

                const key = `${label.toLowerCase()}|${bucket || source.target_bucket || "mixed"}`;
                const existing = lineIssueMap.get(key) || {
                    label,
                    issueKinds: new Set<ReviewIssueKind>(),
                    bucketLabels: new Set<string>(),
                    sourceLabels: new Set<string>(),
                    details: new Set<string>(),
                    occurrenceCount: 0,
                };
                existing.issueKinds.add(issueKind);
                if (bucket) {
                    existing.bucketLabels.add(BUCKET_LABELS[bucket]);
                } else if (source.target_bucket !== "mixed") {
                    existing.bucketLabels.add(BUCKET_LABELS[source.target_bucket]);
                }
                existing.sourceLabels.add(getSourceSummaryTitle(source.label, source.target_bucket));
                if (detail) existing.details.add(detail);
                existing.occurrenceCount += 1;
                lineIssueMap.set(key, existing);
            };

            for (const charge of displayCharges) {
                const chargeLabel = charge.source_label || charge.description;
                if (
                    charge.manual_resolution_status !== "RESOLVED" &&
                    charge.normalization_status === "UNMAPPED"
                ) {
                    addLineIssue(chargeLabel, "unmapped", "Needs manual product mapping.", charge.bucket);
                }
                if (
                    charge.manual_resolution_status !== "RESOLVED" &&
                    charge.normalization_status === "AMBIGUOUS"
                ) {
                    addLineIssue(
                        chargeLabel,
                        "ambiguous",
                        "Multiple product matches were found. Confirm the correct mapping.",
                        charge.bucket
                    );
                }
                if (charge.conditional) {
                    addLineIssue(
                        chargeLabel,
                        "conditional",
                        "Conditional charge. Confirm it should stay in the quote.",
                        charge.bucket
                    );
                }
            }

            for (const warning of actionableWarnings) {
                const parsed = parseLineIssueWarning(warning);
                if (!parsed) continue;
                for (const label of parsed.labels) {
                    addLineIssue(label, parsed.kind, parsed.detail);
                }
            }

            const generalChecks = attentionItems.filter((item) => !isCountOnlySummaryWarning(item));
            return {
                id: source.id,
                label: getSourceSummaryTitle(source.label, source.target_bucket),
                targetBucket: source.target_bucket,
                lineCount: fallbackVisibleCharges.length || sourceCharges.length || source.charge_count || 0,
                currencies,
                buckets: resolvedBuckets,
                subtitle: getSourceSummarySubtitle(source.target_bucket),
                counts: {
                    unmapped: getAnalysisSignalCount(source, "unmapped_line_count"),
                    lowConfidence: getAnalysisSignalCount(source, "low_confidence_line_count"),
                    conditional: getAnalysisSignalCount(source, "conditional_charge_count"),
                },
                lineIssues: Array.from(lineIssueMap.entries()).map(([key, item]) => ({
                    key,
                    label: item.label,
                    issueKinds: Array.from(item.issueKinds.values()),
                    bucketLabels: Array.from(item.bucketLabels.values()),
                    sourceLabels: Array.from(item.sourceLabels.values()),
                    details: Array.from(item.details.values()),
                    occurrenceCount: item.occurrenceCount,
                })),
                generalChecks,
            };
        });
    }, [editableBuckets, state.spe?.charges, state.spe?.sources, visibleReviewFormCharges]);

    const intakeSafety = state.spe?.intake_safety;
    const quoteCreationBlocked = Boolean(intakeSafety && !intakeSafety.is_safe_to_quote);
    const totalImportedLines = sourceReviewSummaries.reduce((count, summary) => count + summary.lineCount, 0);
    const importedReviewCounts = useMemo(
        () =>
            sourceReviewSummaries.reduce(
                (totals, summary) => ({
                    unmapped: totals.unmapped + summary.counts.unmapped,
                    lowConfidence: totals.lowConfidence + summary.counts.lowConfidence,
                    conditional: totals.conditional + summary.counts.conditional,
                }),
                { unmapped: 0, lowConfidence: 0, conditional: 0 }
            ),
        [sourceReviewSummaries]
    );
    const matchedImportedLineCount = useMemo(
        () =>
            visibleReviewFormCharges.filter((charge) => {
                if (charge.manual_resolution_status === "RESOLVED") return true;
                return charge.normalization_status === "MATCHED";
            }).length,
        [visibleReviewFormCharges]
    );
    const sourceLabelById = useMemo(() => {
        const entries: Array<[string, string]> = (state.spe?.sources || []).map((source) => [
            source.id,
            getSourceSummaryTitle(source.label, source.target_bucket),
        ]);
        return new Map(entries);
    }, [state.spe?.sources]);

    const reviewLines = useMemo(() => {
        const affected: ImportedReviewLine[] = [];
        const unaffected: ImportedReviewLine[] = [];

        for (const charge of visibleReviewFormCharges) {
            const issueKinds = new Set<ReviewIssueKind>();
            const details = new Set<string>();
            const normalizedLabel = normalizeIssueLabel(
                charge.normalized_label || charge.source_label || charge.description || ""
            );
            const source = state.spe?.sources?.find((item) => item.id === charge.source_batch_id);
            const actionableWarnings = (source?.warnings || [])
                .map(normalizeSummaryMessage)
                .filter(isActionableAiWarning);

            if (
                charge.manual_resolution_status !== "RESOLVED" &&
                charge.normalization_status === "UNMAPPED"
            ) {
                issueKinds.add("unmapped");
                details.add("Needs manual product mapping.");
            }
            if (
                charge.manual_resolution_status !== "RESOLVED" &&
                charge.normalization_status === "AMBIGUOUS"
            ) {
                issueKinds.add("ambiguous");
                details.add("Multiple product matches were found. Confirm the correct mapping.");
            }
            if (charge.conditional) {
                issueKinds.add("conditional");
                details.add("Conditional charge. Confirm it should stay in the quote.");
            }

            for (const warning of actionableWarnings) {
                const parsed = parseLineIssueWarning(warning);
                if (!parsed) continue;
                if (
                    parsed.kind === "lowConfidence" &&
                    parsed.labels.some((label) => normalizeIssueLabel(label) === normalizedLabel)
                ) {
                    issueKinds.add("lowConfidence");
                    details.add("AI normalization was low confidence. Verify the label before confirming.");
                }
            }

            const reviewLine: ImportedReviewLine = {
                key: charge.id || `${charge.bucket}-${charge.description}-${charge.amount}-${charge.currency}`,
                chargeLineId: charge.id,
                label: getSpotChargeDisplayLabel(charge, { includeProductCode: true }),
                amountDisplay: formatChargeAmount(charge),
                unitLabel: chargeUnitLabel(charge.unit),
                bucketLabel: BUCKET_LABELS[charge.bucket],
                sourceLabel:
                    sourceLabelById.get(charge.source_batch_id || "") ||
                    charge.source_batch_label ||
                    "Imported rates",
                issueKinds: Array.from(issueKinds.values()),
                details: Array.from(details.values()),
                canReviewInSheet:
                    Boolean(charge.id) &&
                    charge.manual_resolution_status !== "RESOLVED" &&
                    (charge.normalization_status === "UNMAPPED" ||
                        charge.normalization_status === "AMBIGUOUS"),
                charge,
            };

            if (reviewLine.issueKinds.length > 0) {
                affected.push(reviewLine);
            } else {
                unaffected.push(reviewLine);
            }
        }

        const sortLines = (lines: ImportedReviewLine[]) =>
            lines.sort((left, right) => {
                const leftPriority = issueKindPriority[getPrimaryIssueKind(left.issueKinds)];
                const rightPriority = issueKindPriority[getPrimaryIssueKind(right.issueKinds)];
                if (leftPriority !== rightPriority) {
                    return leftPriority - rightPriority;
                }
                return left.label.localeCompare(right.label);
            });

        return {
            affected: sortLines(affected),
            unaffected: sortLines(unaffected),
        };
    }, [sourceLabelById, state.spe?.sources, visibleReviewFormCharges]);
    const groupedLineIssues: SourceLineIssue[] = [];
    const expandedIssueRows: Record<string, boolean> = {};

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
    const importWideChecks = useMemo(
        () =>
            Array.from(
                new Set([
                    ...sourceReviewSummaries.flatMap((summary) => summary.generalChecks),
                    ...overlapWarnings,
                ])
            ),
        [overlapWarnings, sourceReviewSummaries]
    );
    const [activeReviewRequest, setActiveReviewRequest] = useState<{
        chargeLineId: string;
        openManualReview: boolean;
        requestKey: number;
    } | null>(null);
    const [reviewMode, setReviewMode] = useState<ReviewMode>("issues");
    const [activeIssueDetails, setActiveIssueDetails] = useState<ImportedReviewLine | null>(null);
    const hasReviewActions =
        importedReviewCounts.unmapped > 0 ||
        importedReviewCounts.lowConfidence > 0 ||
        importedReviewCounts.conditional > 0 ||
        reviewLines.affected.length > 0 ||
        importWideChecks.length > 0;

    // Handle saving charges, acknowledging, and creating the final quote in one flow
    const handleSaveAndCreateQuote = async (
        charges: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>
    ) => {
        if (state.spe) {
            if (quoteCreationBlocked) {
                return;
            }
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
    const handleSaveDraft = async (
        charges: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>
    ) => {
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

    const handleReviewLine = useCallback((line: ImportedReviewLine) => {
        if (!line.chargeLineId) return;
        setReviewMode("allCharges");
        setActiveReviewRequest({
            chargeLineId: line.chargeLineId,
            openManualReview: line.canReviewInSheet,
            requestKey: Date.now(),
        });
    }, []);
    const toggleIssueDetails = useCallback((key: string) => {
        void key;
    }, []);



    // Render step progress - clean, minimal design
    const renderProgress = () => (
        <div className="flex items-center justify-center gap-8 mb-8">
            {STEPS.map((step, index) => {
                const displayStep: DisplayStep =
                    currentStep === "intake" ? "intake" : (reviewMode === "allCharges" ? "confirm" : "review");
                const stepIndex = STEPS.findIndex(s => s.id === displayStep);
                const isCompleted = index < stepIndex;
                const isCurrent = step.id === displayStep;

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
                        {"<-"} Back to Import
                    </Button>

                    <Card className="overflow-hidden border-slate-200/80 bg-white shadow-[0_22px_70px_-44px_rgba(15,23,42,0.55)]">
                        <CardHeader className="border-b border-slate-800 bg-[linear-gradient(135deg,#071426_0%,#0f2744_58%,#0b5aa8_100%)] pb-5 text-white">
                            <div className="space-y-4">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                                    <div className="max-w-3xl">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-sky-200">
                                            RateEngine SPOT
                                        </div>
                                        <CardTitle className="mt-2 text-2xl font-semibold text-white">
                                            AI SPOT Rate Review
                                        </CardTitle>
                                        <p className="mt-2 text-sm leading-6 text-sky-100">
                                            Rates extracted and organized. Review exceptions before quote creation.
                                        </p>
                                    </div>
                                    <Tabs value={reviewMode} onValueChange={(value) => setReviewMode(value as ReviewMode)}>
                                        <TabsList className="h-auto border border-white/15 bg-white/10 p-1 text-white">
                                            <TabsTrigger value="issues">
                                                Needs Review ({reviewLines.affected.length})
                                            </TabsTrigger>
                                            <TabsTrigger value="allCharges">
                                                All Charges ({visibleReviewFormCharges.length})
                                            </TabsTrigger>
                                        </TabsList>
                                    </Tabs>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-4">
                                    <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 shadow-sm">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-100">
                                            Imported
                                        </div>
                                        <div className="mt-2 text-2xl font-semibold text-white">
                                            {totalImportedLines}
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 shadow-sm">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-100">
                                            Needs review
                                        </div>
                                        <div className={`mt-2 text-2xl font-semibold ${reviewLines.affected.length > 0 ? "text-amber-200" : "text-emerald-200"}`}>
                                            {reviewLines.affected.length}
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 shadow-sm">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-100">
                                            Matched
                                        </div>
                                        <div className="mt-2 text-2xl font-semibold text-emerald-200">
                                            {matchedImportedLineCount}
                                        </div>
                                    </div>
                                    <div className="rounded-xl border border-white/15 bg-white/10 px-4 py-3 shadow-sm">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.2em] text-sky-100">
                                            Conditional
                                        </div>
                                        <div className={`mt-2 text-2xl font-semibold ${importedReviewCounts.conditional > 0 ? "text-amber-200" : "text-emerald-200"}`}>
                                            {importedReviewCounts.conditional}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        </CardHeader>
                            <CardContent className="p-6">
                                <Tabs value={reviewMode} onValueChange={(value) => setReviewMode(value as ReviewMode)}>
                                    <TabsContent value="issues" className="mt-0 space-y-5">
                                        {reviewLines.affected.length > 0 ? (
                                            <>
                                                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                                                    Resolve these lines before creating the quote.
                                                </div>
                                                <section className="space-y-3">
                                                    <div className="flex items-end justify-between gap-3">
                                                        <div>
                                                            <div className="text-sm font-semibold text-slate-950">Issue queue</div>
                                                            <p className="mt-1 text-sm text-slate-600">
                                                                Only lines that need a decision are shown here.
                                                            </p>
                                                        </div>
                                                        {reviewLines.unaffected.length > 0 ? (
                                                            <div className="text-sm text-slate-500">
                                                                {reviewLines.unaffected.length} ready line{reviewLines.unaffected.length === 1 ? "" : "s"} hidden in All Charges
                                                            </div>
                                                        ) : null}
                                                    </div>
                                                    <div className="space-y-3">
                                                        {reviewLines.affected.map((line) => (
                                                            <div
                                                                key={line.key}
                                                                className="rounded-xl border border-slate-200 bg-white px-4 py-4 shadow-sm"
                                                            >
                                                                <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                                                                    <div className="min-w-0 space-y-2">
                                                                        <div className="flex flex-wrap items-center gap-2">
                                                                            {line.issueKinds.map((kind) => (
                                                                                <Badge
                                                                                    key={`${line.key}-${kind}`}
                                                                                    variant="outline"
                                                                                    className={issueKindMeta[kind].className}
                                                                                >
                                                                                    {issueKindMeta[kind].label}
                                                                                </Badge>
                                                                            ))}
                                                                        </div>
                                                                        <div>
                                                                            <div className="text-base font-semibold text-slate-950">{line.label}</div>
                                                                            <div className="mt-1 text-sm text-slate-600">
                                                                                {line.amountDisplay} / {line.unitLabel}
                                                                            </div>
                                                                        </div>
                                                                        <div className="text-sm font-medium text-slate-800">
                                                                            {getIssueProblemMessage(line.issueKinds)}
                                                                        </div>
                                                                        <div className="text-xs text-slate-500">
                                                                            {line.bucketLabel} / {line.sourceLabel}
                                                                        </div>
                                                                    </div>
                                                                    <div className="flex shrink-0 gap-2">
                                                                        <Button
                                                                            type="button"
                                                                            size="sm"
                                                                            onClick={() => handleReviewLine(line)}
                                                                            disabled={!line.chargeLineId}
                                                                        >
                                                                            Resolve
                                                                        </Button>
                                                                        <Button
                                                                            type="button"
                                                                            variant="ghost"
                                                                            size="sm"
                                                                            onClick={() => setActiveIssueDetails(line)}
                                                                        >
                                                                            Details
                                                                        </Button>
                                                                    </div>
                                                                </div>
                                                            </div>
                                                        ))}
                                                    </div>
                                                </section>
                                            </>
                                        ) : (
                                            <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-900">
                                                No imported lines need action right now. Switch to All Charges if you want to review the full list before confirming.
                                            </div>
                                        )}

                                        {importWideChecks.length > 0 ? (
                                            <details className="rounded-[24px] border border-slate-200 bg-slate-50/70 px-5 py-4">
                                                <summary className="cursor-pointer text-sm font-medium text-slate-700">
                                                    Other checks ({importWideChecks.length})
                                                </summary>
                                                <ul className="mt-3 space-y-2 text-sm text-slate-700">
                                                    {importWideChecks.map((warning) => (
                                                        <li key={warning}>{warning}</li>
                                                    ))}
                                                </ul>
                                            </details>
                                        ) : null}
                                    </TabsContent>

                                    <TabsContent value="allCharges" className="mt-0 space-y-5">
                                        <div className="rounded-[24px] border border-slate-200 bg-slate-50/80 px-5 py-4 text-sm text-slate-700">
                                            Full charge list for editing and final confirmation. Use Needs Review to stay focused on only the lines that still need a decision.
                                        </div>

                                        <SpotRateEntryForm
                                            onSubmit={handleSaveAndCreateQuote}
                                            isLoading={state.isLoading}
                                            initialCharges={allReviewFormCharges}
                                            suggestedCharges={analysisResult?.assertions || []}
                                            shipmentType={resolvedShipmentType}
                                            serviceScope={serviceScope}
                                            missingComponents={EMPTY_COMPONENTS}
                                            submitLabel="Confirm & Create Quote"
                                            submitDisabled={quoteCreationBlocked}
                                            submitDisabledReason={quoteCreationBlocked ? "Quote creation is temporarily unavailable." : null}
                                            onSaveDraft={handleSaveDraft}
                                            onManualResolveChargeLine={actions.manuallyResolveChargeLine}
                                            productCodeDomain={resolvedShipmentType}
                                            reviewRequest={activeReviewRequest}
                                        />

                                        {importWideChecks.length > 0 ? (
                                            <details className="rounded-[24px] border border-slate-200 bg-slate-50/70 px-5 py-4">
                                                <summary className="cursor-pointer text-sm font-medium text-slate-700">
                                                    Other checks ({importWideChecks.length})
                                                </summary>
                                                <ul className="mt-3 space-y-2 text-sm text-slate-700">
                                                    {importWideChecks.map((warning) => (
                                                        <li key={warning}>{warning}</li>
                                                    ))}
                                                </ul>
                                            </details>
                                        ) : null}

                                        <Card className="border-amber-200 bg-amber-50/60">
                                            <CardContent className="pt-4">
                                                <p className="text-sm text-amber-900">
                                                    Final submission records the SPOT acknowledgement and creates the quote from the imported charges. Rates are still conditional until carrier and space are confirmed.
                                                </p>
                                            </CardContent>
                                        </Card>
                                    </TabsContent>
                                </Tabs>

                                <div className={`mt-6 flex flex-col gap-3 rounded-2xl border px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${
                                    reviewLines.affected.length > 0
                                        ? "border-amber-200 bg-amber-50 text-amber-950"
                                        : "border-emerald-200 bg-emerald-50 text-emerald-950"
                                }`}>
                                    <div>
                                        <div className="text-sm font-semibold">
                                            {reviewLines.affected.length > 0
                                                ? `Resolve ${reviewLines.affected.length} issue${reviewLines.affected.length === 1 ? "" : "s"} before creating quote`
                                                : "Ready to create quote"}
                                        </div>
                                        <div className="mt-1 text-xs opacity-80">
                                            {reviewLines.affected.length > 0
                                                ? "Needs Review shows only the decisions blocking a clean quote."
                                                : "All imported charges are mapped or intentionally conditional."}
                                        </div>
                                    </div>
                                    <Button
                                        type="button"
                                        size="sm"
                                        variant={reviewLines.affected.length > 0 ? "outline" : "default"}
                                        onClick={() => setReviewMode(reviewLines.affected.length > 0 ? "issues" : "allCharges")}
                                    >
                                        {reviewLines.affected.length > 0 ? "Review issues" : "Go to confirmation"}
                                    </Button>
                                </div>

                                {false && (
                                    <>
                                {hasReviewActions ? (
                                    <div className="rounded-[24px] border border-amber-200 bg-[linear-gradient(135deg,#fff8eb_0%,#fffdf8_100%)] px-5 py-4 text-sm text-amber-950">
                                        Fix the affected imported lines first, then confirm the quote.
                                    </div>
                                ) : (
                                    <div className="rounded-[24px] border border-emerald-200 bg-[linear-gradient(135deg,#edfcf4_0%,#f8fffb_100%)] px-5 py-4 text-sm text-emerald-900">
                                        Imported charges match the missing parts of this quote and are ready to confirm.
                                    </div>
                                )}

                                {reviewLines.affected.length > 0 && (
                                    <section className="space-y-3">
                                        <div>
                                            <div className="text-sm font-semibold text-slate-950">Affected lines</div>
                                            <p className="mt-1 text-sm text-slate-600">
                                                These are the imported lines that still need your decision.
                                            </p>
                                        </div>
                                        <div className="space-y-3">
                                            {reviewLines.affected.map((line) => (
                                                <div
                                                    key={line.key}
                                                    className="rounded-2xl border border-slate-200 bg-white px-4 py-3 shadow-sm"
                                                >
                                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                        <div className="min-w-0 space-y-1">
                                                            <div className="font-medium text-slate-950">{line.label}</div>
                                                            <div className="text-sm text-slate-600">
                                                                {line.amountDisplay} • {line.unitLabel}
                                                            </div>
                                                            <div className="text-xs text-slate-500">
                                                                {line.bucketLabel} • {line.sourceLabel}
                                                            </div>
                                                        </div>
                                                        <div className="flex flex-col items-start gap-3 sm:items-end">
                                                            <div className="flex flex-wrap gap-2">
                                                                {line.issueKinds.map((kind) => (
                                                                    <Badge
                                                                        key={`${line.key}-${kind}`}
                                                                        variant="outline"
                                                                        className={issueKindMeta[kind].className}
                                                                    >
                                                                        {issueKindMeta[kind].label}
                                                                    </Badge>
                                                                ))}
                                                            </div>
                                                            <div className="flex gap-2">
                                                                <Button
                                                                    type="button"
                                                                    size="sm"
                                                                    onClick={() => handleReviewLine(line)}
                                                                    disabled={!line.chargeLineId}
                                                                >
                                                                    Review
                                                                </Button>
                                                                <Button
                                                                    type="button"
                                                                    variant="outline"
                                                                    size="sm"
                                                                    onClick={() => toggleIssueDetails(line.key)}
                                                                >
                                                                    Details
                                                                </Button>
                                                            </div>
                                                        </div>
                                                    </div>
                                                    {expandedIssueRows[line.key] && line.details.length > 0 && (
                                                        <div className="mt-3 rounded-xl border border-slate-200 bg-slate-50/80 px-3 py-3 text-xs leading-5 text-slate-600">
                                                            <ul className="space-y-1">
                                                                {line.details.map((detail) => (
                                                                    <li key={`${line.key}-${detail}`}>{detail}</li>
                                                                ))}
                                                            </ul>
                                                        </div>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </section>
                                )}

                                {false && groupedLineIssues.length > 0 && (
                                    <section className="space-y-3">
                                        <div>
                                            <div className="text-sm font-semibold text-slate-950">Affected lines</div>
                                            <p className="mt-1 text-sm text-slate-600">
                                                Each row shows the line and why it still needs a decision.
                                            </p>
                                        </div>
                                        <div className="space-y-3">
                                            {groupedLineIssues.map((issue) => (
                                                <div
                                                    key={issue.key}
                                                    className="rounded-2xl border border-slate-200 bg-white px-4 py-3"
                                                >
                                                    <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                                                        <div className="min-w-0">
                                                            <div className="font-medium text-slate-950">{issue.label}</div>
                                                            <div className="mt-1 text-xs text-slate-500">
                                                                {[...issue.bucketLabels, ...issue.sourceLabels].filter(Boolean).join(" • ")}
                                                            </div>
                                                        </div>
                                                        <div className="flex flex-wrap gap-2">
                                                            {issue.issueKinds.map((kind) => (
                                                                <Badge
                                                                    key={`${issue.key}-${kind}`}
                                                                    variant="outline"
                                                                    className={issueKindMeta[kind].className}
                                                                >
                                                                    {issueKindMeta[kind].label}
                                                                </Badge>
                                                            ))}
                                                        </div>
                                                    </div>
                                                    {(issue.details.length > 0 || issue.sourceLabels.length > 1) && (
                                                        <details className="mt-3">
                                                            <summary className="cursor-pointer text-xs font-medium text-slate-600 hover:text-slate-900">
                                                                Details
                                                            </summary>
                                                            <div className="mt-2 space-y-2 text-xs leading-5 text-slate-600">
                                                                {issue.details.length > 0 && (
                                                                    <ul className="space-y-1">
                                                                        {issue.details.map((detail) => (
                                                                            <li key={`${issue.key}-${detail}`}>{detail}</li>
                                                                        ))}
                                                                    </ul>
                                                                )}
                                                                {issue.sourceLabels.length > 1 && (
                                                                    <div>Seen in: {issue.sourceLabels.join(", ")}</div>
                                                                )}
                                                            </div>
                                                        </details>
                                                    )}
                                                </div>
                                            ))}
                                        </div>
                                    </section>
                                )}

                                {importWideChecks.length > 0 && (
                                    <details className="rounded-[24px] border border-slate-200 bg-slate-50/70 px-5 py-4">
                                        <summary className="cursor-pointer text-sm font-medium text-slate-700">
                                            Other checks ({importWideChecks.length})
                                        </summary>
                                        <ul className="mt-3 space-y-2 text-sm text-slate-700">
                                            {importWideChecks.map((warning) => (
                                                <li key={warning}>{warning}</li>
                                            ))}
                                        </ul>
                                    </details>
                                )}
                                {reviewLines.unaffected.length > 0 && (
                                    <details className="rounded-[24px] border border-emerald-200 bg-emerald-50/50 px-5 py-4">
                                        <summary className="cursor-pointer text-sm font-medium text-emerald-900">
                                            Ready lines ({reviewLines.unaffected.length})
                                        </summary>
                                        <div className="mt-3 grid gap-2">
                                            {reviewLines.unaffected.map((line) => (
                                                <div
                                                    key={line.key}
                                                    className="flex flex-col gap-1 rounded-xl border border-emerald-100 bg-white/80 px-3 py-3 text-sm text-slate-700 sm:flex-row sm:items-center sm:justify-between"
                                                >
                                                    <div className="min-w-0">
                                                        <div className="font-medium text-slate-900">{line.label}</div>
                                                        <div className="text-xs text-slate-500">
                                                            {line.bucketLabel} • {line.sourceLabel}
                                                        </div>
                                                    </div>
                                                    <div className="text-sm text-slate-600">
                                                        {line.amountDisplay} • {line.unitLabel}
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    </details>
                                )}
                                    </>
                                )}
                            </CardContent>
                        </Card>

                    <Sheet open={Boolean(activeIssueDetails)} onOpenChange={(open) => !open && setActiveIssueDetails(null)}>
                        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
                            {activeIssueDetails ? (
                                <div className="space-y-6">
                                    <SheetHeader className="space-y-3 border-b border-slate-200 pb-6">
                                        <div className="flex flex-wrap gap-2">
                                            {activeIssueDetails.issueKinds.map((kind) => (
                                                <Badge
                                                    key={`sheet-${activeIssueDetails.key}-${kind}`}
                                                    variant="outline"
                                                    className={issueKindMeta[kind].className}
                                                >
                                                    {issueKindMeta[kind].label}
                                                </Badge>
                                            ))}
                                        </div>
                                        <div>
                                            <SheetTitle>{activeIssueDetails.label}</SheetTitle>
                                            <SheetDescription className="mt-2 leading-6">
                                                {getIssueProblemMessage(activeIssueDetails.issueKinds)}
                                            </SheetDescription>
                                        </div>
                                    </SheetHeader>

                                    <section className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4 text-sm">
                                        <div className="grid gap-3 sm:grid-cols-2">
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Amount</div>
                                                <div className="mt-1 text-slate-900">{activeIssueDetails.amountDisplay}</div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Unit</div>
                                                <div className="mt-1 text-slate-900">{activeIssueDetails.unitLabel}</div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Bucket</div>
                                                <div className="mt-1 text-slate-900">{activeIssueDetails.bucketLabel}</div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Source</div>
                                                <div className="mt-1 text-slate-900">{activeIssueDetails.sourceLabel}</div>
                                            </div>
                                        </div>
                                    </section>

                                    <section className="space-y-3">
                                        <div className="text-sm font-semibold text-slate-950">What needs attention</div>
                                        <ul className="space-y-2 text-sm leading-6 text-slate-700">
                                            {activeIssueDetails.details.map((detail) => (
                                                <li key={`${activeIssueDetails.key}-${detail}`}>{detail}</li>
                                            ))}
                                        </ul>
                                    </section>

                                    <section className="space-y-3">
                                        <div className="text-sm font-semibold text-slate-950">Normalization audit</div>
                                        <div className="grid gap-4 rounded-xl border border-slate-200 bg-white p-4 text-sm sm:grid-cols-2">
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Source label</div>
                                                <div className="mt-1 text-slate-900">
                                                    {String(activeIssueDetails.charge.source_label || activeIssueDetails.charge.description || "").trim() || "Not recorded"}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Normalized label</div>
                                                <div className="mt-1 text-slate-900">
                                                    {String(activeIssueDetails.charge.normalized_label || "").trim() || "Not recorded"}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Method</div>
                                                <div className="mt-1 text-slate-900">{humanizeEnum(activeIssueDetails.charge.normalization_method)}</div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Effective ProductCode</div>
                                                <div className="mt-1 text-slate-900">{formatProductCodeSummary(getEffectiveProductCode(activeIssueDetails.charge))}</div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Manual resolution</div>
                                                <div className="mt-1 text-slate-900">
                                                    {activeIssueDetails.charge.manual_resolution_status === "RESOLVED"
                                                        ? formatProductCodeSummary(activeIssueDetails.charge.manual_resolved_product_code)
                                                        : "Not resolved"}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Status</div>
                                                <div className="mt-1 text-slate-900">
                                                    {getChargeStatusLabel(activeIssueDetails.charge)}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Source reference</div>
                                                <div className="mt-1 text-slate-900">
                                                    {String(activeIssueDetails.charge.source_reference || "").trim() || "Not recorded"}
                                                </div>
                                            </div>
                                            <div>
                                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Flags</div>
                                                <div className="mt-1 text-slate-900">
                                                    {[
                                                        activeIssueDetails.charge.is_primary_cost ? "Primary" : null,
                                                        activeIssueDetails.charge.conditional ? "Conditional" : null,
                                                        activeIssueDetails.charge.exclude_from_totals ? "Excluded from totals" : null,
                                                    ].filter(Boolean).join(", ") || "None"}
                                                </div>
                                            </div>
                                        </div>
                                    </section>

                                    <div className="border-t border-slate-200 pt-4">
                                        <Button
                                            type="button"
                                            onClick={() => {
                                                handleReviewLine(activeIssueDetails);
                                                setActiveIssueDetails(null);
                                            }}
                                            disabled={!activeIssueDetails.chargeLineId}
                                        >
                                            Resolve
                                        </Button>
                                    </div>
                                </div>
                            ) : null}
                        </SheetContent>
                    </Sheet>
                </div>
            )}


        </div >
    );
}


