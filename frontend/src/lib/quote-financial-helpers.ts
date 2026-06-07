import {
    CanonicalQuoteLineItem,
    CanonicalQuoteResult,
    QuoteComputeResult,
    SellLine,
    V3QuoteLine,
    V3QuoteComputeResponse,
} from "./types";

export type LooseRecord = Record<string, unknown>;

export type RawQuoteLine = V3QuoteLine & Partial<SellLine> & {
    margin_amount?: string | null;
};

export type BreakdownLine = SellLine & { 
    sell_fcy_currency?: string;
    canonical_item?: CanonicalQuoteLineItem;
    raw_line?: RawQuoteLine;
    subcategory?: string;
    margin_amount?: string | null;
};

export type BreakdownDataShape = {
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

export type BucketType = 'ORIGIN' | 'FREIGHT' | 'DESTINATION';

export type WarningDetails = { text: string; level: 'critical' | 'info' };

export const SUBCATEGORY_ORDER = [
    "Customs / Regulatory",
    "Documentation",
    "Local Transport / Cartage",
    "Handling / Terminal",
    "Freight / Carrier",
    "Carrier Surcharges",
    "Service / Agency Fees",
    "Other Charges",
];

export function toMoneyString(value: number): string {
    return value.toFixed(2);
}

export function mapCanonicalComponentToLeg(component: string): SellLine["leg"] {
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

export function mapCanonicalLineItemToBreakdownLine(
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
        margin_percent: item.margin_percent,
        exchange_rate: item.rate || "0",
        subcategory: item.subcategory,
        source: item.cost_source,
        is_informational: !item.included_in_total,
        margin_amount: item.margin_amount,
        canonical_item: item,
        raw_line: rawLine,
    };
}

export function buildCanonicalTotals(result: CanonicalQuoteResult): LooseRecord {
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

export const formatAmount = (amountStr: string | number | undefined, currency: string) => {
    const amount = typeof amountStr === 'number' ? amountStr : parseFloat(amountStr || "0");
    const formatted = new Intl.NumberFormat("en-US", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    }).format(amount);
    return `${currency} ${formatted}`;
};

export function getBucket(line: SellLine): BucketType {
    if (line.leg === 'MAIN' || line.leg === 'FREIGHT') return 'FREIGHT';
    if (line.leg === 'ORIGIN') return 'ORIGIN';
    return 'DESTINATION';
}

export function calculateBucketTotal(lines: BreakdownLine[], field: string): number {
    return lines.reduce((sum, line) => {
        const rawValue = ((line as unknown) as Record<string, unknown>)[field];
        const value = parseFloat(String(rawValue ?? '0'));
        return sum + value;
    }, 0);
}

export function readField(obj: unknown, key: string): unknown {
    if (!obj || typeof obj !== "object") return undefined;
    return (obj as Record<string, unknown>)[key];
}

export function readStringField(obj: unknown, key: string): string | undefined {
    const value = readField(obj, key);
    return typeof value === "string" ? value : undefined;
}

export function getDisplaySellAmount(line: BreakdownLine, isShowingFCY: boolean): number {
    const rawValue = isShowingFCY
        ? (line.sell_fcy || line.sell_pgk)
        : (line.sell_pgk || line.sell_fcy);
    return parseFloat(String(rawValue || "0"));
}

export function isAvailable(value: unknown): boolean {
    return value !== null && value !== undefined && value !== "";
}

export function displayValue(value: unknown): string {
    return isAvailable(value) ? String(value) : "Not available";
}

export function displayApplicable(value: unknown, applicable: boolean): string {
    if (!applicable) return "Not applicable";
    return displayValue(value);
}

export function displayMoney(value: unknown, currency: string): string {
    if (!isAvailable(value)) return "Not available";
    return formatAmount(String(value), currency);
}

export function displayPercent(value: unknown): string {
    if (!isAvailable(value)) return "Not available";
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return String(value);
    return `${parsed.toFixed(2)}%`;
}

export function findRawLine(rawLines: RawQuoteLine[], canonicalLine: CanonicalQuoteLineItem): RawQuoteLine | undefined {
    if (canonicalLine.line_id) {
        const byId = rawLines.find((line) => line.id === canonicalLine.line_id);
        if (byId) return byId;
    }
    return rawLines.find((line) => {
        const code = line.product_code || line.component || line.service_component?.code;
        return code === canonicalLine.product_code && line.description === canonicalLine.description;
    });
}

export function lineWarnings(line: CanonicalQuoteLineItem, rawLine?: Partial<V3QuoteLine>): WarningDetails[] {
    const warnings: WarningDetails[] = [];
    if (rawLine?.is_rate_missing) warnings.push({ text: "Missing buy rate", level: 'critical' });
    if (line.is_manual_override || rawLine?.is_manual_override) warnings.push({ text: "Manual override", level: 'info' });
    if (line.rate_source === "FALLBACK_RULE") warnings.push({ text: "FX or rate fallback applied", level: 'info' });
    return warnings;
}

export function sourceLabel(line: CanonicalQuoteLineItem, rawLine?: Partial<V3QuoteLine>): string {
    if (line.is_spot_sourced || rawLine?.is_spot_sourced) return "SPOT";
    if (line.is_manual_override || rawLine?.is_manual_override) return "Manual entry";
    if (line.rate_source === "MANUAL_OVERRIDE") return "Manual entry";
    if (line.rate_source === "PARTNER_SPOT") return "SPOT";
    if (line.rate_source === "DB_TARIFF") return "V4 rate card";
    if (line.rate_source === "FALLBACK_RULE") return "Fallback rule";
    return displayValue(line.rate_source);
}
