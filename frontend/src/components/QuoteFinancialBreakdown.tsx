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
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Separator } from "@/components/ui/separator";
import { AlertTriangle, Calculator, ChevronDown, ChevronRight, Package, MapPin, ReceiptText, Plane } from "lucide-react";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult | V3QuoteComputeResponse;
}

type LooseRecord = Record<string, unknown>;
type BreakdownLine = SellLine & { sell_fcy_currency?: string };
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

// Simplified currency display without symbol (for cleaner table display)
const formatAmount = (amountStr: string | number | undefined, currency: string) => {
    const amount = typeof amountStr === 'number' ? amountStr : parseFloat(amountStr || "0");
    const formatted = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(amount);
    return `${currency} ${formatted}`;
};


type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION';

// Get bucket for a line
function getBucket(line: SellLine): BucketType {
    if (line.leg === 'MAIN' || line.leg === 'FREIGHT') return 'FREIGHT';
    if (line.leg === 'ORIGIN') return 'ORIGIN';
    return 'DESTINATION';
}

// Calculate bucket subtotal
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

function normalizeStatus(result: QuoteComputeResult | V3QuoteComputeResponse): string {
    const maybeStatus = readStringField(result, "status") || readStringField((result as BreakdownDataShape).quote_result, "status");
    return (maybeStatus || "").toUpperCase();
}

function isAvailable(value: unknown): boolean {
    return value !== null && value !== undefined && value !== "";
}

