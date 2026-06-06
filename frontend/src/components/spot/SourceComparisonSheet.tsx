"use client";

import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import type { SPEChargeLine } from "@/lib/spot-types";
import { getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";
import {
    formatChargeAmount,
    chargeUnitLabel,
} from "@/lib/spot-workspace-helpers";

export interface SourceComparisonSheetProps {
    open: boolean;
    sourceComparisonText: string;
    sourceComparisonCharges: SPEChargeLine[];
    selectedSourceChargeKey: string | null;
    selectedSourceCharge: SPEChargeLine | null;
    onOpenChange: (open: boolean) => void;
    onSelectSourceChargeKey: (key: string | null) => void;
}

export function SourceComparisonSheet({
    open,
    sourceComparisonText,
    sourceComparisonCharges,
    selectedSourceChargeKey,
    selectedSourceCharge,
    onOpenChange,
    onSelectSourceChargeKey,
}: SourceComparisonSheetProps) {
    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-5xl">
                <div className="space-y-6">
                    <SheetHeader className="space-y-2 border-b border-slate-200 pb-5">
                        <SheetTitle>Source comparison</SheetTitle>
                        <SheetDescription>
                            Optional audit view. Select a charge to inspect the captured source evidence.
                        </SheetDescription>
                    </SheetHeader>
                    <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,0.8fr)]">
                        <section className="space-y-3">
                            <div className="text-sm font-semibold text-slate-950">Source text</div>
                            <div className="max-h-[70vh] overflow-auto rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm leading-6 text-slate-800">
                                {sourceComparisonText ? (
                                    <pre className="whitespace-pre-wrap font-sans">{sourceComparisonText}</pre>
                                ) : (
                                    <div className="text-slate-500">No source text captured for this source.</div>
                                )}
                            </div>
                        </section>
                        <section className="space-y-3">
                            <div className="text-sm font-semibold text-slate-950">Extracted charges</div>
                            <div className="space-y-2">
                                {sourceComparisonCharges.map((charge) => {
                                    const key = charge.id || `${charge.bucket}-${charge.description}-${charge.amount}`;
                                    const isSelected = key === (selectedSourceCharge?.id || `${selectedSourceCharge?.bucket}-${selectedSourceCharge?.description}-${selectedSourceCharge?.amount}`);
                                    return (
                                        <button
                                            key={key}
                                            type="button"
                                            onClick={() => onSelectSourceChargeKey(key)}
                                            className={`w-full rounded-xl border px-4 py-3 text-left text-sm transition-colors ${
                                                isSelected
                                                    ? "border-primary bg-primary/5 text-slate-950"
                                                    : "border-slate-200 bg-white text-slate-700 hover:border-primary/40"
                                            }`}
                                        >
                                            <div className="font-semibold">{getSpotChargeDisplayLabel(charge, { includeProductCode: true })}</div>
                                            <div className="mt-1 text-xs text-slate-500">
                                                {formatChargeAmount(charge)} / {chargeUnitLabel(charge.unit)}
                                            </div>
                                        </button>
                                    );
                                })}
                            </div>
                            <div className="rounded-xl border border-slate-200 bg-white p-4">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Source</div>
                                {selectedSourceCharge?.source_excerpt ? (
                                    <div className="mt-3 rounded-md border border-primary/20 bg-primary/5 p-3 text-sm leading-6 text-slate-900">
                                        {selectedSourceCharge.source_excerpt}
                                    </div>
                                ) : (
                                    <div className="mt-3 text-sm text-slate-500">No snippet captured for this charge.</div>
                                )}
                                <div className="mt-3 space-y-1 text-xs text-slate-500">
                                    {selectedSourceCharge?.source_line_number ? <div>Line {selectedSourceCharge.source_line_number}</div> : null}
                                    {selectedSourceCharge?.source_line_identity ? <div className="break-all">{selectedSourceCharge.source_line_identity}</div> : null}
                                </div>
                            </div>
                        </section>
                    </div>
                </div>
            </SheetContent>
        </Sheet>
    );
}
