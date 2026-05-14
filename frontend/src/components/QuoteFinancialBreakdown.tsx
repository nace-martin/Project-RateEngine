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

type LooseRecord = Record<string, unknown>;
type BreakdownLine = SellLine & { 
    sell_fcy_currency?: string;
    canonical_item?: CanonicalQuoteLineItem;
    raw_line?: RawQuoteLine;
};
type BreakdownDataShape = {
    status?: string;
    quote_result?: CanonicalQuoteResult | null;
    latest_version?: {
        sell_lines?: BreakdownLine[];
        lines?: BreakdownLine[];
        totals?: LooseRecord;
    };
    sell_lines?: BreakdownLine[];
    lines?: BreakdownLine[];
    totals?: LooseRecord;
};
type RawQuoteLine = V3QuoteLine & BreakdownLine;

function toMoneyString(value: number): string {
    return value.toFixed(2);
}

function mapCanonicalComponentToLeg(component: string): SellLine["leg"] {
    switch ((component || "").toUpperCase()) {
        case "ORIGIN_LOCAL":
            return "ORIGIN";
        case "DESTINATION_LOCAL":
            return "DESTINATION";
        case "FREIGHT":
            return "FREIGHT";
        default:
            return "DESTINATION";
    }
}

function mapCanonicalLineItemToBreakdownLine(
    item: CanonicalQuoteLineItem,
    currency: string,
    rawLine?: RawQuoteLine
): BreakdownLine {
    const sellAmount = parseFloat(item.sell_amount || "0");
    const taxAmount = parseFloat(item.tax_amount || "0");
    const sellInclTax = sellAmount + taxAmount;

    return {
        line_type: "COMPONENT",
        component: item.product_code || item.component,
        description: item.description,
        leg: mapCanonicalComponentToLeg(item.component),
        cost_pgk: item.cost_amount,
        sell_pgk: currency === "PGK" ? item.sell_amount : "0.00",
        sell_pgk_incl_gst: currency === "PGK" ? toMoneyString(sellInclTax) : "0.00",
        gst_amount: item.tax_amount,
        sell_fcy: currency !== "PGK" ? item.sell_amount : item.sell_amount,
        sell_fcy_incl_gst: currency !== "PGK" ? toMoneyString(sellInclTax) : toMoneyString(sellInclTax),
        sell_currency: currency,
        sell_fcy_currency: currency !== "PGK" ? currency : undefined,
        margin_percent: "0",
        exchange_rate: "0",
        source: item.cost_source,
        is_informational: !item.included_in_total,
        canonical_item: item,
        raw_line: rawLine,
    };
}

function buildCanonicalTotals(result: CanonicalQuoteResult): LooseRecord {
    const currency = (result.currency || "PGK").toUpperCase();
    const sellTotal = parseFloat(result.sell_total || "0");
    const gstAmount = parseFloat(result.tax_breakdown?.gst_amount || "0");
    const exGst = sellTotal - gstAmount;

    return {
        currency,
        total_quote_amount: toMoneyString(sellTotal),
        total_gst: result.tax_breakdown?.gst_amount || "0.00",
        gst_amount: result.tax_breakdown?.gst_amount || "0.00",
        total_sell_pgk: result.total_sell_pgk,
        total_sell_pgk_incl_gst: currency === "PGK" ? result.sell_total : result.total_sell_pgk,
        total_sell_ex_gst: toMoneyString(exGst),
        total_sell_fcy: currency !== "PGK" ? toMoneyString(exGst) : undefined,
        total_sell_fcy_incl_gst: currency !== "PGK" ? result.sell_total : undefined,
        total_sell_fcy_currency: currency !== "PGK" ? currency : undefined,
    };
}

const formatAmount = (amountStr: string | number | undefined, currency: string) => {
    const amount = typeof amountStr === 'number' ? amountStr : parseFloat(amountStr || "0");
    const formatted = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(amount);
    return `${currency} ${formatted}`;
};

type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION';

function getBucket(line: SellLine): BucketType {
    if (line.leg === 'MAIN' || line.leg === 'FREIGHT') return 'FREIGHT';
    if (line.leg === 'ORIGIN') return 'ORIGIN';
    return 'DESTINATION';
}