function displayValue(value: unknown): string {
    return isAvailable(value) ? String(value) : "Not available";
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

function lineWarnings(line: CanonicalQuoteLineItem, rawLine?: RawQuoteLine): string[] {
    const warnings: string[] = [];
    if (rawLine?.is_rate_missing) warnings.push("Missing buy rate");
    if (line.is_manual_override || rawLine?.is_manual_override) warnings.push("Manual override");
    if (line.rate_source === "FALLBACK_RULE") warnings.push("FX or rate fallback");
    if (!line.calculation_notes && !rawLine?.calculation_notes) warnings.push("Missing calculation metadata");
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
    const canonicalLines = canonicalResult?.line_items?.length
        ? canonicalResult.line_items.map((item) => mapCanonicalLineItemToBreakdownLine(item, canonicalCurrency))
        : [];
    const sell_lines = canonicalLines.length > 0
        ? canonicalLines
        : (((data.sell_lines || data.lines || []) as unknown[]) as BreakdownLine[]);
    const rawQuoteLines = ((((data.lines || []) as unknown[]) as RawQuoteLine[]) || []);
    const totals = canonicalResult ? buildCanonicalTotals(canonicalResult) : data.totals;
    const quoteStatus = normalizeStatus(result);
    const showCalculationReview = Boolean(canonicalResult && ["DRAFT", "INCOMPLETE"].includes(quoteStatus));

    // Detect display currency and logic flags
    const firstLineCurrency = sell_lines[0]?.sell_fcy_currency || sell_lines[0]?.sell_currency || 'PGK';
    const displayCurrency = readStringField(totals, 'currency') || readStringField(totals, 'total_sell_fcy_currency') || firstLineCurrency;
    const isShowingFCY = displayCurrency !== 'PGK';

    // Separate informational (conditional) charges from priced lines
    const pricedLines = sell_lines.filter(
        (line) => !line.is_informational && getDisplaySellAmount(line, isShowingFCY) > 0
    );
    const informationalLines = sell_lines.filter((line) => line.is_informational);

    // Group PRICED lines by bucket (not informational ones)
    const buckets: Record<BucketType, BreakdownLine[]> = {
        ORIGIN: [],
        FREIGHT: [],
        DESTINATION: [],
    };

    pricedLines.forEach((line) => {
        const bucket = getBucket(line);
        buckets[bucket].push(line);
    });

    // 3. Robust Total Mapping - Exhaustive check of all possible backend field names
    const totalExGst = isShowingFCY
        ? parseFloat(String(readField(totals, 'total_sell_ex_gst') ?? readField(totals, 'total_sell_fcy') ?? readField(totals, 'sell_fcy') ?? '0'))
        : parseFloat(String(readField(totals, 'total_sell_pgk') ?? readField(totals, 'sell_pgk') ?? '0'));
        
    const totalGst = parseFloat(String(readField(totals, 'gst_amount') ?? readField(totals, 'total_gst') ?? readField(totals, 'gst_pgk') ?? '0'));
    
    const totalIncGst = isShowingFCY
        ? parseFloat(String(readField(totals, 'total_quote_amount') ?? readField(totals, 'total_sell_fcy_incl_gst') ?? readField(totals, 'sell_fcy_incl_gst') ?? readField(totals, 'total_sell_fcy') ?? '0'))
        : parseFloat(String(readField(totals, 'total_sell_pgk_incl_gst') ?? readField(totals, 'sell_pgk_incl_gst') ?? readField(totals, 'sell_pgk') ?? '0'));



    return (
        <Card className="overflow-hidden border-slate-200">
            <CardHeader className="pb-4 border-b border-slate-100">
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
            <CardContent className="p-0">
                {/* ORIGIN CHARGES */}
                {buckets.ORIGIN.length > 0 && (
                    <BucketSection
                        title="Origin Charges"
                        lines={buckets.ORIGIN}
                        displayCurrency={displayCurrency}
                        isShowingFCY={isShowingFCY}
                        icon={<Package className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}
                {/* FREIGHT CHARGES */}
                {buckets.FREIGHT.length > 0 && (
                    <BucketSection
                        title="Freight Charges"
                        lines={buckets.FREIGHT}
                        displayCurrency={displayCurrency}
                        isShowingFCY={isShowingFCY}
                        icon={<Plane className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}

                {/* DESTINATION CHARGES */}
                {buckets.DESTINATION.length > 0 && (
                    <BucketSection
                        title="Destination Charges"
                        lines={buckets.DESTINATION}
                        displayCurrency={displayCurrency}
                        isShowingFCY={isShowingFCY}
                        icon={<MapPin className="w-4 h-4 text-blue-600" />}
                        colorClass="blue"
                    />
                )}

                {/* Totals Section */}
                <div className="p-6 bg-slate-50 border-t border-slate-200">
                    <div className="flex flex-col items-end space-y-2">
                        <div className="flex justify-between w-full max-w-xs text-sm">
                            <span className="text-slate-500">Total Sell (Ex GST)</span>
                            <span className="font-mono font-medium">
                                {formatAmount(totalExGst, displayCurrency)}
                            </span>
                        </div>
                        <div className="flex justify-between w-full max-w-xs text-sm">
                            <span className="text-slate-500">Total GST (10%)</span>
                            <span className="font-mono">
                                {formatAmount(totalGst, displayCurrency)}
                            </span>
                        </div>
                        <Separator className="w-full max-w-xs my-2" />
                        <div className="flex justify-between w-full max-w-xs items-end">
                            <span className="text-sm font-medium text-slate-700">Total Quote Amount</span>
                            <div className="text-right">
                                <span className="block text-2xl font-bold text-blue-600">
                                    {displayCurrency} {totalIncGst.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                                </span>
                                <span className="text-[10px] text-slate-400 uppercase">
                                    {displayCurrency} (INC GST)
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                {showCalculationReview && canonicalResult && (
                    <CalculationReviewPanel
                        quoteResult={canonicalResult}
                        rawLines={rawQuoteLines}
                        displayCurrency={displayCurrency}
                    />
                )}

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

function CalculationReviewPanel({
    quoteResult,
    rawLines,
    displayCurrency,
}: {
    quoteResult: CanonicalQuoteResult;
    rawLines: RawQuoteLine[];
    displayCurrency: string;
}) {
    const [isOpen, setIsOpen] = useState(false);
    const taxTotal = quoteResult.tax_breakdown?.gst_amount || "0.00";
    const grandTotal = quoteResult.sell_total || "0.00";
    const fx = quoteResult.fx_applied;
    const warnings = [
        ...(quoteResult.warnings || []),
        ...quoteResult.line_items.flatMap((line) => lineWarnings(line, findRawLine(rawLines, line))),
    ].filter((item, index, items) => item && items.indexOf(item) === index);

    // Hide FX display if it's PGK to PGK with rate 1.0
    const showFxSummary = fx?.applied && !(fx.currency === "PGK" && Number(fx.rate) === 1.0);

    return (
        <div className="border-t border-slate-200 bg-white">
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left hover:bg-slate-50 transition-colors"
            >
                <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-md bg-blue-50 p-2 text-blue-600">
                        <Calculator className="h-4 w-4" />
                    </div>
                    <div>
                        <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-semibold text-slate-900">Pricing Breakdown & Audit</h3>
                            <span className="rounded bg-slate-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-slate-500 border border-slate-200">
                                Internal only
                            </span>
                        </div>
                        <p className="mt-1 text-sm text-slate-500">
                            Detailed calculation review, source flags, margins, and tax audit data.
                        </p>
                    </div>
                </div>
                {isOpen ? (
                    <ChevronDown className="h-5 w-5 shrink-0 text-slate-400" />
                ) : (
                    <ChevronRight className="h-5 w-5 shrink-0 text-slate-400" />
                )}
            </button>

            {isOpen && (
                <div className="space-y-6 border-t border-slate-100 bg-slate-50/30 px-6 py-6">
                    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        <ReviewMetric label="Total buy cost" value={displayMoney(quoteResult.total_cost_pgk, "PGK")} />
                        <ReviewMetric label="Total sell amount" value={displayMoney(quoteResult.total_sell_pgk, "PGK")} />
                        <ReviewMetric
                            label="Overall Gross margin"
                            value={`${displayMoney(quoteResult.margin_amount, "PGK")} (${displayPercent(quoteResult.margin_percent)})`}
                            highlight={Number(quoteResult.margin_percent) < 0 ? "error" : "success"}
                        />
                        <ReviewMetric label="GST/tax total" value={displayMoney(taxTotal, displayCurrency)} />
                        <ReviewMetric label="Grand total" value={displayMoney(grandTotal, displayCurrency)} />
                        <ReviewMetric
                            label="Base FX Conversion"
                            value={
                                showFxSummary
                                    ? `${displayValue(fx.currency)} → PGK at ${displayValue(fx.rate)}`
                                    : "Not applicable (PGK)"
                            }
                        />
                    </div>

                    {warnings.length > 0 && (
                        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 shadow-sm">
                            <div className="flex items-center gap-2 text-sm font-bold text-amber-900 uppercase tracking-tight">
                                <AlertTriangle className="h-4 w-4 text-amber-600" />
                                Warnings and exceptions
                            </div>
                            <ul className="mt-2 space-y-1 text-sm text-amber-800">
                                {warnings.map((warning) => (
                                    <li key={warning} className="flex items-start gap-2">
                                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-amber-400" />
                                        {warning}
                                    </li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="space-y-4">
                        <div className="text-xs font-bold uppercase tracking-widest text-slate-400 px-1">Line Item Details</div>
                        {quoteResult.line_items.map((line) => (
                            <CalculationLineDetails
                                key={line.line_id || `${line.product_code}-${line.sort_order}`}
                                line={line}
                                rawLine={findRawLine(rawLines, line)}
                                displayCurrency={displayCurrency}
                                fx={fx}
                            />
                        ))}
                    </div>

                    <div className="rounded-md border border-slate-200 bg-white p-4 text-[11px] leading-relaxed text-slate-500 shadow-sm italic">
                        <strong className="text-slate-700 not-italic uppercase tracking-tighter mr-1">Traceability Note:</strong>
                        Fields marked &quot;Not available&quot; may not yet be persisted in a structured format by the V4 engine or legacy adapter. 
                        Check &quot;Calculation notes&quot; for unstructured audit trails. Effective FX includes any applicable CAF adjustments.
                    </div>
                </div>
            )}
        </div>
    );
}

function ReviewMetric({ label, value, highlight }: { label: string; value: string; highlight?: "success" | "error" }) {
    let textClass = "text-slate-900";
    if (highlight === "success") textClass = "text-emerald-700";
    if (highlight === "error") textClass = "text-rose-700";

    return (
        <div className="rounded-md border border-slate-200 bg-white p-4 shadow-sm">
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
            <div className={`mt-1 text-sm font-bold ${textClass}`}>{value}</div>
        </div>
    );
}

function CalculationLineDetails({
    line,
    rawLine,
    displayCurrency,
    fx,
}: {
    line: CanonicalQuoteLineItem;
    rawLine?: RawQuoteLine;
    displayCurrency: string;
    fx: CanonicalQuoteResult["fx_applied"];
}) {
    const warnings = lineWarnings(line, rawLine);
    const buyCurrency = rawLine?.cost_fcy_currency || line.cost_currency || "PGK";
    const buyAmount = rawLine?.cost_fcy_currency ? rawLine.cost_fcy : line.cost_amount;
    const sellCurrency = line.sell_currency || displayCurrency;
    
    // Use new tax_rate field if available
    const gstRateRaw = line.tax_rate || rawLine?.gst_rate;
    const gstPercentStr = isAvailable(gstRateRaw) ? displayPercent(Number(gstRateRaw) * 100) : "Not available";
    const gstTreatment = `${displayValue(line.tax_code)} @ ${gstPercentStr}`;

    const isFcyLine = buyCurrency !== "PGK" || sellCurrency !== "PGK";
    const exchangeRate = line.exchange_rate || rawLine?.exchange_rate || fx?.rate;
    const cafPercent = fx?.caf_percent;

    // Effective rate calculation if possible
    let effectiveFx = "Not available";
    if (isFcyLine && isAvailable(exchangeRate)) {
        const rate = Number(exchangeRate);
        const caf = isAvailable(cafPercent) ? Number(cafPercent) / 100 : 0;
        effectiveFx = (rate * (1 + caf)).toFixed(6);
    } else if (!isFcyLine) {
        effectiveFx = "Not applicable (PGK)";
    }

    return (
        <div className="rounded-lg border border-slate-200 bg-white shadow-sm overflow-hidden">
            <details className="group">
                <summary className="flex cursor-pointer list-none items-center justify-between p-4 hover:bg-slate-50 transition-colors">
                    <div className="flex flex-col gap-1 pr-4">
                        <div className="font-bold text-slate-800 text-sm group-open:text-blue-700 transition-colors">{line.description}</div>
                        <div className="flex items-center gap-2 text-[11px] text-slate-500 font-medium">
                            <span className="bg-slate-100 px-1.5 py-0.5 rounded border border-slate-200">{line.product_code || "MISC"}</span>
                            <span>•</span>
                            <span className="uppercase tracking-tight text-blue-600">{sourceLabel(line, rawLine)}</span>
                            <span>•</span>
                            <span>{line.is_manual_override || rawLine?.is_manual_override ? "Manual Override" : "System Calculated"}</span>
                        </div>
                    </div>
                    <div className="flex items-center gap-4">
                        <div className="text-right">
                            <div className="text-sm font-bold text-slate-900">
                                {displayMoney(line.sell_amount, sellCurrency)}
                            </div>
                            <div className="text-[10px] text-slate-400 font-bold uppercase">Sell Ex-GST</div>
                        </div>
                        <ChevronRight className="h-4 w-4 text-slate-400 transition-transform group-open:rotate-90" />
                    </div>
                </summary>
                
                <div className="border-t border-slate-100 bg-slate-50/20">
                    {warnings.length > 0 && (
                        <div className="flex flex-wrap gap-2 px-4 py-2 bg-amber-50/50 border-b border-amber-100">
                            {warnings.map((warning) => (
                                <span key={warning} className="rounded bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-800 uppercase tracking-tight">
                                    {warning}
                                </span>
                            ))}
                        </div>
                    )}
                    
                    <div className="p-4 space-y-6">
                        {/* Section: Core Commercials */}
                        <div>
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3 border-b border-slate-100 pb-1">Line Core Metrics</div>
                            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                                <ReviewField label="Quantity" value={displayValue(line.quantity)} />
                                <ReviewField label="Unit / Basis" value={`${displayValue(line.unit_type)} / ${displayValue(line.basis)}`} />
                                <ReviewField label="Calculated Rate" value={isAvailable(line.rate) ? `${displayValue(line.rate)} / ${line.unit_type}` : "Not available"} />
                                <ReviewField
                                    label="Margin (vs PGK Cost)"
                                    value={`${displayMoney(line.margin_amount, "PGK")} (${displayPercent(line.margin_percent)})`}
                                    highlight={Number(line.margin_percent) < 0 ? "error" : "success"}
                                />

                            </div>
                        </div>

                        {/* Section: FX & Audit */}
                        <div>
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3 border-b border-slate-100 pb-1">FX & Currency Audit</div>
                            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                                <ReviewField label="Buy Amount" value={displayMoney(buyAmount, buyCurrency)} />
                                <ReviewField label="FX Rate Used" value={isFcyLine ? displayValue(exchangeRate) : "Not applicable"} />
                                <ReviewField label="CAF applied" value={isFcyLine && isAvailable(cafPercent) ? displayPercent(cafPercent) : "Not applicable"} />
                                <ReviewField label="Effective FX" value={effectiveFx} />
                            </div>
                        </div>

                        {/* Section: Taxation & Final */}
                        <div>
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-3 border-b border-slate-100 pb-1">Taxation & Fulfillment</div>
                            <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-4">
                                <ReviewField label="GST Treatment" value={gstTreatment} />
                                <ReviewField label="GST Amount" value={displayMoney(line.tax_amount, sellCurrency)} />
                                <ReviewField label="Total (Inc-GST)" value={displayMoney(Number(line.sell_amount || 0) + Number(line.tax_amount || 0), sellCurrency)} />
                                <ReviewField label="Rule Family" value={displayValue(line.rule_family)} />
                            </div>
                        </div>

                        {/* Calculation Notes */}
                        <div className="bg-white rounded border border-slate-200 p-3">
                            <div className="text-[10px] font-bold text-slate-400 uppercase tracking-widest mb-1">Internal Calculation Notes</div>
                            <div className="text-xs text-slate-700 leading-relaxed font-mono">
                                {line.calculation_notes || rawLine?.calculation_notes || "No additional calculation notes recorded."}
                            </div>
                        </div>
                    </div>
                </div>
            </details>
        </div>
    );
}

function ReviewField({ label, value, highlight }: { label: string; value: string; highlight?: "success" | "error" }) {
    let textClass = "text-slate-900";
    if (highlight === "success") textClass = "text-emerald-700";
    if (highlight === "error") textClass = "text-rose-700";

    return (
        <div>
            <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
            <div className={`mt-1 break-words text-xs font-semibold ${textClass}`}>{value}</div>
        </div>
    );
}

// Helper for section styling - Refined for visual hierarchy & lighter feel
function getSectionStyle() {
    return {
        wrapper: "mb-6 rounded-lg border border-slate-200 overflow-hidden bg-white shadow-sm", // Clean card style
        header: "bg-white hover:bg-slate-50 border-b border-slate-100 transition-colors", // Lighter header
        title: "text-slate-900", // Stronger title contrast
        iconBg: "bg-blue-50 text-blue-600", // Subtler icon background
        borderLeft: "border-l-[4px] border-l-blue-500" // Consistent accent
    };
}

// Bucket Section Component
function BucketSection({
    title,
    lines,
    displayCurrency,
    isShowingFCY,
    icon,
    // colorClass prop is present in parent but ignored here to enforce standardized Blue theme
}: {
    title: string;
    lines: BreakdownLine[];
    displayCurrency: string;
    isShowingFCY: boolean;
    icon: React.ReactNode;
    colorClass?: string;
}) {
    // Default to collapsed for Freight/Dest, maybe Expanded for Origin? 
    // User requested default collapsed previously.
    const [isExpanded, setIsExpanded] = useState(false);
    const styles = getSectionStyle();

    // Calculate subtotal for this bucket
    const bucketTotal = isShowingFCY
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    return (
        <div className={styles.wrapper}>
            <button
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
                            {!isExpanded && (
                                <span className="flex items-center justify-center bg-slate-100 text-slate-500 text-[11px] font-semibold h-6 px-2 rounded-full">
                                    {lines.length}
                                </span>
                            )}
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
                <div className="p-6 pt-2 bg-slate-50/30">
                    <div className="bg-white rounded-lg border border-slate-200 shadow-sm overflow-hidden">
                        <Table>
                            <TableHeader className="bg-slate-50/80">
                                <TableRow className="hover:bg-transparent border-b border-slate-100">
                                    <TableHead className="w-[50%] h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 pl-6">Description</TableHead>
                                    <TableHead className="text-right h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500">Sell (Ex GST)</TableHead>
                                    <TableHead className="text-center h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 w-[120px]">GST</TableHead>
                                    <TableHead className="text-right h-10 text-[11px] font-bold uppercase tracking-wider text-slate-500 pr-6">Total</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {lines.map((line, index: number) => (
                                    <ChargeRow
                                        key={index}
                                        line={line}
                                        displayCurrency={displayCurrency}
                                        isShowingFCY={isShowingFCY}
                                    />
                                ))}
                            </TableBody>
                        </Table>
                    </div>
                </div>
            )}
        </div>
    );
}

// Individual Charge Row
function ChargeRow({
    line,
    displayCurrency,
    isShowingFCY
}: {
    line: BreakdownLine;
    displayCurrency: string;
    isShowingFCY: boolean;
}) {
    // Robust line mapping
    const sellExGst = isShowingFCY 
        ? (line.sell_fcy || line.sell_pgk) 
        : (line.sell_pgk || line.sell_fcy);
        
    const gstAmountVal = parseFloat(line.gst_amount || '0');

    // Determine GST display text
    let gstDisplay: React.ReactNode = '—';
    if (gstAmountVal > 0) {
        gstDisplay = formatAmount(gstAmountVal, displayCurrency);
    } else {
        // Updated to non-interactive muted text
        gstDisplay = <span className="text-[10px] font-medium text-slate-400 uppercase tracking-wide">Exempt</span>;
    }

    const total = isShowingFCY
        ? (line.sell_fcy_incl_gst || line.sell_fcy)
        : (line.sell_pgk_incl_gst || line.sell_pgk || line.sell_fcy_incl_gst);

    return (
        <TableRow className="hover:bg-blue-50/30 border-b border-slate-50 last:border-0 transition-colors">
            <TableCell className="py-4 pl-6">
                <div className="font-medium text-slate-700 text-sm">
                    {line.description}
                </div>
                {/* Reduced emphasis on line codes - secondary info */}
                <div className="text-[10px] text-slate-400 uppercase tracking-wider mt-1 font-mono opacity-80">
                    {line.component || 'MISC'}
                </div>
            </TableCell>
            <TableCell className="text-right font-mono text-sm text-slate-600 py-4">
                {formatAmount(sellExGst, displayCurrency)}
            </TableCell>
            <TableCell className="text-center py-4">
                {/* GST Column centered and clean */}
                <div className="flex items-center justify-center">
                    {gstDisplay}
                </div>
            </TableCell>
            <TableCell className="text-right font-mono text-sm font-bold text-slate-800 py-4 pr-6">
                {formatAmount(total, displayCurrency)}
            </TableCell>
        </TableRow>
    );
}
