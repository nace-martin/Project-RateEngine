"use client";

import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { getEffectiveProductCode } from "@/lib/spot-charge-display";
import {
    getIssueProblemMessage,
    humanizeEnum,
    formatProductCodeSummary,
    getChargeStatusLabel,
} from "@/lib/spot-workspace-helpers";
import type { ImportedReviewLine } from "@/lib/spot-workspace-helpers";
import { issueKindMeta } from "@/lib/spot-workspace-helpers";

export interface IssueDetailsSheetProps {
    open: boolean;
    activeIssueDetails: ImportedReviewLine | null;
    isLoading: boolean;
    onOpenChange: (open: boolean) => void;
    onResolveConditional: (line: ImportedReviewLine, action: "KEEP" | "REMOVE") => void | Promise<void>;
    onReviewLine: (line: ImportedReviewLine) => void;
}

export function IssueDetailsSheet({
    open,
    activeIssueDetails,
    isLoading,
    onOpenChange,
    onResolveConditional,
    onReviewLine,
}: IssueDetailsSheetProps) {
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
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

                        <div className="flex flex-wrap gap-2 border-t border-slate-200 pt-4">
                            {activeIssueDetails.canResolveConditional ? (
                                <>
                                    <Button
                                        type="button"
                                        onClick={() => void onResolveConditional(activeIssueDetails, "KEEP")}
                                        disabled={!activeIssueDetails.chargeLineId || isLoading}
                                    >
                                        Keep in quote
                                    </Button>
                                    <Button
                                        type="button"
                                        variant="outline"
                                        onClick={() => void onResolveConditional(activeIssueDetails, "REMOVE")}
                                        disabled={!activeIssueDetails.chargeLineId || isLoading}
                                    >
                                        Remove
                                    </Button>
                                </>
                            ) : null}
                            {activeIssueDetails.canReviewInSheet ? (
                                <Button
                                    type="button"
                                    onClick={() => {
                                        onReviewLine(activeIssueDetails);
                                    }}
                                    disabled={!activeIssueDetails.chargeLineId || isLoading}
                                >
                                    Resolve
                                </Button>
                            ) : null}
                        </div>
                    </div>
                ) : null}
            </SheetContent>
        </Sheet>
    );
}
