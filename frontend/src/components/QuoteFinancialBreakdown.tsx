"use client";

import { useState } from "react";
import {
    CanonicalQuoteLineItem,
    CanonicalQuoteResult,
    QuoteComputeResult,
    SellLine,
    V3QuoteLine,
    V3QuoteComputeResponse,
} from "@/lib/types";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import { AlertTriangle, ChevronDown, ChevronRight, Package, MapPin, ReceiptText, Plane } from "lucide-react";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult | V3QuoteComputeResponse;
}

import {
    LooseRecord,
    RawQuoteLine,
    BreakdownLine,
    BreakdownDataShape,
    BucketType,
    WarningDetails,
    SUBCATEGORY_ORDER,
    toMoneyString,
    mapCanonicalComponentToLeg,
    mapCanonicalLineItemToBreakdownLine,
    buildCanonicalTotals,
    formatAmount,
    getBucket,
    calculateBucketTotal,
    readField,
    readStringField,
    getDisplaySellAmount,
    isAvailable,
    displayValue,
    displayApplicable,
    displayMoney,
    displayPercent,
    findRawLine,
    lineWarnings,
    sourceLabel,
} from "@/lib/quote-financial-helpers";

export default function QuoteFinancialBreakdown({ result }: QuoteFinancialBreakdownProps) {
    const normalizedResult = result as unknown as BreakdownDataShape;
    const canonicalResult = normalizedResult.quote_result ?? null;
    const data = normalizedResult.latest_version ?? normalizedResult;
    const canonicalCurrency = (canonicalResult?.currency || "PGK").toUpperCase();
    
    const rawQuoteLines = ((((data.lines || []) as unknown[]) as RawQuoteLine[]) || []);
    
    const canonicalLines = canonicalResult?.line_items?.length
        ? canonicalResult.line_items.map((item) => mapCanonicalLineItemToBreakdownLine(item, canonicalCurrency, findRawLine(rawQuoteLines, item)))
        : [];
        
    const sell_lines = canonicalLines.length > 0
        ? canonicalLines
        : (((data.sell_lines || data.lines || []) as unknown[]) as BreakdownLine[]);
        
    const totals = canonicalResult ? buildCanonicalTotals(canonicalResult) : data.totals;

    const firstLineCurrency = sell_lines[0]?.sell_fcy_currency || sell_lines[0]?.sell_currency || 'PGK';
    const displayCurrency = readStringField(totals, 'currency') || readStringField(totals, 'total_sell_fcy_currency') || firstLineCurrency;
    const isShowingFCY = displayCurrency !== 'PGK';

    const pricedLines = sell_lines.filter(
        (line) => !line.is_informational && getDisplaySellAmount(line, isShowingFCY) > 0
    );
    const informationalLines = sell_lines.filter((line) => line.is_informational);

    const buckets: Record<BucketType, BreakdownLine[]> = {
        ORIGIN: [],
        FREIGHT: [],
        DESTINATION: [],
    };

    pricedLines.forEach((line) => {
        const bucket = getBucket(line);
        buckets[bucket].push(line);
    });

    return (
        <Card className="overflow-hidden border-slate-200 shadow-sm">
            <CardHeader className="pb-4 border-b border-slate-100 bg-white">
                <div className="flex items-center justify-between">
                    <CardTitle className="text-lg font-semibold flex items-center gap-2">
                        <ReceiptText className="w-5 h-5 text-slate-400" />
                        Financial Breakdown
                    </CardTitle>
                    <span className="text-xs text-slate-400">
                        Computed {"computation_date" in result ? result.computation_date : result.latest_version?.created_at}
                    </span>
                </div>
            </CardHeader>
            <CardContent className="p-0 bg-slate-50/50">
                
                {/* Top Financial Summary */}
                {canonicalResult && (
                    <div className="px-6 py-5 border-b border-slate-200 bg-white grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div className="flex flex-col justify-center">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Total Buy Cost</span>
                            <span className="text-base font-medium text-slate-800">{displayMoney(canonicalResult.total_cost_pgk, "PGK")}</span>
                        </div>
                        <div className="flex flex-col justify-center">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">Total Sell Amount</span>
                            <span className="text-base font-medium text-slate-800">{displayMoney(canonicalResult.total_sell_pgk, "PGK")}</span>
                        </div>
                        <div className="flex flex-col justify-center">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 mb-1">GST / Tax Total</span>
                            <span className="text-base font-medium text-slate-800">{displayMoney(canonicalResult.tax_breakdown?.gst_amount, displayCurrency)}</span>
                        </div>
                        <div className="flex flex-col justify-center md:border-l md:border-slate-200 md:pl-6">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-emerald-600 mb-1">Gross Margin</span>
                            <div className="flex items-baseline gap-1.5">
                                <span className="text-xl font-bold text-slate-900">{displayMoney(canonicalResult.margin_amount, "PGK")}</span>
                                <span className="text-sm font-medium text-emerald-600">({displayPercent(canonicalResult.margin_percent)})</span>
                            </div>
                        </div>
                        <div className="flex flex-col justify-center md:border-l md:border-slate-200 md:pl-6">
                            <span className="text-[11px] font-bold uppercase tracking-wider text-blue-600 mb-1">Grand Total</span>
                            <span className="text-2xl font-black text-slate-900">{displayMoney(canonicalResult.sell_total, displayCurrency)}</span>
                        </div>
                    </div>
                )}

                <div className="p-6 space-y-6">
                    {/* ORIGIN CHARGES */}
                    {buckets.ORIGIN.length > 0 && (
                        <BucketSection
                            title="Origin Charges"
                            lines={buckets.ORIGIN}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            globalFx={canonicalResult?.fx_applied}
                            icon={<Package className="w-4 h-4 text-blue-600" />}
                        />
                    )}
                    
                    {/* FREIGHT CHARGES */}
                    {buckets.FREIGHT.length > 0 && (
                        <BucketSection
                            title="Freight Charges"
                            lines={buckets.FREIGHT}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            globalFx={canonicalResult?.fx_applied}
                            icon={<Plane className="w-4 h-4 text-blue-600" />}
                        />
                    )}

                    {/* DESTINATION CHARGES */}
                    {buckets.DESTINATION.length > 0 && (
                        <BucketSection
                            title="Destination Charges"
                            lines={buckets.DESTINATION}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            globalFx={canonicalResult?.fx_applied}
                            icon={<MapPin className="w-4 h-4 text-blue-600" />}
                        />
                    )}
                </div>

                {/* Conditional Charges Footnotes */}
                {informationalLines.length > 0 && (
                    <div className="p-4 bg-amber-50/50 border-t border-amber-200">
                        <div className="flex items-start gap-2">
                            <span className="text-amber-600 text-xs font-semibold uppercase tracking-wide">Conditions & Notes</span>
                        </div>
                        <ul className="mt-2 space-y-1">
                            {informationalLines.map((line, idx) => (
                                <li key={idx} className="text-xs text-amber-800 flex items-start gap-2">
                                    <span className="text-amber-500">•</span>
                                    <span>{line.description} — <em className="text-amber-600">if applicable</em></span>
                                </li>
                            ))}
                        </ul>
                    </div>
                )}
            </CardContent>
        </Card>
    );
}

