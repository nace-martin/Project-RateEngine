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

// =============================================================================
// AIRPORT → CITY MAPPING
// =============================================================================

export const AIRPORT_CITY_MAP: Record<string, { city: string; country: string }> = {
    // Papua New Guinea
    'POM': { city: 'Port Moresby', country: 'PG' },
    'LAE': { city: 'Lae', country: 'PG' },
    'RAB': { city: 'Rabaul', country: 'PG' },
    'GKA': { city: 'Goroka', country: 'PG' },
    'HGU': { city: 'Mount Hagen', country: 'PG' },
    'MXH': { city: 'Mendi', country: 'PG' },
    'WWK': { city: 'Wewak', country: 'PG' },

    // Asia Pacific
    'SIN': { city: 'Singapore', country: 'SG' },
    'HKG': { city: 'Hong Kong', country: 'HK' },
    'NRT': { city: 'Tokyo Narita', country: 'JP' },
    'HND': { city: 'Tokyo Haneda', country: 'JP' },
    'ICN': { city: 'Seoul', country: 'KR' },
    'PVG': { city: 'Shanghai', country: 'CN' },
    'PEK': { city: 'Beijing', country: 'CN' },
    'CAN': { city: 'Guangzhou', country: 'CN' },
    'BKK': { city: 'Bangkok', country: 'TH' },
    'KUL': { city: 'Kuala Lumpur', country: 'MY' },
    'CGK': { city: 'Jakarta', country: 'ID' },
    'MNL': { city: 'Manila', country: 'PH' },

    // Australia
    'SYD': { city: 'Sydney', country: 'AU' },
    'MEL': { city: 'Melbourne', country: 'AU' },
    'BNE': { city: 'Brisbane', country: 'AU' },
    'PER': { city: 'Perth', country: 'AU' },
    'ADL': { city: 'Adelaide', country: 'AU' },
    'CNS': { city: 'Cairns', country: 'AU' },

    // New Zealand
    'AKL': { city: 'Auckland', country: 'NZ' },
    'WLG': { city: 'Wellington', country: 'NZ' },
    'CHC': { city: 'Christchurch', country: 'NZ' },

    // Europe & Middle East
    'LHR': { city: 'London', country: 'GB' },
    'FRA': { city: 'Frankfurt', country: 'DE' },
    'AMS': { city: 'Amsterdam', country: 'NL' },
    'CDG': { city: 'Paris', country: 'FR' },
    'DXB': { city: 'Dubai', country: 'AE' },
    'DOH': { city: 'Doha', country: 'QA' },

    // North America
    'LAX': { city: 'Los Angeles', country: 'US' },
    'JFK': { city: 'New York', country: 'US' },
    'SFO': { city: 'San Francisco', country: 'US' },
    'ORD': { city: 'Chicago', country: 'US' },
    'YVR': { city: 'Vancouver', country: 'CA' },
    'YYZ': { city: 'Toronto', country: 'CA' },
};

/**
 * Get city name from airport code
 */
export function getCityFromCode(code: string): string {
    const entry = AIRPORT_CITY_MAP[code?.toUpperCase()];
    return entry?.city || code;
}

/**
 * Format route as "City → City" with codes as secondary
 */
export function formatRouteWithCities(fromCode: string, toCode: string): {
    primary: string;
    secondary: string
} {
    return {
        primary: `${getCityFromCode(fromCode)} → ${getCityFromCode(toCode)}`,
        secondary: `${fromCode} → ${toCode}`
    };
}

/**
 * Clean charge description - remove redundant prefixes
 */
export function cleanChargeDescription(description: string): string {
    if (!description) return '';
    return description
        .replace(/^Export\s+/i, '')
        .replace(/^Import\s+/i, '')
        .replace(/^Domestic\s+/i, '')
        .trim();
}

/**
 * Format weight consistently
 */
export function formatWeight(weight: number | string, unit: string = 'kg'): string {
    const numWeight = typeof weight === 'string' ? parseFloat(weight) : weight;
    if (isNaN(numWeight)) return `0.00 ${unit}`;
    return `${numWeight.toFixed(2)} ${unit}`;
}

/**
 * Format PGK currency consistently (always "PGK X,XXX.XX")
 */
export function formatPGK(amount: number | string): string {
    const numAmount = typeof amount === 'string' ? parseFloat(amount) : amount;
    if (isNaN(numAmount)) return 'PGK 0.00';
    return `PGK ${numAmount.toLocaleString('en-US', {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2
    })}`;
}

/**
 * Format rate per unit
 */
export function formatRatePerUnit(rate: number | string, unit: string = 'kg'): string {
    const numRate = typeof rate === 'string' ? parseFloat(rate) : rate;
    if (isNaN(numRate)) return `PGK 0.00/${unit}`;
    return `PGK ${numRate.toFixed(2)}/${unit}`;
}

