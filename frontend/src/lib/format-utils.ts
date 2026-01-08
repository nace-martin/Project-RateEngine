/**
 * Format Utilities
 * Shared formatting functions for display purposes
 */

/**
 * Transform location string from "CODE - Full Name" to "City (CODE)"
 * 
 * Examples:
 * - "SYD - Sydney Airport" → "Sydney (SYD)"
 * - "POM - Port Moresby Jacksons Intl" → "Port Moresby (POM)"
 * - "BNE - Brisbane Intl" → "Brisbane (BNE)"
 */
export function formatRouteDisplay(location: string): string {
    if (!location) return '';

    // Match pattern: "CODE - City Name [Optional Airport/Intl suffix]"
    const match = location.match(/^([A-Z]{3})\s*-\s*(.+)$/);
    if (match) {
        const [, code, fullName] = match;
        // Remove airport/terminal suffixes to get just the city name
        const cityName = fullName
            .replace(/\s+(Airport|Intl|International|Jacksons|Terminal|Apt).*$/i, '')
            .trim();
        return `${cityName} (${code})`;
    }

    // If no match, return as-is
    return location;
}

/**
 * Format transport mode for display
 * Converts mode codes to human-readable labels
 */
export function formatModeDisplay(mode: string): string {
    const modeMap: Record<string, string> = {
        'AIR': 'Air Freight',
        'SEA': 'Sea Freight',
        'INLAND': 'Inland Transport',
        'ROAD': 'Inland Transport',
        'air': 'Air Freight',
        'sea': 'Sea Freight',
        'inland': 'Inland Transport',
        'road': 'Inland Transport',
    };
    return modeMap[mode] || mode;
}

/**
 * Format currency with proper symbol and grouping
 */
export function formatCurrency(value: number | string, currency = 'PGK'): string {
    const numValue = typeof value === 'string' ? parseFloat(value) : value;
    if (isNaN(numValue)) return `${currency} 0`;

    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency,
        maximumFractionDigits: 0,
    }).format(numValue);
}

/**
 * Format status for text display (no badges/icons)
 */
export function formatStatusDisplay(status: string): string {
    const statusMap: Record<string, string> = {
        'draft': 'Draft',
        'finalized': 'Finalized',
        'sent': 'Sent',
        'approved': 'Approved',
        'cancelled': 'Cancelled',
        'DRAFT': 'Draft',
        'FINALIZED': 'Finalized',
        'SENT': 'Sent',
        'APPROVED': 'Approved',
        'CANCELLED': 'Cancelled',
    };
    return statusMap[status] || status;
}
