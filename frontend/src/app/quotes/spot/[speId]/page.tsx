"use client";

/**
 * SPOT Rate Entry Page
 * 
 * SPOT workflow:
 * 1. Intake - Paste agent reply or upload source data
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
    SpotTemplateValidationCard,
} from "@/components/spot";
import { SpotRateEntryForm } from "@/components/spot/SpotRateEntryForm";
import { SpotWorkspaceSummary } from "@/components/spot/SpotWorkspaceSummary";
import { SourceComparisonSheet } from "@/components/spot/SourceComparisonSheet";
import { IssueDetailsSheet } from "@/components/spot/IssueDetailsSheet";
import type { SPEChargeLine, SPECommodity, TemplateFinding } from "@/lib/spot-types";
import type { ReplyAnalysisResult } from "@/lib/spot-types";
import { getSpotStandardCharges, reviewSpotFinding } from "@/lib/api";
import { getEffectiveProductCode, getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";
import { getSpotFinalizeDisabledReason } from "@/lib/spot-finalization";
import { COMMERCIAL_BUCKETS, inferCommercialBucket } from "@/lib/spot-commercial-buckets";
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
    { id: "intake", label: "1. Intake", description: "Paste or upload rates" },
    { id: "review", label: "2. Review", description: "Resolve exceptions" },
    { id: "confirm", label: "3. Confirm", description: "Create quote" },
];

const EMPTY_COMPONENTS: string[] = [];
const EMPTY_CHARGES: SPEChargeLine[] = [];
import {
    ReviewIssueKind,
    ImportedReviewLine,
    issueKindMeta,
    BUCKET_LABELS,
    issueKindPriority,
    isBuySideCharge,
    isStandardRateCharge,
    componentToBucket,
    sanitizeSummaryMessage,
    normalizeSummaryMessage,
    getAnalysisSignalCount,
    normalizeIssueLabel,
    isCountOnlySummaryWarning,
    parseLineIssueWarning,
    getPrimaryIssueKind,
    getIssueProblemMessage,
    humanizeEnum,
    formatProductCodeSummary,
    getChargeStatusLabel,
    chargeUnitLabel,
    formatChargeAmount,
    isActionableAiWarning,
    getSourceSummaryTitle,
    getSourceSummarySubtitle,
    formatMissingComponents,
    formatListWithAnd,
} from "@/lib/spot-workspace-helpers";

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
    const contactIdParam = searchParams.get("contact_id") || "";
    const incotermParam = searchParams.get("incoterm") || "";
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

    const handleReviewFinding = useCallback(async (finding: TemplateFinding, comment: string) => {
        if (!state.spe) return;
        try {
            await reviewSpotFinding(state.spe.id, {
                finding_code: finding.code,
                canonical_type: finding.canonical_type,
                template_line_id: finding.template_line_id,
                charge_line_id: finding.charge_line_id,
                comment: comment || undefined
            });
            await loadSPE(state.spe.id);
        } catch (err) {
            console.error("Failed to review finding:", err);
            alert(err instanceof Error ? err.message : "Failed to submit review");
        }
    }, [state.spe, loadSPE]);

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
                if (charge.conditional && !charge.conditional_acknowledged) {
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
                    conditional: displayCharges.filter(
                        (charge) => charge.conditional && !charge.conditional_acknowledged
                    ).length,
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
            if (charge.conditional && !charge.conditional_acknowledged) {
                issueKinds.add("conditional");
                details.add("Conditional charge. Confirm it should stay in the quote.");
            }

            for (const warning of actionableWarnings) {
                const parsed = parseLineIssueWarning(warning);
                if (!parsed) continue;
                if (
                    parsed.kind === "lowConfidence" &&
                    charge.manual_resolution_status !== "RESOLVED" &&
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
                        charge.normalization_status === "AMBIGUOUS" ||
                        issueKinds.has("lowConfidence")),
                canResolveConditional: Boolean(charge.id) && Boolean(charge.conditional && !charge.conditional_acknowledged),
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
    const [finalizeError, setFinalizeError] = useState<string | null>(null);
    const [reviewMode, setReviewMode] = useState<ReviewMode>("issues");
    const [allChargesFilter, setAllChargesFilter] = useState<"all" | "matched" | "conditional">("all");
    const [activeIssueDetails, setActiveIssueDetails] = useState<ImportedReviewLine | null>(null);
    const [sourceComparisonOpen, setSourceComparisonOpen] = useState(false);
    const [selectedSourceChargeKey, setSelectedSourceChargeKey] = useState<string | null>(null);
    const unresolvedReviewIssueCount = reviewLines.affected.length;
    const quoteSubmitDisabledReason = getSpotFinalizeDisabledReason({
        spe: state.spe,
        unresolvedReviewIssueCount,
        unresolvedReviewIssueLabels: reviewLines.affected.map((line) => line.label),
    });
    const quoteSubmitDisabled = Boolean(quoteSubmitDisabledReason);
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
            if (quoteSubmitDisabledReason) {
                setFinalizeError(quoteSubmitDisabledReason);
                return;
            }

            setFinalizeError(null);
            let spe = state.spe;

            if (spe.status === "draft" && charges.length > 0) {
                const updatedSpe = await actions.updateSPE(spe.id, {
                    charges,
                    conditions: {
                        space_not_confirmed: true,
                        airline_acceptance_not_confirmed: true,
                        rate_validity_hours: 72,
                        conditional_charges_present: charges.some(c => c.conditional),
                    }
                });
                if (!updatedSpe) {
                    return;
                }
                spe = updatedSpe;
            }

            if (!spe.acknowledgement) {
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
                contact_id: contactIdParam || undefined,
                incoterm: incotermParam || undefined,
            });

            if (result?.success && result.quote_id) {
                router.push(`/quotes/${result.quote_id}`);
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
    const handleConditionalDecision = useCallback(async (
        line: ImportedReviewLine,
        action: "KEEP" | "REMOVE"
    ) => {
        if (!line.chargeLineId) return;
        await actions.resolveConditionalChargeLine(line.chargeLineId, action);
        setActiveIssueDetails(null);
    }, [actions]);
    const toggleIssueDetails = useCallback((key: string) => {
        void key;
    }, []);
    const sourceComparisonCharges = useMemo(
        () => visibleReviewFormCharges.filter((charge) => !isStandardRateCharge(charge)),
        [visibleReviewFormCharges]
    );
    const selectedSourceCharge = useMemo(
        () =>
            sourceComparisonCharges.find((charge) =>
                (charge.id || `${charge.bucket}-${charge.description}-${charge.amount}`) === selectedSourceChargeKey
            ) || sourceComparisonCharges[0] || null,
        [selectedSourceChargeKey, sourceComparisonCharges]
    );
    const sourceComparisonText = useMemo(() => {
        const selectedSourceId = selectedSourceCharge?.source_batch_id;
        const source =
            state.spe?.sources?.find((item) => item.id === selectedSourceId) ||
            state.spe?.sources?.find((item) => item.raw_text) ||
            null;
        return source?.raw_text || "";
    }, [selectedSourceCharge?.source_batch_id, state.spe?.sources]);



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
            <SpotWorkspaceSummary
                customerName={displayCustomerName}
                originCode={originCode || state.spe?.shipment.origin_code || ""}
                destinationCode={destCode || state.spe?.shipment.destination_code || ""}
                commodity={commodity || state.spe?.shipment.commodity || ""}
                weightKg={weight || state.spe?.shipment.total_weight_kg || 0}
                pieces={pieces || state.spe?.shipment.pieces || 0}
                serviceScope={displayServiceScope}
                paymentTerms={displayPaymentTerm}
            />

            {/* Error display */}
            {(state.error || finalizeError) && (
                <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4">
                    <p className="text-sm font-medium text-red-800">{state.error || finalizeError}</p>
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
                    onSkipToManual={() => {
                        userAdvancedToReviewRef.current = true;
                        setCurrentStep("review");
                    }}
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

                    {state.spe?.template_validation && (
                        <SpotTemplateValidationCard 
                            validation={state.spe.template_validation} 
                            onReviewFinding={handleReviewFinding}
                        />
                    )}

                    <Card className="overflow-hidden border-slate-200 bg-white shadow-sm">
                        <CardHeader className="border-b border-primary/20 bg-primary pb-5 text-primary-foreground">
                            <div className="space-y-4">
                                <div className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
                                    <div className="max-w-3xl">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-primary-foreground/75">
                                            RateEngine SPOT
                                        </div>
                                        <CardTitle className="mt-2 text-2xl font-semibold text-primary-foreground">
                                            SPOT Rate Review
                                        </CardTitle>
                                        <p className="mt-2 text-sm leading-6 text-primary-foreground/85">
                                            Imported rates are organized for this quote. Resolve blockers, then review the final charge list.
                                        </p>
                                    </div>
                                    <Tabs value={reviewMode} onValueChange={(value) => setReviewMode(value as ReviewMode)}>
                                        <TabsList className="h-auto border border-white/25 bg-white/10 p-1 text-primary-foreground">
                                            <TabsTrigger value="issues">
                                                Needs Review ({unresolvedReviewIssueCount})
                                            </TabsTrigger>
                                            <TabsTrigger value="allCharges">
                                                All Charges ({visibleReviewFormCharges.length})
                                            </TabsTrigger>
                                        </TabsList>
                                    </Tabs>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-4">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setReviewMode("allCharges");
                                            setAllChargesFilter("all");
                                        }}
                                        className={`text-left rounded-xl border px-4 py-3 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98] ${
                                            reviewMode === "allCharges" && allChargesFilter === "all"
                                                ? "border-primary bg-slate-100 ring-2 ring-primary/20"
                                                : "border-white/25 bg-white text-slate-900"
                                        }`}
                                    >
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                            Imported
                                        </div>
                                        <div className="mt-2 text-2xl font-semibold text-slate-950">
                                            {totalImportedLines}
                                        </div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setReviewMode("issues");
                                        }}
                                        className={`text-left rounded-xl border px-4 py-3 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98] ${
                                            reviewMode === "issues"
                                                ? "border-amber-500 bg-amber-50 ring-2 ring-amber-500/20"
                                                : "border-white/25 bg-white text-slate-900"
                                        }`}
                                    >
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                            Needs review
                                        </div>
                                        <div className={`mt-2 text-2xl font-semibold ${unresolvedReviewIssueCount > 0 ? "text-amber-700" : "text-emerald-700"}`}>
                                            {unresolvedReviewIssueCount}
                                        </div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setReviewMode("allCharges");
                                            setAllChargesFilter("matched");
                                        }}
                                        className={`text-left rounded-xl border px-4 py-3 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98] ${
                                            reviewMode === "allCharges" && allChargesFilter === "matched"
                                                ? "border-emerald-600 bg-emerald-50 ring-2 ring-emerald-600/20"
                                                : "border-white/25 bg-white text-slate-900"
                                        }`}
                                    >
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                            Matched
                                        </div>
                                        <div className="mt-2 text-2xl font-semibold text-emerald-700">
                                            {matchedImportedLineCount}
                                        </div>
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setReviewMode("allCharges");
                                            setAllChargesFilter("conditional");
                                        }}
                                        className={`text-left rounded-xl border px-4 py-3 shadow-sm transition-all hover:scale-[1.02] active:scale-[0.98] ${
                                            reviewMode === "allCharges" && allChargesFilter === "conditional"
                                                ? "border-amber-600 bg-amber-50 ring-2 ring-amber-600/20"
                                                : "border-white/25 bg-white text-slate-900"
                                        }`}
                                    >
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-slate-500">
                                            Conditional
                                        </div>
                                        <div className={`mt-2 text-2xl font-semibold ${importedReviewCounts.conditional > 0 ? "text-amber-700" : "text-emerald-700"}`}>
                                            {importedReviewCounts.conditional}
                                        </div>
                                    </button>
                                </div>
                            </div>
                        </CardHeader>
                            <CardContent className="p-6">
                                <Tabs value={reviewMode} onValueChange={(value) => setReviewMode(value as ReviewMode)}>
                                    <TabsContent value="issues" className="mt-0 space-y-5">
                                        {unresolvedReviewIssueCount > 0 ? (
                                            <>
                                                <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950">
                                                    Resolve {unresolvedReviewIssueCount} issue{unresolvedReviewIssueCount === 1 ? "" : "s"} before creating quote.
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
                                                                    <div className="flex shrink-0 flex-wrap justify-end gap-2">
                                                                        {line.canResolveConditional ? (
                                                                            <>
                                                                                <Button
                                                                                    type="button"
                                                                                    size="sm"
                                                                                    onClick={() => void handleConditionalDecision(line, "KEEP")}
                                                                                    disabled={!line.chargeLineId || state.isLoading}
                                                                                >
                                                                                    Accept Conditional
                                                                                </Button>
                                                                                <Button
                                                                                    type="button"
                                                                                    variant="outline"
                                                                                    size="sm"
                                                                                    onClick={() => void handleConditionalDecision(line, "REMOVE")}
                                                                                    disabled={!line.chargeLineId || state.isLoading}
                                                                                >
                                                                                    Remove from Quote
                                                                                </Button>
                                                                            </>
                                                                        ) : null}
                                                                        {line.canReviewInSheet ? (
                                                                            <Button
                                                                                type="button"
                                                                                size="sm"
                                                                                onClick={() => handleReviewLine(line)}
                                                                                disabled={!line.chargeLineId || state.isLoading}
                                                                            >
                                                                                Resolve ProductCode
                                                                            </Button>
                                                                        ) : null}
                                                                        <Button
                                                                            type="button"
                                                                            variant="ghost"
                                                                            size="sm"
                                                                            onClick={() => setActiveIssueDetails(line)}
                                                                        >
                                                                            View Issue Details
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
                                                No imported lines need action right now. Review the final charge list before creating the quote.
                                            </div>
                                        )}

                                        {importWideChecks.length > 0 ? (
                                            <details className="rounded-xl border border-slate-200 bg-slate-50/70 px-5 py-4">
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
                                        <div className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-slate-50/80 px-5 py-4 text-sm text-slate-700 sm:flex-row sm:items-center sm:justify-between">
                                            <div>
                                                Full included charge list for final review. Return to Needs Review for any lines that still need a decision.
                                            </div>
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                onClick={() => {
                                                    setSelectedSourceChargeKey(
                                                        sourceComparisonCharges[0]
                                                            ? sourceComparisonCharges[0].id || `${sourceComparisonCharges[0].bucket}-${sourceComparisonCharges[0].description}-${sourceComparisonCharges[0].amount}`
                                                            : null
                                                    );
                                                    setSourceComparisonOpen(true);
                                                }}
                                                disabled={sourceComparisonCharges.length === 0}
                                            >
                                                View source comparison
                                            </Button>
                                        </div>

                                        <SpotRateEntryForm
                                            onSubmit={handleSaveAndCreateQuote}
                                            isLoading={state.isLoading}
                                            initialCharges={allReviewFormCharges}
                                            suggestedCharges={analysisResult?.assertions || []}
                                            shipmentType={resolvedShipmentType}
                                            serviceScope={serviceScope}
                                            missingComponents={EMPTY_COMPONENTS}
                                            submitLabel="Create Quote"
                                            submitDisabled={quoteSubmitDisabled}
                                            submitDisabledReason={quoteSubmitDisabledReason}
                                            allowEmptySubmit={Boolean(state.spe?.can_proceed)}
                                            onSaveDraft={handleSaveDraft}
                                            onManualResolveChargeLine={actions.manuallyResolveChargeLine}
                                            productCodeDomain={resolvedShipmentType}
                                            envelopeId={state.spe?.id}
                                            reviewRequest={activeReviewRequest}
                                            filterType={allChargesFilter}
                                        />

                                        {importWideChecks.length > 0 ? (
                                            <details className="rounded-xl border border-slate-200 bg-slate-50/70 px-5 py-4">
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

                                        <div className="rounded-xl border border-slate-200 bg-slate-50/80 px-5 py-4 space-y-4">
                                            <div className="text-sm font-semibold text-slate-900">Final Review by Commercial Bucket</div>
                                            <div className="divide-y divide-slate-200">
                                                {COMMERCIAL_BUCKETS.map((cb) => {
                                                    const cbCharges = allReviewFormCharges.filter((charge) => {
                                                        const rb = charge.reviewed_bucket || inferCommercialBucket(charge);
                                                        return rb === cb.id;
                                                    });
                                                    if (cbCharges.length === 0) return null;
                                                    
                                                    // Calculate total for this bucket if amount is parseable
                                                    const totalVal = cbCharges.reduce((sum, c) => {
                                                        const amt = parseFloat(c.amount);
                                                        return isNaN(amt) ? sum : sum + amt;
                                                    }, 0);
                                                    
                                                    // Map currency symbols or labels if any. Default USD/PGK.
                                                    const currencyLabel = cbCharges[0]?.currency || "USD";

                                                    return (
                                                        <div key={cb.id} className="flex justify-between py-2 text-xs">
                                                            <span className="text-slate-600 font-medium">
                                                                {cb.label} ({cbCharges.length} {cbCharges.length === 1 ? "charge" : "charges"})
                                                            </span>
                                                            <span className="font-semibold text-slate-900">
                                                                {totalVal.toFixed(2)} {currencyLabel}
                                                            </span>
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                            <div className="grid gap-2 sm:grid-cols-3 text-xs pt-2 border-t border-slate-200">
                                                <div className="flex items-center gap-2">
                                                    <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
                                                    <span className="text-slate-700">Matched: <span className="font-semibold text-slate-900">{matchedImportedLineCount}</span></span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className={`inline-block h-2 w-2 rounded-full ${importedReviewCounts.conditional > 0 ? "bg-amber-500" : "bg-emerald-500"}`} />
                                                    <span className="text-slate-700">Conditional: <span className="font-semibold text-slate-900">{importedReviewCounts.conditional}</span></span>
                                                </div>
                                                <div className="flex items-center gap-2">
                                                    <span className={`inline-block h-2 w-2 rounded-full ${unresolvedReviewIssueCount > 0 ? "bg-red-500" : "bg-emerald-500"}`} />
                                                    <span className="text-slate-700">Unresolved: <span className="font-semibold text-slate-900">{unresolvedReviewIssueCount}</span></span>
                                                </div>
                                            </div>
                                            {quoteSubmitDisabledReason ? (
                                                <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                                                    <span className="font-medium">Cannot create quote:</span> {quoteSubmitDisabledReason}
                                                </div>
                                            ) : (
                                                <div className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-900">
                                                    All blockers resolved. Ready to create quote. Rates remain conditional until carrier and space are confirmed.
                                                </div>
                                            )}
                                        </div>
                                    </TabsContent>
                                </Tabs>

                                {reviewMode === "issues" && (
                                    <div className={`mt-6 flex flex-col gap-3 rounded-xl border px-5 py-4 sm:flex-row sm:items-center sm:justify-between ${
                                        unresolvedReviewIssueCount > 0
                                            ? "border-amber-200 bg-amber-50 text-amber-950"
                                            : "border-emerald-200 bg-emerald-50 text-emerald-950"
                                    }`}>
                                        <div>
                                            <div className="text-sm font-semibold">
                                                {unresolvedReviewIssueCount > 0
                                                    ? `Resolve ${unresolvedReviewIssueCount} issue${unresolvedReviewIssueCount === 1 ? "" : "s"} before creating quote`
                                                    : "Ready for final review"}
                                            </div>
                                            <div className="mt-1 text-xs opacity-80">
                                                {unresolvedReviewIssueCount > 0
                                                    ? "Needs Review shows only the decisions blocking quote creation."
                                                    : "All blockers are resolved. Review the included charges before creating the quote."}
                                            </div>
                                        </div>
                                        {unresolvedReviewIssueCount > 0 ? (
                                            <Button
                                                type="button"
                                                size="sm"
                                                onClick={() => {
                                                    const firstIssue = reviewLines.affected[0];
                                                    if (!firstIssue) return;
                                                    if (firstIssue.canReviewInSheet) {
                                                        handleReviewLine(firstIssue);
                                                        return;
                                                    }
                                                    setActiveIssueDetails(firstIssue);
                                                }}
                                            >
                                                Resolve first issue
                                            </Button>
                                        ) : (
                                            <Button
                                                type="button"
                                                size="sm"
                                                onClick={() => setReviewMode("allCharges")}
                                            >
                                                Review Final Quote
                                            </Button>
                                        )}
                                    </div>
                                )}

                                {false && (
                                    <>
                                {hasReviewActions ? (
                                    <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-4 text-sm text-amber-950">
                                        Fix the affected imported lines first, then confirm the quote.
                                    </div>
                                ) : (
                                    <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-5 py-4 text-sm text-emerald-900">
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

                    <IssueDetailsSheet
                        open={Boolean(activeIssueDetails)}
                        activeIssueDetails={activeIssueDetails}
                        isLoading={state.isLoading}
                        onOpenChange={(open) => !open && setActiveIssueDetails(null)}
                        onResolveConditional={handleConditionalDecision}
                        onReviewLine={(line) => {
                            handleReviewLine(line);
                            setActiveIssueDetails(null);
                        }}
                    />

                    <SourceComparisonSheet
                        open={sourceComparisonOpen}
                        sourceComparisonText={sourceComparisonText}
                        sourceComparisonCharges={sourceComparisonCharges}
                        selectedSourceChargeKey={selectedSourceChargeKey}
                        selectedSourceCharge={selectedSourceCharge}
                        onOpenChange={setSourceComparisonOpen}
                        onSelectSourceChargeKey={setSelectedSourceChargeKey}
                    />
                </div>
            )}


        </div >
    );
}