function calculateBucketTotal(lines: BreakdownLine[], field: string): number {
    return lines.reduce((sum, line) => {
        const rawValue = ((line as unknown) as Record<string, unknown>)[field];
        const value = parseFloat(String(rawValue ?? '0'));
        return sum + value;
    }, 0);
}

function readField(obj: unknown, key: string): unknown {
    if (!obj || typeof obj !== "object") return undefined;
    return (obj as Record<string, unknown>)[key];
}

function readStringField(obj: unknown, key: string): string | undefined {
    const value = readField(obj, key);
    return typeof value === "string" ? value : undefined;
}

function getDisplaySellAmount(line: BreakdownLine, isShowingFCY: boolean): number {
    const rawValue = isShowingFCY
        ? (line.sell_fcy || line.sell_pgk)
        : (line.sell_pgk || line.sell_fcy);
    return parseFloat(String(rawValue || "0"));
}

function isAvailable(value: unknown): boolean {
    return value !== null && value !== undefined && value !== "";
}

function displayValue(value: unknown): string {
    return isAvailable(value) ? String(value) : "Not available";
}

function displayApplicable(value: unknown, applicable: boolean): string {
    if (!applicable) return "Not applicable";
    return displayValue(value);
}

function displayMoney(value: unknown, currency: string): string {
    if (!isAvailable(value)) return "Not available";
    return formatAmount(String(value), currency);
}

function displayPercent(value: unknown): string {
    if (!isAvailable(value)) return "Not available";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return String(value);
    return `${parsed.toFixed(2)}%`;
}

function findRawLine(rawLines: RawQuoteLine[], canonicalLine: CanonicalQuoteLineItem): RawQuoteLine | undefined {
    if (canonicalLine.line_id) {
        const byId = rawLines.find((line) => line.id === canonicalLine.line_id);
        if (byId) return byId;
    }
    return rawLines.find((line) => {
        const code = line.product_code || line.component || line.service_component?.code;
        return code === canonicalLine.product_code && line.description === canonicalLine.description;
    });
}

type WarningDetails = { text: string; level: 'critical' | 'info' };

function lineWarnings(line: CanonicalQuoteLineItem, rawLine?: RawQuoteLine): WarningDetails[] {
    const warnings: WarningDetails[] = [];
    if (rawLine?.is_rate_missing) warnings.push({ text: "Missing buy rate", level: 'critical' });
    if (line.is_manual_override || rawLine?.is_manual_override) warnings.push({ text: "Manual override", level: 'info' });
    if (line.rate_source === "FALLBACK_RULE") warnings.push({ text: "FX or rate fallback applied", level: 'info' });
    return warnings;
}

function sourceLabel(line: CanonicalQuoteLineItem, rawLine?: RawQuoteLine): string {
    if (line.is_spot_sourced || rawLine?.is_spot_sourced) return "SPOT";
    if (line.is_manual_override || rawLine?.is_manual_override) return "Manual entry";
    if (line.rate_source === "MANUAL_OVERRIDE") return "Manual entry";
    if (line.rate_source === "PARTNER_SPOT") return "SPOT";
    if (line.rate_source === "DB_TARIFF") return "V4 rate card";
    if (line.rate_source === "FALLBACK_RULE") return "Fallback rule";
    return displayValue(line.rate_source);
}

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
                <div className="p-4 bg-slate-50/30 flex flex-col gap-2">
                    {lines.map((line, index) => (
                        <ChargeCard
                            key={index}
                            line={line}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            globalFx={globalFx}
                        />
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
    const marginAmount = canonicalItem?.margin_amount;
    const marginPercent = canonicalItem?.margin_percent;
    const warnings = canonicalItem ? lineWarnings(canonicalItem, rawLine) : [];
    
    const hasWarnings = warnings.length > 0;
    const isCriticalWarning = warnings.some(w => w.level === 'critical');

    const buyAmountNum = Number(buyAmount || 0);
    const sellExGstNum = Number(sellExGst || 0);
    
    let finalMarginAmount = canonicalItem?.margin_amount ?? rawLine?.margin_amount;
    let finalMarginPercent = canonicalItem?.margin_percent ?? rawLine?.margin_percent;
    
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
