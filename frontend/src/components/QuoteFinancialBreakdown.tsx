"use client";

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
import { Package, MapPin, ReceiptText, Plane } from "lucide-react";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult | V3QuoteComputeResponse;
}

import BucketSection from "./quotes/BucketSection";
import {
    RawQuoteLine,
    BreakdownLine,
    BreakdownDataShape,
    BucketType,
    mapCanonicalLineItemToBreakdownLine,
    buildCanonicalTotals,
    getBucket,
    readStringField,
    getDisplaySellAmount,
    displayMoney,
    displayPercent,
    findRawLine,
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

