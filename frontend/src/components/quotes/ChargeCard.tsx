import { useState } from "react";
import { CanonicalQuoteResult } from "@/lib/types";
import { BreakdownLine } from "@/lib/quote-financial-helpers";
import { AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { usePermissions } from "@/hooks/usePermissions";
import {
    displayMoney,
    displayPercent,
    displayValue,
    displayApplicable,
    formatAmount,
    sourceLabel,
    lineWarnings,
} from "@/lib/quote-financial-helpers";

export default function ChargeCard({
    line,
    displayCurrency,
    isShowingFCY,
    globalFx,
}: {
    line: BreakdownLine;
    displayCurrency: string;
    isShowingFCY: boolean;
    globalFx?: CanonicalQuoteResult["fx_applied"];
}) {
    const [isExpanded, setIsExpanded] = useState(false);
    const { canViewCOGS, canViewMargins } = usePermissions();
    const canonicalItem = line.canonical_item;
    const rawLine = line.raw_line;

    const sellExGst = isShowingFCY 
        ? (line.sell_fcy || line.sell_pgk) 
        : (line.sell_pgk || line.sell_fcy);
    
    const buyCurrency = rawLine?.cost_fcy_currency || canonicalItem?.cost_currency || "PGK";
    const buyAmount = rawLine?.cost_fcy_currency ? rawLine.cost_fcy : canonicalItem?.cost_amount;
    
    const desc = line.description;
    const code = canonicalItem?.product_code || line.component || "MISC";
    const status = canonicalItem ? sourceLabel(canonicalItem, rawLine) : "Unknown";
    const warnings = canonicalItem ? lineWarnings(canonicalItem, rawLine) : [];
    
    const hasWarnings = warnings.length > 0;
    const isCriticalWarning = warnings.some(w => w.level === 'critical');

    const buyAmountNum = Number(buyAmount || 0);
    const sellExGstNum = Number(sellExGst || 0);
    const costPgk = Number(rawLine?.cost_pgk || (canonicalItem as any)?.cost_pgk || (buyCurrency === "PGK" ? buyAmount : 0) || 0);
    
    let finalMarginAmount = line.margin_amount || rawLine?.margin_amount;
    let finalMarginPercent = line.margin_percent || rawLine?.margin_percent;
    
    if (finalMarginAmount === undefined || finalMarginAmount === null) {
        if (isShowingFCY) {
            finalMarginAmount = String(sellExGstNum - buyAmountNum);
        } else {
            finalMarginAmount = String(sellExGstNum - costPgk);
        }
    }
    
    if (finalMarginPercent === undefined || finalMarginPercent === null || finalMarginPercent === "0" || finalMarginPercent === "0.00") {
        if (isShowingFCY) {
            if (sellExGstNum > 0) {
                finalMarginPercent = String(((sellExGstNum - buyAmountNum) / sellExGstNum) * 100);
            } else {
                finalMarginPercent = "0.00";
            }
        } else {
            if (sellExGstNum > 0) {
                finalMarginPercent = String(((sellExGstNum - costPgk) / sellExGstNum) * 100);
            } else {
                finalMarginPercent = "0.00";
            }
        }
    }

    return (
        <div className={`rounded-lg border ${isExpanded ? 'border-blue-200 shadow-sm' : 'border-slate-200'} bg-white overflow-hidden transition-all`}>
            <div 
                className={`flex flex-col xl:flex-row xl:items-center gap-4 p-4 cursor-pointer hover:bg-slate-50 ${hasWarnings ? (isCriticalWarning ? 'bg-red-50/20' : 'bg-amber-50/20') : ''}`}
                onClick={() => setIsExpanded(!isExpanded)}
            >
                <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-800 text-sm truncate">{desc}</span>
                        {canonicalItem?.is_manual_override && (
                            <span className="px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 text-[10px] font-medium uppercase tracking-wide">Manual</span>
                        )}
                    </div>
                    <div className="flex items-center gap-3 mt-1.5">
                        <span className="text-[11px] font-mono text-slate-500 bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">{code}</span>
                        <span className="text-[11px] font-medium text-slate-500">{status}</span>
                        {hasWarnings && (
                            <span className={`text-[11px] font-medium flex items-center gap-1 ${isCriticalWarning ? 'text-red-600' : 'text-amber-600'}`}>
                                <AlertTriangle className="w-3 h-3" />
                                {warnings.length} note{warnings.length !== 1 ? 's' : ''}
                            </span>
                        )}
                    </div>
                </div>

                <div className="flex flex-wrap items-center gap-4 md:gap-8 justify-between xl:justify-end">
                    {canViewCOGS && (
                        <div className="flex flex-col xl:items-end min-w-[80px]">
                            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-0.5">Buy</span>
                            <span className="text-sm font-medium text-slate-600">{canonicalItem || rawLine ? displayMoney(buyAmount, buyCurrency) : "—"}</span>
                        </div>
                    )}
                    {canViewMargins && (
                        <div className="flex flex-col xl:items-end min-w-[100px]">
                            <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-0.5">Margin</span>
                            <div className="flex items-center gap-1 text-sm">
                                <span className="font-medium text-emerald-600">{canonicalItem || rawLine ? displayMoney(finalMarginAmount, "PGK") : "—"}</span>
                                {(canonicalItem || rawLine) && <span className="text-[11px] font-medium text-emerald-600/70">({displayPercent(finalMarginPercent)})</span>}
                            </div>
                        </div>
                    )}
                    <div className="flex flex-col xl:items-end min-w-[100px]">
                        <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-0.5">Sell (Ex GST)</span>
                        <span className="text-sm font-bold text-slate-900">{formatAmount(sellExGst, displayCurrency)}</span>
                    </div>
                    <div className="text-slate-400 self-center hidden md:block">
                        {isExpanded ? <ChevronDown className="w-5 h-5" /> : <ChevronRight className="w-5 h-5" />}
                    </div>
                </div>
            </div>

            {isExpanded && canonicalItem && (
                <div className="border-t border-slate-100 bg-slate-50/50 p-5">
                    <div className="flex items-center justify-between mb-4">
                        <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Calculation Details</h4>
                    </div>

                    {hasWarnings && (
                        <div className={`mb-5 rounded-md border p-3 ${isCriticalWarning ? 'border-red-200 bg-red-50 text-red-800' : 'border-amber-200 bg-amber-50 text-amber-800'}`}>
                            <div className="flex items-center gap-2 text-xs font-semibold mb-1.5">
                                <AlertTriangle className="h-4 w-4" />
                                {isCriticalWarning ? 'Pricing Risks' : 'Informational Notes'}
                            </div>
                            <ul className="space-y-1 text-xs">
                                {warnings.map((w, i) => (
                                    <li key={i} className="flex gap-2 items-start"><span className="opacity-50">•</span>{w.text}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-y-5 gap-x-6 text-sm">
                        <DetailField label="Quantity" value={displayValue(canonicalItem.quantity)} />
                        <DetailField label="Unit / Basis" value={`${displayValue(canonicalItem.unit_type)} / ${displayValue(canonicalItem.basis)}`} />
                        <DetailField label="GST Treatment" value={(() => {
                            let computedGstRate = rawLine?.gst_rate ? Number(rawLine.gst_rate) * 100 : 0;
                            const taxAmtNum = Number(canonicalItem.tax_amount || 0);
                            const sellAmtNum = Number(canonicalItem.sell_amount || 0);
                            
                            // If explicit rate missing but tax amount exists, compute it
                            if (computedGstRate === 0 && taxAmtNum > 0 && sellAmtNum > 0) {
                                computedGstRate = (taxAmtNum / sellAmtNum) * 100;
                            }
                            
                            const rateDisplay = displayPercent(computedGstRate);
                            if (taxAmtNum > 0) {
                                return `${displayValue(canonicalItem.tax_code)} at ${rateDisplay} (${displayMoney(taxAmtNum, canonicalItem.sell_currency || displayCurrency)})`;
                            }
                            return `${displayValue(canonicalItem.tax_code)} at ${rateDisplay}`;
                        })()} />
                        <DetailField label="Final Total (Inc GST)" value={displayMoney(Number(canonicalItem.sell_amount || 0) + Number(canonicalItem.tax_amount || 0), canonicalItem.sell_currency || displayCurrency)} />
                        
                        {(() => {
                            if (!canViewMargins) return null; // Detailed FX/CAF requires margin visibility
                            
                            const sellCurrency = canonicalItem.sell_currency || displayCurrency;
                            const fxApplies = typeof canonicalItem.fx_applied === "boolean"
                                ? canonicalItem.fx_applied
                                : String(buyCurrency || "PGK").toUpperCase() !== "PGK" || String(sellCurrency || "PGK").toUpperCase() !== "PGK";

                            if (!fxApplies) return <DetailField label="FX & CAF" value="Not applicable" />;
                            
                            return (
                                <>
                                    <DetailField label="FX Base Rate" value={displayApplicable(globalFx?.base_rate || rawLine?.exchange_rate || globalFx?.rate, true)} />
                                    <DetailField label="CAF Applied" value={globalFx?.caf_percent ? displayPercent(Number(globalFx.caf_percent) * 100) : "Not available"} />
                                    <DetailField label="Effective FX" value={displayApplicable(globalFx?.effective_fx_after_caf, true)} />
                                    <DetailField label="FX Direction" value={displayApplicable(globalFx?.direction, true)} />
                                </>
                            );
                        })()}
                        
                        <DetailField label="Notes" value={canonicalItem.calculation_notes || rawLine?.calculation_notes || "None"} colSpan={2} />
                    </div>
                </div>
            )}
        </div>
    );
}

function DetailField({ label, value, colSpan = 1 }: { label: string; value: React.ReactNode; colSpan?: number }) {
    return (
        <div className={colSpan > 1 ? `md:col-span-${colSpan}` : ''}>
            <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1">{label}</div>
            <div className="text-slate-800 break-words font-medium">{value}</div>
        </div>
    );
}
