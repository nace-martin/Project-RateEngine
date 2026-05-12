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
import { AlertTriangle, Calculator, ChevronDown, ChevronRight, Package, MapPin, ReceiptText, Plane, Landmark, Globe, Database, Edit3, ShoppingCart, TrendingUp, TrendingDown, Info, ShieldCheck, Tag, Zap } from "lucide-react";
import { Badge } from "@/components/ui/badge";

interface QuoteFinancialBreakdownProps {
    result: QuoteComputeResult | V3QuoteComputeResponse;
}

type LooseRecord = Record<string, unknown>;
type BreakdownLine = SellLine & {
    sell_fcy_currency?: string;
    margin_percent?: string;
    margin_amount?: string;
    exchange_rate?: string;
    source?: string;
    is_informational?: boolean;
    tax_code?: string;
    tax_rate?: string;
    unit_type?: string;
    rate?: string;
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
        margin_percent: item.margin_percent || "0",
        margin_amount: item.margin_amount || "0",
        exchange_rate: item.exchange_rate || "0",
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


type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION' | 'CUSTOMS' | 'OTHER';

// Get bucket for a line
function getBucket(line: BreakdownLine): BucketType {
    const leg = line.leg || '';
    const code = (line.component || '').toUpperCase();

    // Customs / Regulatory logic
    if (['CUS', 'DUTY', 'TAX', 'GST', 'VAT', 'ENTRY', 'ADMIN', 'PERMIT'].some(s => code.includes(s))) {
        return 'CUSTOMS';
    }

    if (leg === 'ORIGIN') return 'ORIGIN';
    if (leg === 'DESTINATION') return 'DESTINATION';
    if (leg === 'MAIN' || leg === 'FREIGHT' || ['AF', 'FSC', 'SSC', 'ISS', 'WRS'].includes(code)) return 'FREIGHT';

    return 'OTHER';
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

function lineWarnings(line?: CanonicalQuoteLineItem, rawLine?: RawQuoteLine): string[] {
    const warnings: string[] = [];
    if (rawLine?.is_rate_missing) warnings.push("Missing buy rate");
    if (line?.is_manual_override || rawLine?.is_manual_override) warnings.push("Manual override");
    if (line?.rate_source === "FALLBACK_RULE") warnings.push("FX or rate fallback");
    return warnings;
}

function sourceLabel(line?: CanonicalQuoteLineItem, rawLine?: RawQuoteLine): string {
    if (line?.is_spot_sourced || rawLine?.is_spot_sourced) return "SPOT";
    if (line?.is_manual_override || rawLine?.is_manual_override) return "Manual entry";

    const rateSource = line?.rate_source || rawLine?.rate_source;
    if (rateSource === "MANUAL_OVERRIDE") return "Manual entry";
    if (rateSource === "PARTNER_SPOT") return "SPOT";
    if (rateSource === "DB_TARIFF") return "V4 rate card";
    if (rateSource === "FALLBACK_RULE") return "Fallback rule";
    if (rateSource === "IMPORTED_RATECARD") return "V4 rate card";

    return displayValue(rateSource);
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
        CUSTOMS: [],
        OTHER: [],
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
                {/* COMMERCIAL SECTIONS */}
                <div className="p-4 space-y-4">
                    {buckets.ORIGIN.length > 0 && (
                        <BucketSection
                            title="Origin Charges"
                            lines={buckets.ORIGIN}
                            rawLines={rawQuoteLines}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            icon={<Package className="w-4 h-4 text-blue-600" />}
                            isInternal={showCalculationReview}
                        />
                    )}
                    {buckets.FREIGHT.length > 0 && (
                        <BucketSection
                            title="Freight / Carrier Charges"
                            lines={buckets.FREIGHT}
                            rawLines={rawQuoteLines}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            icon={<Plane className="h-4 w-4 text-blue-600" />}
                            isInternal={showCalculationReview}
                        />
                    )}
                    {buckets.DESTINATION.length > 0 && (
                        <BucketSection
                            title="Destination Charges"
                            lines={buckets.DESTINATION}
                            rawLines={rawQuoteLines}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            icon={<MapPin className="h-4 w-4 text-blue-600" />}
                            isInternal={showCalculationReview}
                        />
                    )}
                    {buckets.CUSTOMS.length > 0 && (
                        <BucketSection
                            title="Customs / Regulatory"
                            lines={buckets.CUSTOMS}
                            rawLines={rawQuoteLines}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            icon={<Landmark className="h-4 w-4 text-blue-600" />}
                            isInternal={showCalculationReview}
                        />
                    )}
                    {buckets.OTHER.length > 0 && (
                        <BucketSection
                            title="Other / Manual"
                            lines={buckets.OTHER}
                            rawLines={rawQuoteLines}
                            displayCurrency={displayCurrency}
                            isShowingFCY={isShowingFCY}
                            icon={<Info className="h-4 w-4 text-blue-600" />}
                            isInternal={showCalculationReview}
                        />
                    )}
                </div>

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

function PricingHealthCheck({
    quoteResult,
    rawLines,
}: {
    quoteResult: CanonicalQuoteResult;
    rawLines: RawQuoteLine[];
}) {
    const fx = quoteResult.fx_applied;
    const margin = parseFloat(String(quoteResult.margin_percent || "0"));
    const hasManual = quoteResult.line_items.some(l => l.is_manual_override);
    const hasSpot = quoteResult.line_items.some(l => l.is_spot_sourced);
    const hasMissingBuy = rawLines.some(l => l.is_rate_missing);

    // Margin Status
    let marginStatus: "success" | "warning" | "error" = "success";
    let marginLabel = "Healthy";
    if (margin < 0) {
        marginStatus = "error";
        marginLabel = "Negative";
    } else if (margin < 15) {
        marginStatus = "warning";
        marginLabel = "Low";
    }

    // GST Status & Reconciliation
    const summaryGst = parseFloat(quoteResult.tax_breakdown?.gst_amount || "0");
    const lineGstTotal = quoteResult.line_items.reduce((sum, l) => sum + parseFloat(l.tax_amount || "0"), 0);
    const gstDiff = Math.abs(summaryGst - lineGstTotal);
    const hasTaxWarning = quoteResult.warnings.some(w => w.toLowerCase().includes("tax") || w.toLowerCase().includes("gst")) || gstDiff > 0.05;

    const gstStatus = hasTaxWarning ? "warning" : "success";
    const gstLabel = hasTaxWarning ? "Needs Review" : "OK";

    // FX Status
    const isPgkOnly = fx.currency === "PGK" && (Number(fx.rate) === 1.0 || !fx.rate);
    const fxStatus = (fx.applied && !isPgkOnly) ? "success" : isPgkOnly ? "neutral" : "warning";
    const fxLabel = (fx.applied && !isPgkOnly) ? "Applied" : isPgkOnly ? "N/A" : "Missing data";

    // Source mix
    let sourceLabelText = "V4 Tariff";
    if (hasSpot && hasManual) sourceLabelText = "Mixed (SPOT/Manual)";
    else if (hasSpot) sourceLabelText = "SPOT";
    else if (hasManual) sourceLabelText = "Manual entry";

    const exceptions = [
        ...(quoteResult.warnings || []),
        ...quoteResult.line_items.flatMap((line) => lineWarnings(line, findRawLine(rawLines, line))),
    ].filter((item, index, items) => item && items.indexOf(item) === index)
     .filter(w => !w.toLowerCase().includes("metadata")); // Filter noise

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
                <HealthCard
                    label="Margin"
                    value={`${margin.toFixed(1)}%`}
                    subValue={marginLabel}
                    status={marginStatus}
                    icon={margin < 0 ? <TrendingDown className="h-4 w-4" /> : <TrendingUp className="h-4 w-4" />}
                />
                <HealthCard
                    label="GST/Tax"
                    value={gstLabel}
                    subValue={hasTaxWarning ? "Variance detected" : "Reconciled"}
                    status={gstStatus}
                    icon={<Landmark className="h-4 w-4" />}
                />
                <HealthCard
                    label="FX/CAF"
                    value={fxLabel}
                    subValue={fx.currency && !isPgkOnly ? `Base: ${fx.currency}` : undefined}
                    status={fxStatus}
                    icon={<Globe className="h-4 w-4" />}
                />
                <HealthCard
                    label="Source"
                    value={sourceLabelText}
                    status="neutral"
                    icon={<Database className="h-4 w-4" />}
                />
                <HealthCard
                    label="Overrides"
                    value={hasManual ? "Present" : "None"}
                    status={hasManual ? "warning" : "success"}
                    icon={<Edit3 className="h-4 w-4" />}
                />
                <HealthCard
                    label="Buy Rates"
                    value={hasMissingBuy ? "Missing" : "All Found"}
                    status={hasMissingBuy ? "error" : "success"}
                    icon={<ShoppingCart className="h-4 w-4" />}
                />
            </div>

            {exceptions.length > 0 && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <div className="flex items-center gap-2 text-sm font-bold text-amber-800 uppercase tracking-tight mb-2">
                        <AlertTriangle className="h-4 w-4" />
                        {exceptions.length} Pricing Exceptions Found
                    </div>
                    <ul className="space-y-1.5">
                        {exceptions.map((ex, i) => (
                            <li key={i} className="text-xs text-amber-700 flex items-center gap-2">
                                <span className="h-1 w-1 rounded-full bg-amber-400" />
                                {ex}
                            </li>
                        ))}
                    </ul>
                </div>
            )}
        </div>
    );
}

function HealthCard({
    label,
    value,
    subValue,
    status,
    icon
}: {
    label: string;
    value: string;
    subValue?: string;
    status: "success" | "warning" | "error" | "neutral";
    icon: React.ReactNode;
}) {
    const statusClasses = {
        success: "bg-emerald-50 text-emerald-700 border-emerald-100",
        warning: "bg-amber-50 text-amber-700 border-amber-100",
        error: "bg-rose-50 text-rose-700 border-rose-100",
        neutral: "bg-slate-50 text-slate-600 border-slate-100",
    };

    return (
        <div className={`rounded-lg border p-3 flex flex-col gap-1 ${statusClasses[status]}`}>
            <div className="flex items-center justify-between opacity-80">
                <span className="text-[10px] font-bold uppercase tracking-wider">{label}</span>
                {icon}
            </div>
            <div className="text-sm font-bold truncate">{value}</div>
            {subValue && <div className="text-[9px] font-medium uppercase">{subValue}</div>}
        </div>
    );
}

function CalculationReviewPanel({
    quoteResult,
    rawLines,
}: {
    quoteResult: CanonicalQuoteResult;
    rawLines: RawQuoteLine[];
}) {
    const [isOpen, setIsOpen] = useState(false);

    return (
        <div className="border-t border-slate-200 bg-slate-50/50">
            <button
                type="button"
                onClick={() => setIsOpen(!isOpen)}
                className="flex w-full items-center justify-between gap-4 px-6 py-4 text-left hover:bg-slate-100/80 transition-colors"
            >
                <div className="flex items-center gap-3">
                    <Calculator className="h-4 w-4 text-slate-400" />
                    <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-slate-700 uppercase tracking-tight">Pricing Health Check</span>
                        <span className="rounded bg-slate-200/50 px-1.5 py-0.5 text-[9px] font-bold uppercase text-slate-500">
                            Internal Audit
                        </span>
                    </div>
                </div>
                <div className="flex items-center gap-2 text-slate-400">
                    <span className="text-xs font-medium">{isOpen ? "Hide Audit" : "Show Audit Details"}</span>
                    {isOpen ? (
                        <ChevronDown className="h-4 w-4" />
                    ) : (
                        <ChevronRight className="h-4 w-4" />
                    )}
                </div>
            </button>

            {isOpen && (
                <div className="space-y-6 border-t border-slate-200/60 bg-white px-6 py-6 animate-in fade-in slide-in-from-top-1 duration-200">
                    <PricingHealthCheck
                        quoteResult={quoteResult}
                        rawLines={rawLines}
                    />

                    <div className="rounded border border-slate-100 bg-slate-50/50 p-3 text-[10px] text-slate-500 leading-relaxed italic">
                        Internal use only. This section provides a commercial health check of the quote pricing logic.
                        Audit flags represent risks to margin, compliance, or data integrity.
                    </div>
                </div>
            )}
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
    rawLines,
    displayCurrency,
    isShowingFCY,
    icon,
    isInternal,
}: {
    title: string;
    lines: BreakdownLine[];
    rawLines: RawQuoteLine[];
    displayCurrency: string;
    isShowingFCY: boolean;
    icon: React.ReactNode;
    isInternal?: boolean;
}) {
    const [isExpanded, setIsExpanded] = useState(false);
    const styles = getSectionStyle();

    // Calculate subtotal for this bucket
    const bucketTotal = isShowingFCY
        ? calculateBucketTotal(lines, 'sell_fcy')
        : calculateBucketTotal(lines, 'sell_pgk');

    // Calculate margin for this bucket if internal
    let bucketMarginText = "";
    let bucketMarginStatus: "success" | "warning" | "error" = "success";
    let exceptionCount = 0;

    if (isInternal) {
        const totalSellPgk = lines.reduce((sum, l) => sum + parseFloat(String(l.sell_pgk || "0")), 0);
        const totalMarginPgk = lines.reduce((sum, l) => sum + parseFloat(String(l.margin_amount || "0")), 0);
        const marginPct = totalSellPgk > 0 ? (totalMarginPgk / totalSellPgk) * 100 : 0;

        bucketMarginText = `${marginPct.toFixed(1)}% margin`;
        if (marginPct < 0) bucketMarginStatus = "error";
        else if (marginPct < 15) bucketMarginStatus = "warning";

        // Count exceptions in this bucket
        lines.forEach(line => {
            const raw = rawLines.find(r => (r.product_code || r.component) === line.component && r.description === line.description);
            if (raw?.is_rate_missing) exceptionCount++;
            if (raw?.is_manual_override) exceptionCount++;
        });
    }

    return (
        <div className={styles.wrapper}>
            <button
                onClick={() => setIsExpanded(!isExpanded)}
                className={`w-full flex items-center justify-between p-4 ${styles.header} ${styles.borderLeft}`}
            >
                <div className="flex items-center gap-3">
                    <div className={`p-2 rounded-lg ${styles.iconBg}`}>
                        {icon}
                    </div>
                    <div className="text-left">
                        <div className="flex items-center gap-2">
                            <h3 className={`text-sm font-bold tracking-tight ${styles.title}`}>
                                {title}
                            </h3>
                            {isInternal && bucketMarginText && (
                                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                                    bucketMarginStatus === "error" ? "bg-rose-100 text-rose-700" :
                                    bucketMarginStatus === "warning" ? "bg-amber-100 text-amber-700" :
                                    "bg-emerald-100 text-emerald-700"
                                }`}>
                                    {bucketMarginText}
                                </span>
                            )}
                            {exceptionCount > 0 && (
                                <span className="flex items-center gap-1 bg-amber-100 text-amber-700 text-[9px] font-bold px-1.5 py-0.5 rounded">
                                    <AlertTriangle className="h-2.5 w-2.5" />
                                    {exceptionCount}
                                </span>
                            )}
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    <div className="text-right">
                        <p className="text-[9px] text-slate-400 font-bold uppercase tracking-wider">Subtotal</p>
                        <p className="text-sm font-bold text-slate-900 mono-font">
                            {formatAmount(bucketTotal, displayCurrency)}
                        </p>
                    </div>
                    {isExpanded ? (
                        <ChevronDown className="w-4 h-4 text-slate-400" />
                    ) : (
                        <ChevronRight className="w-4 h-4 text-slate-400" />
                    )}
                </div>
            </button>

            {isExpanded && (
                <div className="bg-slate-50/30 border-t border-slate-100">
                    <Table>
                        <TableHeader className="bg-slate-50/80">
                            <TableRow className="hover:bg-transparent border-b border-slate-100">
                                <TableHead className="w-[45%] h-8 text-[10px] font-bold uppercase tracking-wider text-slate-500 pl-4">Description</TableHead>
                                <TableHead className="text-right h-8 text-[10px] font-bold uppercase tracking-wider text-slate-500">Sell (Ex GST)</TableHead>
                                <TableHead className="text-center h-8 text-[10px] font-bold uppercase tracking-wider text-slate-500 w-[100px]">GST</TableHead>
                                <TableHead className="text-right h-8 text-[10px] font-bold uppercase tracking-wider text-slate-500 pr-4">Total</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {lines.map((line, index: number) => (
                                <ChargeRow
                                    key={index}
                                    line={line}
                                    rawLine={rawLines.find(r => (r.product_code || r.component) === line.component && r.description === line.description)}
                                    displayCurrency={displayCurrency}
                                    isShowingFCY={isShowingFCY}
                                    isInternal={isInternal}
                                />
                            ))}
                        </TableBody>
                    </Table>
                </div>
            )}
        </div>
    );
}

// Individual Charge Row
function ChargeRow({
    line,
    rawLine,
    displayCurrency,
    isShowingFCY,
    isInternal
}: {
    line: BreakdownLine;
    rawLine?: RawQuoteLine;
    displayCurrency: string;
    isShowingFCY: boolean;
    isInternal?: boolean;
}) {
    const [isExpanded, setIsExpanded] = useState(false);

    const sellExGst = isShowingFCY
        ? (line.sell_fcy || line.sell_pgk)
        : (line.sell_pgk || line.sell_fcy);

    const gstAmountVal = parseFloat(line.gst_amount || '0');

    let gstDisplay: React.ReactNode = '—';
    if (gstAmountVal > 0) {
        gstDisplay = formatAmount(gstAmountVal, displayCurrency);
    } else {
        gstDisplay = <span className="text-[9px] font-medium text-slate-400 uppercase">Exempt</span>;
    }

    const total = isShowingFCY
        ? (line.sell_fcy_incl_gst || line.sell_fcy)
        : (line.sell_pgk_incl_gst || line.sell_pgk || line.sell_fcy_incl_gst);

    const hasWarning = isInternal && (rawLine?.is_rate_missing || rawLine?.is_manual_override);

    // logic flags for compact badges in row
    const source = sourceLabel(undefined, rawLine);
    const buyCurrency = rawLine?.cost_fcy_currency || "PGK";
    const exchangeRate = parseFloat(rawLine?.exchange_rate || "0");
    const isFcy = buyCurrency !== "PGK" && exchangeRate !== 0 && exchangeRate !== 1;
    const notes = (rawLine?.calculation_notes || "").toLowerCase();
    const isGstExempt = parseFloat(rawLine?.gst_rate || "0") === 0;

    return (
        <>
            <TableRow
                className={`group border-b border-slate-50 last:border-0 transition-colors ${
                    isExpanded ? "bg-blue-50/50" : "hover:bg-slate-50/80"
                } ${hasWarning ? "bg-amber-50/30" : ""}`}
            >
                <TableCell className="py-3 pl-4">
                    <div className="flex items-start gap-2">
                        {isInternal && (
                            <button
                                onClick={() => setIsExpanded(!isExpanded)}
                                className="mt-1 p-0.5 hover:bg-slate-200 rounded transition-colors text-slate-400"
                                title="View Pricing Logic"
                            >
                                {isExpanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
                            </button>
                        )}
                        <div className="flex flex-col gap-1">
                            <div className="font-medium text-slate-700 text-xs flex items-center gap-1.5 flex-wrap">
                                {line.description}
                                {hasWarning && <AlertTriangle className="h-3 w-3 text-amber-500" />}

                                {isInternal && (
                                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                                        <Badge variant="outline" className="px-1 py-0 text-[8px] h-3.5 bg-slate-50 text-slate-400 border-slate-200 font-medium uppercase">
                                            {source}
                                        </Badge>
                                        {isFcy && <Globe className="h-2.5 w-2.5 text-blue-400" />}
                                        {notes.includes("caf") && <Zap className="h-2.5 w-2.5 text-amber-400" />}
                                        {isGstExempt ? <ShieldCheck className="h-2.5 w-2.5 text-slate-300" /> : <Landmark className="h-2.5 w-2.5 text-emerald-400" />}
                                    </div>
                                )}
                            </div>
                            <div className="flex items-center gap-2">
                                <div className="text-[9px] text-slate-400 uppercase tracking-wider font-mono">
                                    {line.component || 'MISC'}
                                </div>
                                {isInternal && (
                                    <button
                                        onClick={() => setIsExpanded(!isExpanded)}
                                        className="text-[9px] font-bold text-blue-600 hover:underline flex items-center gap-0.5"
                                    >
                                        {isExpanded ? "Hide Logic" : "View Pricing Logic"}
                                    </button>
                                )}
                            </div>
                        </div>
                    </div>
                </TableCell>
                <TableCell className="text-right font-mono text-xs text-slate-600 py-3 align-top">
                    {formatAmount(sellExGst, displayCurrency)}
                </TableCell>
                <TableCell className="text-center py-3 align-top">
                    {gstDisplay}
                </TableCell>
                <TableCell className="text-right font-mono text-xs font-bold text-slate-800 py-3 pr-4 align-top">
                    {formatAmount(total, displayCurrency)}
                </TableCell>
            </TableRow>

            {isInternal && isExpanded && (
                <TableRow className="bg-white border-b border-slate-200/60 shadow-inner">
                    <TableCell colSpan={4} className="py-6 px-10">
                        <PricingLogicTrace
                            line={line}
                            rawLine={rawLine}
                        />
                    </TableCell>
                </TableRow>
            )}
        </>
    );
}

function LogicBadge({
    label,
    variant = "outline",
    icon: Icon
}: {
    label: string;
    variant?: "outline" | "default" | "secondary" | "destructive" | "success" | "warning";
    icon?: React.ElementType;
}) {
    const variantClasses = {
        outline: "bg-white text-slate-600 border-slate-200",
        default: "bg-slate-100 text-slate-700 border-transparent",
        secondary: "bg-blue-50 text-blue-700 border-blue-100",
        destructive: "bg-rose-50 text-rose-700 border-rose-100",
        success: "bg-emerald-50 text-emerald-700 border-emerald-100",
        warning: "bg-amber-50 text-amber-700 border-amber-100",
    };

    return (
        <Badge variant="outline" className={`px-1.5 py-0 text-[9px] font-bold uppercase tracking-tight gap-1 flex items-center shadow-none ${variantClasses[variant as keyof typeof variantClasses] || variantClasses.outline}`}>
            {Icon && <Icon className="h-2.5 w-2.5" />}
            {label}
        </Badge>
    );
}

function PricingLogicTrace({
    line,
    rawLine,
}: {
    line: BreakdownLine;
    rawLine?: RawQuoteLine;
}) {
    const source = sourceLabel(undefined, rawLine);
    const buyCurrency = rawLine?.cost_fcy_currency || "PGK";
    const buyAmount = rawLine?.cost_fcy || rawLine?.cost_pgk || "0";
    const exchangeRate = parseFloat(rawLine?.exchange_rate || "0");
    const isFcy = buyCurrency !== "PGK" && exchangeRate !== 0 && exchangeRate !== 1;

    // Attempt to detect logic from notes or rule families
    const notes = (rawLine?.calculation_notes || "").toLowerCase();
    const isMinMargin = notes.includes("minimum margin") || notes.includes("min margin");
    const isDiscount = notes.includes("discount") || rawLine?.rule_family?.toLowerCase().includes("discount");

    const gstRate = parseFloat(rawLine?.gst_rate || "0");
    const isGstExempt = gstRate === 0;

    // Generate Human-Readable Explanation
    let explanation = `RateEngine used the ${source}`;
    if (isFcy) {
        explanation += `, converted ${buyCurrency} buy cost to PGK`;
        if (notes.includes("caf")) explanation += " (including CAF adjustment)";
    }

    if (isDiscount) explanation += ", applied a customer discount";
    if (isMinMargin) explanation += ", enforced the minimum margin rule";
    else explanation += ", and applied standard margin";

    explanation += ` to calculate the final sell amount. ${isGstExempt ? "GST was not applicable for this line." : `GST was applied at ${displayPercent(gstRate * 100)}.`}`;

    return (
        <div className="space-y-5">
            {/* Logic Badges */}
            <div className="flex flex-wrap gap-1.5">
                <LogicBadge label={source} icon={Database} variant="secondary" />
                {isFcy && <LogicBadge label="FX Converted" icon={Globe} variant="outline" />}
                {notes.includes("caf") && <LogicBadge label="CAF Applied" icon={Zap} variant="outline" />}
                {isMinMargin && <LogicBadge label="Minimum Margin" icon={ShieldCheck} variant="warning" />}
                {isDiscount && <LogicBadge label="Discount Applied" icon={Tag} variant="success" />}
                {!isGstExempt ? <LogicBadge label="GST Applied" icon={Landmark} variant="outline" /> : <LogicBadge label="GST Exempt" icon={ShieldCheck} variant="default" />}
            </div>

            {/* Explanation Sentence */}
            <div className="flex items-start gap-2.5 p-3 rounded-md bg-blue-50/50 border border-blue-100/50 text-xs text-blue-800 leading-relaxed italic">
                <Info className="h-4 w-4 text-blue-400 shrink-0 mt-0.5" />
                <span>{explanation}</span>
            </div>

            {/* Step-by-Step Trace */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-5">
                <TraceStep
                    label="Pricing Source"
                    value={source}
                    subValue={rawLine?.basis ? `Basis: ${rawLine.basis}` : undefined}
                />
                <TraceStep
                    label="Buy Rate / Cost"
                    value={displayMoney(buyAmount, buyCurrency)}
                    subValue={rawLine?.rate ? `${parseFloat(rawLine.rate).toFixed(4)} / ${rawLine.unit_type || "unit"}` : "Flat amount"}
                />

                {isFcy && (
                    <>
                        <TraceStep
                            label="Currency Exchange"
                            value={`${buyCurrency} → PGK`}
                            subValue={`Base Rate: ${rawLine?.base_exchange_rate || rawLine?.exchange_rate}`}
                        />
                        {parseFloat(String(rawLine?.caf_percent || "0")) !== 0 && (
                            <TraceStep
                                label="CAF Adjustment"
                                value={`${parseFloat(String(rawLine?.caf_percent || "0")) > 0 ? "+" : ""}${rawLine?.caf_percent}%`}
                                subValue="Adjustment to base rate"
                            />
                        )}
                        <TraceStep
                            label="Effective FX (Final)"
                            value={rawLine?.exchange_rate || "1.000000"}
                            highlight="success"
                        />
                    </>
                )}

                <TraceStep
                    label="Margin Applied"
                    value={`${displayPercent(line.margin_percent)}`}
                    subValue={`${displayMoney(line.margin_amount, "PGK")} ${parseFloat(line.margin_percent || "0") < 0 ? "(Loss)" : "(Healthy)"}`}
                    highlight={parseFloat(line.margin_percent || "0") < 0 ? "error" : "success"}
                />

                <TraceStep
                    label="Sell Ex-GST"
                    value={displayMoney(line.sell_pgk, "PGK")}
                />

                <TraceStep
                    label="GST Treatment"
                    value={isGstExempt ? "Exempt" : `${displayPercent(gstRate * 100)} Rate`}
                    subValue={!isGstExempt ? `Amount: ${displayMoney(line.gst_amount, "PGK")}` : "No tax applied"}
                    highlight={!isGstExempt ? "success" : undefined}
                />

                <TraceStep
                    label="Final Sell (Inc-GST)"
                    value={displayMoney(line.sell_pgk_incl_gst, "PGK")}
                    highlight="success"
                    isBold
                />
            </div>

            {rawLine?.calculation_notes && (
                <div className="pt-3 border-t border-slate-100">
                    <div className="text-[9px] font-bold text-slate-400 uppercase tracking-widest mb-1.5 flex items-center gap-1.5">
                        <Database className="h-3 w-3" />
                        System Trace (Debug)
                    </div>
                    <div className="text-[10px] text-slate-500 font-mono leading-relaxed bg-slate-50/50 p-2.5 rounded border border-slate-200/50 overflow-x-auto whitespace-pre-wrap">
                        {rawLine.calculation_notes}
                    </div>
                </div>
            )}
        </div>
    );
}

function TraceStep({
    label,
    value,
    subValue,
    highlight,
    isBold
}: {
    label: string;
    value: string;
    subValue?: string;
    highlight?: "success" | "error";
    isBold?: boolean;
}) {
    let textClass = "text-slate-800";
    if (highlight === "success") textClass = "text-emerald-700";
    if (highlight === "error") textClass = "text-rose-700";

    return (
        <div className="flex flex-col gap-0.5">
            <div className="text-[9px] font-bold uppercase tracking-wider text-slate-400">{label}</div>
            <div className={`text-xs ${isBold ? "font-bold" : "font-semibold"} ${textClass}`}>{value}</div>
            {subValue && <div className="text-[10px] text-slate-500 font-medium">{subValue}</div>}
        </div>
    );
}