// frontend/src/lib/reply-analysis-types.ts
/**
 * Reply Analysis Types
 * 
 * TypeScript definitions for agent reply analysis and assertion classification.
 */

export type AssertionStatus = 'confirmed' | 'conditional' | 'implicit' | 'missing';

export type AssertionCategory =
    | 'rate'
    | 'currency'
    | 'validity'
    | 'routing'
    | 'acceptance'
    | 'origin_charges'
    | 'dest_charges'
    | 'conditions'
    | 'transit_time';

// Fields that MUST be present to proceed
export const MANDATORY_CATEGORIES: AssertionCategory[] = ['rate', 'currency'];

// Fields that are nice to have
export const OPTIONAL_CATEGORIES: AssertionCategory[] = [
    'routing',
    'acceptance',
    'origin_charges',
    'dest_charges',
    'conditions',
    'transit_time',
];

export interface ExtractedAssertion {
    id: string; // Client-side ID for React keys
    text: string;
    category: AssertionCategory;
    value?: string;
    status: AssertionStatus;
    confidence: number;
    source_line?: number;
    rate_amount?: string;
    rate_currency?: string;
    rate_unit?: string;
    validity_date?: string;
}

export interface AnalysisSummary {
    confirmed_count: number;
    conditional_count: number;
    implicit_count: number;
    missing_count: number;
    has_rate: boolean;
    has_currency: boolean;
    has_validity: boolean;
    has_routing: boolean;
    has_acceptance: boolean;
    can_proceed: boolean;
    mandatory_missing: string[];
    requires_acknowledgement: boolean;
}

export interface ReplyAnalysisResult {
    raw_text: string;
    assertions: ExtractedAssertion[];
    summary: AnalysisSummary;
    warnings: string[];
    can_proceed: boolean;
    blocked_reason?: string;
}

// Status display helpers
export const STATUS_LABELS: Record<AssertionStatus, string> = {
    confirmed: 'Confirmed',
    conditional: 'Conditional',
    implicit: 'Implicit',
    missing: 'Missing',
};

export const STATUS_COLORS: Record<AssertionStatus, string> = {
    confirmed: 'bg-green-100 text-green-800 border-green-300',
    conditional: 'bg-amber-100 text-amber-800 border-amber-300',
    implicit: 'bg-orange-100 text-orange-800 border-orange-300',
    missing: 'bg-red-100 text-red-800 border-red-300',
};

export const CATEGORY_LABELS: Record<AssertionCategory, string> = {
    rate: 'Airfreight Rate',
    currency: 'Currency',
    validity: 'Validity',
    routing: 'Routing',
    acceptance: 'Acceptance',
    origin_charges: 'Origin Charges',
    dest_charges: 'Dest. Charges',
    conditions: 'Conditions',
    transit_time: 'Transit Time',
};
