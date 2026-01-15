import { V3QuoteComputeResponse } from "@/lib/types";

export interface UnifiedQuote {
    id: string;
    type: "STANDARD" | "SPOT_DRAFT";
    number: string;
    customer: string;
    route: string;
    date: string; // ISO string
    weight: string;
    status: string;
    total: string; // Formatted currency string or "-"
    actionLink: string;
    rawStatus: string; // For filtering
}

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
    const match = location.match(/^([A-Z]{3})\s*-\s*(.+)$/);
    if (match) {
        const [, code, fullName] = match;
        const cityName = fullName.replace(/\s+(Airport|Intl|International|Jacksons|Terminal|Apt).*$/i, '').trim();
        return `${cityName} (${code})`;
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
    try {
        const dims = quote.latest_version?.payload_json?.dimensions;
        if (dims && Array.isArray(dims)) {
            const total = dims.reduce((sum, d) => sum + (parseFloat(d.gross_weight_kg) || 0), 0);
            return `${total.toFixed(0)} kg`;
        }
    } catch (e) {
        // Fallback or ignore
    }
    return "-";
};

export const getCustomerName = (customer: string | { name?: string | null; company_name?: string | null } | undefined | null): string => {
    if (!customer) return "Unknown Customer";
    if (typeof customer === 'string') return customer;
    return customer.company_name || customer.name || "Unknown Customer";
};