function getSectionStyle() {
    return {
        wrapper: "rounded-xl border border-slate-200 bg-white shadow-sm overflow-hidden",
        header: "bg-white hover:bg-slate-50 border-b border-slate-100 transition-colors cursor-pointer",
        title: "text-slate-900",
        iconBg: "bg-blue-50 text-blue-600",
        borderLeft: "border-l-[4px] border-l-blue-500"
    };
}


function BucketSection({
    title,
    lines,
    displayCurrency,
    isShowingFCY,
    globalFx,
    icon,
}: {
    title: string;
    lines: BreakdownLine[];
    displayCurrency: string;
    isShowingFCY: boolean;
    globalFx?: CanonicalQuoteResult["fx_applied"];
    icon: React.ReactNode;
}) {
    const [isExpanded, setIsExpanded] = useState(true);
    const styles = getSectionStyle();

    const bucketTotal = isShowingFCY
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    // Grouping logic within the bucket
    const groups: Record<string, BreakdownLine[]> = {};
    lines.forEach(line => {
        const sub = line.canonical_item?.subcategory || line.subcategory || 'Other Charges';
        if (!groups[sub]) groups[sub] = [];
        groups[sub].push(line);
    });

    const sortedGroups = Object.keys(groups).sort((a, b) => {
        const orderA = SUBCATEGORY_ORDER.indexOf(a);
        const orderB = SUBCATEGORY_ORDER.indexOf(b);
        const finalA = orderA === -1 ? 999 : orderA;
        const finalB = orderB === -1 ? 999 : orderB;
        return finalA - finalB;
    });

    return (
        <div className={styles.wrapper}>
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full flex items-center justify-between p-5 ${styles.header} ${styles.borderLeft}`}
            >
                <div className="flex items-center gap-4">
                    <div className={`p-2 rounded-lg ${styles.iconBg}`}>
                        {icon}
                    </div>
                    <div className="text-left">
                        <div className="flex items-center gap-3">
                            <h3 className={`text-base font-bold tracking-tight ${styles.title}`}>
                                {title}
                            </h3>
                            <span className="flex items-center justify-center bg-slate-100 text-slate-500 text-[11px] font-semibold h-6 px-2 rounded-full">
                                {lines.length} {lines.length === 1 ? 'charge' : 'charges'}
                            </span>
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-6">
                    <div className="text-right">
                        <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider mb-0.5">Subtotal</p>
                        <p className="text-base font-bold text-slate-900 mono-font">
                            {formatAmount(bucketTotal, displayCurrency)}
                        </p>
                    </div>
                    {isExpanded ? (
                        <ChevronDown className="w-5 h-5 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-5 h-5 text-slate-400" />
                    )}
                </div>
            </button>

            {isExpanded && (
                <div className="p-4 bg-slate-50/30 flex flex-col gap-6">
                    {sortedGroups.map(groupName => (
                        <div key={groupName} className="space-y-3">
                            <h4 className="text-[10px] font-bold text-slate-400 uppercase tracking-widest pl-1">
                                {groupName}
                            </h4>
                            <div className="flex flex-col gap-2">
                                {groups[groupName].map((line, index) => (
                                    <ChargeCard
                                        key={index}
                                        line={line}
                                        displayCurrency={displayCurrency}
                                        isShowingFCY={isShowingFCY}
                                        globalFx={globalFx}
                                    />
                                ))}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}

function ChargeCard({
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
    
    let finalMarginAmount = line.margin_amount || rawLine?.margin_amount;
    let finalMarginPercent = line.margin_percent || rawLine?.margin_percent;
    
    if (finalMarginAmount === undefined || finalMarginAmount === null) {
        finalMarginAmount = String(sellExGstNum - buyAmountNum);
    }
    
    if (finalMarginPercent === undefined || finalMarginPercent === null || finalMarginPercent === "0" || finalMarginPercent === "0.00") {
        if (buyAmountNum > 0) {
            finalMarginPercent = String(((sellExGstNum - buyAmountNum) / buyAmountNum) * 100);
        } else if (sellExGstNum > 0) {
            finalMarginPercent = "100.00";
        } else {
            finalMarginPercent = "0.00";
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
                    <div className="flex flex-col xl:items-end min-w-[80px]">
                        <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-0.5">Buy</span>
                        <span className="text-sm font-medium text-slate-600">{canonicalItem || rawLine ? displayMoney(buyAmount, buyCurrency) : "—"}</span>
                    </div>
                    <div className="flex flex-col xl:items-end min-w-[100px]">
                        <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold mb-0.5">Margin</span>
                        <div className="flex items-center gap-1 text-sm">
                            <span className="font-medium text-emerald-600">{canonicalItem || rawLine ? displayMoney(finalMarginAmount, "PGK") : "—"}</span>
                            {(canonicalItem || rawLine) && <span className="text-[11px] font-medium text-emerald-600/70">({displayPercent(finalMarginPercent)})</span>}
                        </div>
                    </div>
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
