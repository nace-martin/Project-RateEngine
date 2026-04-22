import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChargeNormalizationStatus, SPEProductCodeSummary } from "@/lib/spot-types";

type NormalizationAuditProps = {
    normalizationStatus?: ChargeNormalizationStatus | null;
    normalizationMethod?: string | null;
    sourceLabel?: string | null;
    normalizedLabel?: string | null;
    resolvedProductCode?: SPEProductCodeSummary | null;
    manualResolutionStatus?: "RESOLVED" | null;
    manualResolvedProductCode?: SPEProductCodeSummary | null;
    manualResolutionByUsername?: string | null;
    manualResolutionAt?: string | null;
    canOpenManualReview?: boolean;
    onOpenManualReview?: () => void;
};

const STATUS_STYLES: Record<
    ChargeNormalizationStatus,
    {
        badgeClassName: string;
        label: string;
        summaryClassName: string;
        detailsClassName: string;
    }
> = {
    MATCHED: {
        badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
        label: "Matched",
        summaryClassName: "text-emerald-900",
        detailsClassName: "border-emerald-200 bg-emerald-50/60",
    },
    UNMAPPED: {
        badgeClassName: "border-amber-200 bg-amber-50 text-amber-800",
        label: "Unmapped",
        summaryClassName: "text-amber-950",
        detailsClassName: "border-amber-200 bg-amber-50/70",
    },
    AMBIGUOUS: {
        badgeClassName: "border-rose-200 bg-rose-50 text-rose-800",
        label: "Ambiguous",
        summaryClassName: "text-rose-950",
        detailsClassName: "border-rose-200 bg-rose-50/70",
    },
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

const statusConfigFor = (status?: ChargeNormalizationStatus | null) =>
    status ? STATUS_STYLES[status] : null;

const productCodeSummary = (productCode?: SPEProductCodeSummary | null) => {
    if (!productCode) return "No product code resolved";
    const description = productCode.description?.trim();
    return description
        ? `${productCode.code} - ${description}`
        : productCode.code;
};

const AuditField = ({ label, value }: { label: string; value: string }) => (
    <div className="space-y-1">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">
            {label}
        </div>
        <div className="text-xs leading-5 text-slate-700">
            {value || "Not recorded"}
        </div>
    </div>
);

export function ChargeNormalizationAudit({
    normalizationStatus,
    normalizationMethod,
    sourceLabel,
    normalizedLabel,
    resolvedProductCode,
    manualResolutionStatus,
    manualResolvedProductCode,
    manualResolutionByUsername,
    manualResolutionAt,
    canOpenManualReview = false,
    onOpenManualReview,
}: NormalizationAuditProps) {
    const statusConfig = statusConfigFor(normalizationStatus);
    const hasAuditPayload = Boolean(
        normalizationStatus ||
        sourceLabel ||
        normalizedLabel ||
        normalizationMethod ||
        resolvedProductCode ||
        manualResolutionStatus ||
        manualResolvedProductCode
    );

    if (!hasAuditPayload) {
        return (
            <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600">
                Not normalized
            </Badge>
        );
    }

    return (
        <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
                <Badge
                    variant="outline"
                    className={cn(
                        "font-medium",
                        statusConfig?.badgeClassName || "border-slate-200 bg-slate-50 text-slate-600"
                    )}
                >
                    {statusConfig?.label || "Not normalized"}
                </Badge>
                {resolvedProductCode?.code ? (
                    <span className="text-[11px] font-medium text-slate-600">
                        {resolvedProductCode.code}
                    </span>
                ) : null}
                {manualResolutionStatus === "RESOLVED" ? (
                    <Badge variant="outline" className="border-sky-200 bg-sky-50 text-sky-800">
                        Manually reviewed
                    </Badge>
                ) : null}
            </div>

            {canOpenManualReview ? (
                <div>
                    <Button type="button" variant="outline" size="sm" onClick={onOpenManualReview}>
                        {manualResolutionStatus === "RESOLVED" ? "Update review" : "Review manually"}
                    </Button>
                </div>
            ) : null}

            <details className={cn("rounded-lg border", statusConfig?.detailsClassName || "border-slate-200 bg-slate-50/70")}>
                <summary className={cn("cursor-pointer list-none px-3 py-2 text-[11px] font-semibold", statusConfig?.summaryClassName || "text-slate-900")}>
                    Audit details
                </summary>
                <div className="grid gap-3 border-t border-black/5 px-3 py-3">
                    <AuditField label="Source label" value={String(sourceLabel || "").trim() || "Not recorded"} />
                    <AuditField label="Normalized label" value={String(normalizedLabel || "").trim() || "Not recorded"} />
                    <AuditField label="Method" value={humanizeEnum(normalizationMethod)} />
                    <AuditField label="Resolved product code" value={productCodeSummary(resolvedProductCode)} />
                    <AuditField
                        label="Manual resolution"
                        value={manualResolutionStatus === "RESOLVED" ? productCodeSummary(manualResolvedProductCode) : "Not reviewed"}
                    />
                    {manualResolutionStatus === "RESOLVED" ? (
                        <AuditField
                            label="Reviewed by"
                            value={
                                manualResolutionAt
                                    ? `${manualResolutionByUsername || "Unknown"} on ${new Date(manualResolutionAt).toLocaleString()}`
                                    : manualResolutionByUsername || "Unknown"
                            }
                        />
                    ) : null}
                </div>
            </details>
        </div>
    );
}
