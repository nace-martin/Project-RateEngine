import { V3QuoteComputeResponse } from "@/lib/types";
import { SpotPricingEnvelope } from "./spot-types";

// ... (UnifiedQuote interface)

export const calculateSpotTotal = (draft: SpotPricingEnvelope): string => {
    if (!draft.charges || draft.charges.length === 0) return "-";

    const charges = draft.charges;
    // Check if all charges are in the same currency
    const currency = charges[0].currency;
    const allSameCurrency = charges.every(c => c.currency === currency);

    if (!allSameCurrency) {
        return "Mixed";
    }

    let total = 0;
    const weight = draft.shipment.total_weight_kg || 0;

    for (const c of charges) {
        let lineTotal = 0;
        // Handle potential string numbers with commas
        const amountStr = String(c.amount).replace(/,/g, '');
        const rate = parseFloat(amountStr) || 0;
        const minChargeStr = String(c.min_charge ?? 0).replace(/,/g, '');
        const minCharge = parseFloat(minChargeStr) || 0;

        switch (c.unit) {
            case 'per_kg':
            case 'min_or_per_kg': // Simplified for list view
                lineTotal = Math.max(rate * weight, minCharge);
                break;
            case 'flat':
            case 'per_shipment':
            case 'per_awb':
            case 'per_trip':
            case 'per_set':
            case 'per_man':
                lineTotal = rate;
                break;
            case 'percentage':
                // Percentage is complex to sum without context (e.g. % of what?)
                // For dashboard, we might skip or assume 0, or if it's a known basis?
                // Let's assume 0 for now to avoid incorrect large numbers
                lineTotal = 0;
                break;
            default:
                lineTotal = 0;
        }
        total += lineTotal;
    }

    // If total is 0, show 0.00 instead of -
    if (total === 0 && charges.length > 0) return formatCurrency("0", currency);

    return formatCurrency(total.toString(), currency);
};


export interface UnifiedQuote {
    id: string;
    type: "STANDARD" | "SPOT_DRAFT";
    number: string;
    customer: string;
    route: string;
    date: string; // ISO string
    updatedAt?: string;
    expiry?: string | null; // ISO string
    weight: string;
    status: string;
    total: string; // Formatted currency string or "-"
    actionLink: string;
    rawStatus: string; // For filtering
    mode: string;
    serviceType?: string;
    incoterms?: string;
    scope?: string;
    createdBy?: string;
}

export const getEffectiveQuoteStatus = (status: string, validUntil?: string | null): string => {
    const normalized = status?.toUpperCase?.() ?? "";
    if (normalized !== "SENT" || !validUntil) {
        return normalized || status;
    }
    const expiry = new Date(`${validUntil}T23:59:59`);
    if (Number.isNaN(expiry.getTime())) {
        return normalized;
    }
    return expiry.getTime() < Date.now() ? "EXPIRED" : normalized;
};

export const formatCurrency = (amountStr: string | undefined, currency: string | undefined) => {
    if (!amountStr || !currency) return "-";
    const amount = parseFloat(amountStr);
    return new Intl.NumberFormat("en-AU", {
        style: "currency",
        currency: currency,
    }).format(amount);
};

export const formatRoute = (location: string): string => {
    if (!location) return '';

    // Handle "CODE - Name" format from backend standard quotes
    const match = location.match(/^([A-Z]{3})\s*-\s*(.+)$/);
    if (match) {
        // Return JUST the code as requested by user ("IATA codes instead of City names")
        return match[1];
    }

    // Handle raw codes (e.g. "POM") - if it's already a code, just return it
    if (location.length === 3 && /^[A-Z]{3}$/.test(location)) {
        return location;
    }

    return location;
};

export const formatDate = (dateStr: string): string => {
    try {
        return new Date(dateStr).toLocaleDateString('en-AU', {
            day: 'numeric',
            month: 'short',
            year: 'numeric',
        });
    } catch {
        return dateStr;
    }
};

export const getWeight = (quote: V3QuoteComputeResponse): string => {
    // 1. Check for backend computed weight (added to serializer)
    if (quote.latest_version?.total_weight_kg !== undefined && quote.latest_version?.total_weight_kg !== null) {
        if (quote.latest_version.total_weight_kg > 0) {
            return `${quote.latest_version.total_weight_kg} kg`;
        }
    }

    // 2. Fallback to calculating from payload if present (detailed view)
    try {
        const dims = quote.latest_version?.payload_json?.dimensions;
        if (dims && Array.isArray(dims)) {
            const total = dims.reduce((sum, d) => sum + (parseFloat(d.gross_weight_kg) || 0), 0);
            return `${total.toFixed(0)} kg`;
        }
    } catch {
        // Fallback or ignore
    }
    return "-";
};

export const getCustomerName = (customer: string | { name?: string | null; company_name?: string | null } | undefined | null): string => {
    if (!customer) return "Unknown Customer";
    if (typeof customer === 'string') return customer;
    return customer.company_name || customer.name || "Unknown Customer";
};
