import type { ReactNode } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import { cn } from "@/lib/utils";
import type { ChargeNormalizationStatus, SPEProductCodeSummary } from "@/lib/spot-types";

type DisplayNormalizationStatus = ChargeNormalizationStatus | "MANUAL";

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
    detailsOpen?: boolean;
    onToggleDetails?: () => void;
    children?: ReactNode;
};

const STATUS_STYLES: Record<
    DisplayNormalizationStatus,
    {
        badgeClassName: string;
        label: string;
        detailsClassName: string;
    }
> = {
    MATCHED: {
        badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
        label: "Matched",
        detailsClassName: "border-emerald-200 bg-emerald-50/60",
    },
    UNMAPPED: {
        badgeClassName: "border-amber-200 bg-amber-50 text-amber-800",
        label: "Needs review",
        detailsClassName: "border-amber-200 bg-amber-50/70",
    },
    AMBIGUOUS: {
        badgeClassName: "border-rose-200 bg-rose-50 text-rose-800",
        label: "Ambiguous",
        detailsClassName: "border-rose-200 bg-rose-50/70",
    },
    MANUAL: {
        badgeClassName: "border-sky-200 bg-sky-50 text-sky-800",
        label: "Manually resolved",
        detailsClassName: "border-sky-200 bg-sky-50/70",
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
    detailsOpen = false,
    onToggleDetails,
    children,
}: NormalizationAuditProps) {
    const effectiveStatus: DisplayNormalizationStatus | null =
        manualResolutionStatus === "RESOLVED"
            ? "MANUAL"
            : normalizationStatus || null;
    const statusConfig = effectiveStatus
        ? STATUS_STYLES[effectiveStatus]
        : null;
    const primaryProductCode =
        manualResolutionStatus === "RESOLVED"
            ? manualResolvedProductCode || resolvedProductCode
            : resolvedProductCode;
    const hasAuditPayload = Boolean(
        normalizationStatus ||
        sourceLabel ||
        normalizedLabel ||
        normalizationMethod ||
        resolvedProductCode ||
        manualResolutionStatus ||
        manualResolvedProductCode
    );
    const hasDetails = hasAuditPayload || Boolean(children);

    return (
        <div className="space-y-2">
            <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="space-y-1">
                    <Badge
                        variant="outline"
                        className={cn(
                            "font-medium",
                            statusConfig?.badgeClassName || "border-slate-200 bg-slate-50 text-slate-600"
                        )}
                    >
                        {statusConfig?.label || "Not normalized"}
                    </Badge>
                    {primaryProductCode?.code ? (
                        <div className="text-[11px] text-slate-500">
                            {primaryProductCode.code}
                        </div>
                    ) : null}
                </div>

                <div className="flex items-center gap-1.5">
                    {canOpenManualReview ? (
                        <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={onOpenManualReview}
                            className="h-7"
                        >
                            Review
                        </Button>
                    ) : null}
                    {hasDetails ? (
                        <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            onClick={onToggleDetails}
                            className="h-7 px-2 text-[11px] text-slate-500"
                        >
                            Details
                            {detailsOpen ? (
                                <ChevronDown className="h-3.5 w-3.5" />
                            ) : (
                                <ChevronRight className="h-3.5 w-3.5" />
                            )}
                        </Button>
                    ) : null}
                </div>
            </div>

            <Sheet open={hasDetails && detailsOpen} onOpenChange={(open) => !open && onToggleDetails?.()}>
                <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl">
                    <div className="space-y-6">
                        <SheetHeader className="border-b border-slate-200 pb-5 text-left">
                            <div className="flex flex-wrap gap-2">
                                <Badge
                                    variant="outline"
                                    className={cn(
                                        "font-medium",
                                        statusConfig?.badgeClassName || "border-slate-200 bg-slate-50 text-slate-600"
                                    )}
                                >
                                    {statusConfig?.label || "Not normalized"}
                                </Badge>
                            </div>
                            <SheetTitle>Line details</SheetTitle>
                            <SheetDescription>
                                Source, matching, ProductCode, and low-frequency controls for this charge line.
                            </SheetDescription>
                        </SheetHeader>

                        {hasAuditPayload ? (
                            <section className="space-y-3">
                                <div className="text-sm font-semibold text-slate-950">Normalization</div>
                                <div
                                    className={cn(
                                        "grid gap-4 rounded-lg border p-4 sm:grid-cols-2",
                                        statusConfig?.detailsClassName || "border-slate-200 bg-slate-50/70"
                                    )}
                                >
                                    <AuditField label="Source label" value={String(sourceLabel || "").trim() || "Not recorded"} />
                                    <AuditField label="Normalized label" value={String(normalizedLabel || "").trim() || "Not recorded"} />
                                    <AuditField label="Method" value={humanizeEnum(normalizationMethod)} />
                                    <AuditField label="Resolved ProductCode" value={productCodeSummary(resolvedProductCode)} />
                                    {manualResolutionStatus === "RESOLVED" ? (
                                        <>
                                            <AuditField
                                                label="Manual resolution"
                                                value={productCodeSummary(manualResolvedProductCode)}
                                            />
                                            <AuditField
                                                label="Reviewed by"
                                                value={
                                                    manualResolutionAt
                                                        ? `${manualResolutionByUsername || "Unknown"} on ${new Date(manualResolutionAt).toLocaleString()}`
                                                        : manualResolutionByUsername || "Unknown"
                                                }
                                            />
                                        </>
                                    ) : null}
                                </div>
                            </section>
                        ) : null}

                        {children ? (
                            <section className="space-y-3">
                                <div className="text-sm font-semibold text-slate-950">Line controls</div>
                                <div className="rounded-lg border border-slate-200 bg-white p-4">
                                    {children}
                                </div>
                            </section>
                        ) : null}
                    </div>
                </SheetContent>
            </Sheet>
        </div>
    );
}
