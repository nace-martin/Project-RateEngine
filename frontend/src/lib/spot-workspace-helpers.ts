import type { SPEChargeLine } from "@/lib/spot-types";

export type ReviewIssueKind = "unmapped" | "ambiguous" | "lowConfidence" | "conditional";

export type ImportedReviewLine = {
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
    canResolveConditional: boolean;
    charge: SPEChargeLine;
};

export const issueKindMeta: Record<ReviewIssueKind, { label: string; className: string }> = {
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

export const BUY_SIDE_SOURCE_MARKERS = ["COGS", "BUY"];

export const BUCKET_LABELS: Record<SPEChargeLine["bucket"], string> = {
    airfreight: "Freight",
    origin_charges: "Origin Charges",
    destination_charges: "Destination Charges",
};

export const NON_ACTIONABLE_AI_WARNING_PATTERNS = [
    "validity not specified - assuming 72 hours",
    "routing not specified - may involve multiple legs",
    "space/acceptance not confirmed",
];

export const COUNT_ONLY_WARNING_PATTERNS = [
    /^\d+\s+extracted charge\(s\) could not be mapped cleanly\.?$/i,
    /^\d+\s+extracted charge line\(s\) were low-confidence\.?$/i,
    /^\d+\s+extracted charge line\(s\) are conditional\.?$/i,
    /^Some imported charges need manual review:\s*/i,
    /^Line \d+:/i,
];

export const LOW_CONFIDENCE_WARNING_PATTERN =
    /^Line \d+:\s+(?:Please verify the charge label for|Low-confidence normalization for)\s+'([^']+)'/i;
export const UNMAPPED_WARNING_PATTERN = /^Line \d+:\s+Unmapped charge\s+'([^']+)'/i;
export const MANUAL_REVIEW_WARNING_PATTERN = /^Some imported charges need manual review:\s*(.+)$/i;

export const issueKindPriority: Record<ReviewIssueKind, number> = {
    unmapped: 0,
    ambiguous: 1,
    lowConfidence: 2,
    conditional: 3,
};

export const isBuySideCharge = (charge: SPEChargeLine): boolean => {
    const source = (charge.source_reference || "").toUpperCase();
    // Standard Rate charges are computed FROM COGS but are sell-side charges, so keep them visible.
    if (source.startsWith("STANDARD RATE")) return false;
    // AI/Analysis suggestions are always user-facing
    if (source.includes("AI") || source.includes("ANALYSIS") || source.includes("AGENT REPLY")) return false;
    return BUY_SIDE_SOURCE_MARKERS.some((marker) => source.includes(marker));
};

export const isStandardRateCharge = (charge: SPEChargeLine): boolean =>
    (charge.source_reference || "").toUpperCase().startsWith("STANDARD RATE");

export const componentToBucket = (component: string): SPEChargeLine["bucket"] | null => {
    const normalized = (component || "").toUpperCase();
    if (normalized === "FREIGHT") return "airfreight";
    if (normalized === "ORIGIN_LOCAL") return "origin_charges";
    if (normalized === "DESTINATION_LOCAL") return "destination_charges";
    return null;
};

export const sanitizeSummaryMessage = (message: string): string =>
    message.replace(/^[^A-Za-z0-9]+/, "").trim();

