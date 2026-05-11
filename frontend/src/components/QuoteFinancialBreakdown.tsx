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

    return (
        <div className="border-t border-slate-200 bg-white">
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left hover:bg-slate-50"
            >
                <div className="flex items-start gap-3">
                    <div className="mt-0.5 rounded-md bg-slate-100 p-2 text-slate-600">
                        <Calculator className="h-4 w-4" />
                    </div>
                    <div>
                        <div className="flex flex-wrap items-center gap-2">
                            <h3 className="text-base font-semibold text-slate-900">Pricing Breakdown</h3>
                            <span className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-semibold uppercase text-slate-500">
                                Internal only
                            </span>
                        </div>
                        <p className="mt-1 text-sm text-slate-500">
                            Review calculation inputs, source flags, margins, FX, CAF, and metadata gaps before finalizing.
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
                <div className="space-y-5 border-t border-slate-100 px-6 py-5">
                    <div className="grid gap-3 md:grid-cols-3">
                        <ReviewMetric label="Total buy cost" value={displayMoney(quoteResult.total_cost_pgk, "PGK")} />
                        <ReviewMetric label="Total sell amount" value={displayMoney(quoteResult.total_sell_pgk, "PGK")} />
                        <ReviewMetric label="Gross margin" value={`${displayMoney(quoteResult.margin_amount, "PGK")} (${displayPercent(quoteResult.margin_percent)})`} />
                        <ReviewMetric label="GST/tax total" value={displayMoney(taxTotal, displayCurrency)} />
                        <ReviewMetric label="Grand total" value={displayMoney(grandTotal, displayCurrency)} />
                        <ReviewMetric
                            label="Currency conversion"
                            value={
                                fx?.applied
                                    ? `${displayValue(fx.currency)} -> PGK at ${displayValue(fx.rate)}`
                                    : "No FCY conversion recorded"
                            }
                        />
                    </div>

                    {warnings.length > 0 && (
                        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
                            <div className="flex items-center gap-2 text-sm font-semibold text-amber-900">
                                <AlertTriangle className="h-4 w-4" />
                                Warnings and exceptions
                            </div>
                            <ul className="mt-2 space-y-1 text-sm text-amber-900">
                                {warnings.map((warning) => (
                                    <li key={warning}>{warning}</li>
                                ))}
                            </ul>
                        </div>
                    )}

                    <div className="space-y-3">
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

                    <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 text-xs text-slate-600">
                        Unavailable in this version: explicit buy-rate basis, FX direction, effective FX after CAF,
                        minimum margin rule, and customer override/discount detail unless it has been written into
                        calculation notes. These fields need structured persistence from the V4 engines/adapter for
                        full audit traceability.
                    </div>
                </div>
            )}
        </div>
    );
}

function ReviewMetric({ label, value }: { label: string; value: string }) {
    return (
        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
            <div className="text-[11px] font-semibold uppercase text-slate-500">{label}</div>
            <div className="mt-1 text-sm font-semibold text-slate-900">{value}</div>
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
    const gstTreatment = `${displayValue(line.tax_code)} at ${displayPercent(rawLine?.gst_rate ? Number(rawLine.gst_rate) * 100 : undefined)}`;

    return (
        <details className="rounded-md border border-slate-200 bg-white">
            <summary className="cursor-pointer list-none px-4 py-3 hover:bg-slate-50">
                <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                    <div>
                        <div className="font-medium text-slate-900">{line.description}</div>
                        <div className="mt-1 text-xs text-slate-500">
                            {displayValue(line.product_code)} | {sourceLabel(line, rawLine)} | {line.is_manual_override || rawLine?.is_manual_override ? "Manual" : "System-calculated"}
                        </div>
                    </div>
                    <div className="text-sm font-semibold text-slate-900">
                        {displayMoney(line.sell_amount, sellCurrency)}
                    </div>
                </div>
                {warnings.length > 0 && (
                    <div className="mt-2 flex flex-wrap gap-2">
                        {warnings.map((warning) => (
                            <span key={warning} className="rounded border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-800">
                                {warning}
                            </span>
                        ))}
                    </div>
                )}
            </summary>
            <div className="grid gap-x-5 gap-y-3 border-t border-slate-100 px-4 py-4 text-sm md:grid-cols-2 lg:grid-cols-3">
                <ReviewField label="Charge description" value={line.description} />
                <ReviewField label="Product code" value={line.product_code} />
                <ReviewField label="Buy amount" value={displayMoney(buyAmount, buyCurrency)} />
                <ReviewField label="Buy currency" value={buyCurrency} />
                <ReviewField label="Sell amount" value={displayMoney(line.sell_amount, sellCurrency)} />
                <ReviewField label="Sell currency" value={sellCurrency} />
                <ReviewField label="Quantity" value={displayValue(line.quantity)} />
                <ReviewField label="Unit / basis" value={`${displayValue(line.unit_type)} / ${displayValue(line.basis)}`} />
                <ReviewField label="Buy rate used" value="Not available" />
                <ReviewField label="FX rate used" value={displayValue(rawLine?.exchange_rate || fx?.rate)} />
                <ReviewField label="FX direction" value="Not available" />
                <ReviewField label="CAF applied" value={fx?.caf_percent ? displayPercent(fx.caf_percent) : "Not available"} />
                <ReviewField label="Effective FX after CAF" value="Not available" />
                <ReviewField label="Margin used" value={`${displayMoney(line.margin_amount, "PGK")} (${displayPercent(line.margin_percent)})`} />
                <ReviewField label="Minimum margin rule" value="Not available" />
                <ReviewField label="Customer override/discount" value={line.calculation_notes?.includes("discount") ? line.calculation_notes : "Not available"} />
                <ReviewField label="GST/tax treatment" value={gstTreatment} />
                <ReviewField label="Final calculated sell" value={displayMoney(Number(line.sell_amount || 0) + Number(line.tax_amount || 0), sellCurrency)} />
                <ReviewField label="Pricing source" value={sourceLabel(line, rawLine)} />
                <ReviewField label="Entry mode" value={line.is_manual_override || rawLine?.is_manual_override ? "Manually entered" : "System-calculated"} />
                <ReviewField label="Calculation notes" value={line.calculation_notes || rawLine?.calculation_notes || "Not available"} />
            </div>
        </details>
    );
}

function ReviewField({ label, value }: { label: string; value: string }) {
    return (
        <div>
            <div className="text-[11px] font-semibold uppercase text-slate-500">{label}</div>
            <div className="mt-1 break-words text-slate-900">{value}</div>
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