export const normalizeSummaryMessage = (message: string): string => {
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

export const getAnalysisSignalCount = (source: { analysis_summary_json?: Record<string, unknown> }, key: string): number => {
    const value = source.analysis_summary_json?.[key];
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
};

export const normalizeIssueLabel = (label: string): string =>
    sanitizeSummaryMessage(label).replace(/^['"]|['"]$/g, "").trim();

export const isCountOnlySummaryWarning = (warning: string): boolean =>
    COUNT_ONLY_WARNING_PATTERNS.some((pattern) => pattern.test(warning));

export const parseLineIssueWarning = (warning: string): { labels: string[]; kind: "unmapped" | "lowConfidence"; detail: string } | null => {
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

export const getPrimaryIssueKind = (issueKinds: ReviewIssueKind[]): ReviewIssueKind =>
    [...issueKinds].sort((left, right) => issueKindPriority[left] - issueKindPriority[right])[0] || "conditional";

export const getIssueProblemMessage = (issueKinds: ReviewIssueKind[]): string => {
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

export const humanizeEnum = (value?: string | null): string => {
    const normalized = String(value || "").trim();
    if (!normalized) return "Not recorded";
    return normalized
        .split("_")
        .filter(Boolean)
        .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
        .join(" ");
};

export const formatProductCodeSummary = (productCode?: SPEChargeLine["resolved_product_code"] | null): string => {
    if (!productCode?.code) return "Not recorded";
    return productCode.description ? `${productCode.code} - ${productCode.description}` : productCode.code;
};

export const getChargeStatusLabel = (charge: SPEChargeLine): string => {
    if (charge.manual_resolution_status === "RESOLVED") return "Manually resolved";
    if (charge.normalization_status === "MATCHED") return "Matched";
    if (charge.normalization_status === "AMBIGUOUS") return "Ambiguous";
    if (charge.normalization_status === "UNMAPPED") return "Needs review";
    return "Not normalized";
};

export const chargeUnitLabel = (unit?: SPEChargeLine["unit"]): string => {
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

export const formatChargeAmount = (charge: SPEChargeLine): string => {
    const amount = String(charge.amount || "").trim();
    if (!amount) return charge.currency || "";
    return `${amount} ${charge.currency || ""}`.trim();
};

export const isActionableAiWarning = (warning: string): boolean => {
    const normalized = normalizeSummaryMessage(warning).toLowerCase();
    return !NON_ACTIONABLE_AI_WARNING_PATTERNS.some((pattern) => normalized.includes(pattern));
};

export const getSourceSummaryTitle = (label: string, targetBucket: SPEChargeLine["bucket"] | "mixed"): string => {
    const cleaned = label.replace(/\bAI\b/gi, "").replace(/\s{2,}/g, " ").trim();
    if (cleaned.toLowerCase() === "unified intake") return "Uploaded rates";
    if (cleaned) return cleaned;
    if (targetBucket === "mixed") return "Uploaded rates";
    return `${BUCKET_LABELS[targetBucket]} import`;
};

export const getSourceSummarySubtitle = (bucket: SPEChargeLine["bucket"] | "mixed"): string => {
    if (bucket === "mixed") return "Imported lines are grouped for this quote";
    return `${BUCKET_LABELS[bucket]} lines are grouped for this quote`;
};

export const formatMissingComponents = (components?: string[]): string[] | null => {
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

export const formatListWithAnd = (items: string[]): string => {
    if (items.length <= 1) return items[0] || "";
    if (items.length === 2) return `${items[0]} and ${items[1]}`;
    return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
};

// Helper to convert rate specs into human-friendly text
export function humanizeRate(rate: number | string | null | undefined, unit: string | null, label: string): string {
    if (rate === null || rate === undefined || (typeof rate === "string" && rate.trim() === "")) {
        return "Flat fee";
    }

    const numericRate = typeof rate === "number" ? rate : Number(rate.trim());
    if (!Number.isFinite(numericRate)) {
        return "Rate unavailable";
    }

    if (label.includes("Min")) {
        return `Minimum USD 230.00 or USD ${numericRate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Fuel")) {
        return `USD ${numericRate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Security")) {
        return `USD ${numericRate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Handling")) {
        return `SGD ${numericRate.toFixed(2)} per set`;
    }
    return `${numericRate.toFixed(2)} per ${unit || "unit"}`;
}

export function friendlyStatus(status: string): string {
    switch (status) {
        case "accepted_by_user": return "Accepted";
        case "suggested": return "Suggested";
        case "ignored": return "Ignored";
        case "pending_product_code": return "Pending Product Code";
        case "needs_review": return "Needs Attention";
        case "unclassified":
        case "unclassified_item": return "Unknown Charge";
        default: return status;
    }
}
