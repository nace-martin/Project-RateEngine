// frontend/src/lib/spot-types.ts
/**
 * SPOT Mode TypeScript Types
 * 
 * Matches backend Pydantic schemas in quotes/spot_schemas.py
 */

// =============================================================================
// ENUMS
// =============================================================================

/** SPE lifecycle status */
export type SPEStatus = 'draft' | 'ready' | 'expired' | 'rejected';

/** SPOT Mode UI flow states (state machine) */
export type SpotFlowState =
    | 'NORMAL'           // Not SPOT, use normal quote flow
    | 'OUT_OF_SCOPE'     // Hard reject (non-PNG lane)
    | 'SPOT_REQUIRED'    // Banner displayed, starting SPE
    | 'RATE_ENTRY'       // Entering charges
    | 'AWAITING_ACK'     // Acknowledgement modal
    | 'AWAITING_MANAGER' // Manager approval pending
    | 'READY'            // Can call pricing
    | 'EXPIRED'          // SPE expired
    | 'REJECTED';        // Manager rejected

/** Charge buckets */
export type SPEChargeBucket = 'airfreight' | 'origin_charges' | 'destination_charges';

/** Charge units */
export type SPEChargeUnit = 'per_kg' | 'flat' | 'per_awb' | 'per_shipment' | 'min_or_per_kg' | 'percentage';

/** Commodity types */
export type SPECommodity =
    | 'GCR'   // General Cargo
    | 'SCR'   // Special Cargo
    | 'DG'    // Dangerous Goods
    | 'AVI'   // Live Animals
    | 'PER'   // Perishables
    | 'HVC'   // High Value Cargo
    | 'HUM'   // Human Remains
    | 'OOG'   // Oversized/Heavy
    | 'VUL'   // Vulnerable Cargo
    | 'TTS'   // Time/Temp Sensitive
    | 'OTHER';

// =============================================================================
// API REQUEST/RESPONSE TYPES
// =============================================================================

/** Scope validation request */
export interface ScopeValidateRequest {
    origin_country: string;
    destination_country: string;
}

/** Scope validation response */
export interface ScopeValidateResponse {
    is_valid: boolean;
    error: string | null;
}

/** Trigger evaluation request */
export interface TriggerEvaluateRequest {
    origin_country: string;
    destination_country: string;
    commodity: SPECommodity;
    origin_airport?: string;
    destination_airport?: string;
    has_valid_buy_rate?: boolean;
    has_valid_cogs?: boolean;
    has_valid_sell?: boolean;
    is_multi_leg?: boolean;
    service_scope?: string;
}

/** Trigger result from backend */
export interface TriggerResult {
    code: string;
    text: string;
    missing_components?: string[];
}

/** Trigger evaluation response */
export interface TriggerEvaluateResponse {
    is_spot_required: boolean;
    trigger: TriggerResult | null;
}

// =============================================================================
// SPE DATA TYPES
// =============================================================================

/** SPE shipment context (immutable after creation) */
export interface SPEShipmentContext {
    origin_country: string;
    destination_country: string;
    origin_code: string;
    destination_code: string;
    commodity: SPECommodity;
    total_weight_kg: number;
    pieces: number;
    service_scope?: string;
}

/** SPE charge line */
export interface SPEChargeLine {
    id?: string;
    code: string;
    description: string;
    amount: string;
    currency: 'SGD' | 'USD' | 'AUD' | 'PGK' | 'NZD' | 'HKD';
    unit: SPEChargeUnit;
    bucket: SPEChargeBucket;
    is_primary_cost: boolean;
    conditional: boolean;
    source_reference: string;

    // Extended fields
    min_charge?: string | number;
    note?: string;
    exclude_from_totals?: boolean;
    percentage_basis?: string;
}

/** SPE conditions */
export interface SPEConditions {
    space_not_confirmed: boolean;
    airline_acceptance_not_confirmed: boolean;
    rate_validity_hours: number;
    conditional_charges_present: boolean;
    notes?: string;
}

/** SPE acknowledgement */
export interface SPEAcknowledgement {
    acknowledged_by_user_id: string;
    acknowledged_at: string;
    statement: string;
}

/** SPE manager approval */
export interface SPEManagerApproval {
    approved: boolean;
    manager_user_id: string;
    decision_at: string;
    comment?: string;
}

/** Create SPE request */
export interface CreateSPERequest {
    shipment_context: SPEShipmentContext;
    charges: Omit<SPEChargeLine, 'id'>[];
    conditions?: Partial<SPEConditions>;
    trigger_code: string;
    trigger_text: string;
    validity_hours?: number;
}

/** Full SPE response from API */
export interface SpotPricingEnvelope {
    id: string;
    status: SPEStatus;
    shipment: SPEShipmentContext;
    shipment_context_hash?: string;
    conditions: SPEConditions;
    spot_trigger_reason_code: string;
    spot_trigger_reason_text: string;
    created_at: string;
    expires_at: string;
    is_expired: boolean;
    context_integrity_valid?: boolean;
    acknowledgement: SPEAcknowledgement | null;
    manager_approval: SPEManagerApproval | null;
    requires_manager_approval: boolean;
    charges: SPEChargeLine[];
}

/** SPE compute request */
export interface SPEComputeRequest {
    quote_request: {
        payment_term?: string;
        service_scope?: string;
        output_currency?: string;
    };
}

/** SPE compute result line */
export interface SPEComputeResultLine {
    code: string;
    description: string;
    cost_pgk: string;
    sell_pgk: string;
    sell_pgk_incl_gst: string;
    leg: string;
    source: string;
    is_informational?: boolean;
    bucket: string;
}

/** SPE compute response */
export interface SPEComputeResponse {
    is_complete: boolean;
    reason?: string;
    pricing_mode?: 'SPOT' | 'NORMAL';
    spe_id?: string;
    lines?: SPEComputeResultLine[];
    totals?: {
        total_cost_pgk: string;
        total_sell_pgk: string;
        total_sell_pgk_incl_gst: string;
    };
}

// =============================================================================
// REPLY ANALYSIS TYPES (Phase 1)
// =============================================================================

/** Classification of certainty for extracted assertions */
export type AssertionStatus = 'confirmed' | 'conditional' | 'implicit' | 'missing';

/** Categories of information we expect in agent replies */
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

/** Single claim extracted from agent reply */
export interface ExtractedAssertion {
    text: string;
    category: AssertionCategory;
    value?: string | null;
    status: AssertionStatus;
    confidence: number;
    source_line?: number | null;

    // Parsed values
    rate_amount?: string | null;
    rate_per_unit?: string | null;  // Per-unit rate for MIN_OR_PER_KG
    rate_currency?: string | null;
    rate_unit?: string | null;
    validity_date?: string | null;
}

/** Quick status check of analysis results */
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
}

/** Full analysis of an agent reply */
export interface ReplyAnalysisResult {
    raw_text: string;
    assertions: ExtractedAssertion[];
    summary: AnalysisSummary;
    warnings: string[];
    can_proceed: boolean;
    blocked_reason: string | null;
}

/** Input for manually adding an assertion */
export interface ManualAssertionInput {
    text: string;
    category: AssertionCategory;
    status: AssertionStatus;
    value?: string;
    rate_amount?: string;
    rate_currency?: string;
    rate_unit?: string;
    validity_date?: string;
}

// =============================================================================
// UI CONSTANTS
// =============================================================================

export const STATUS_LABELS: Record<AssertionStatus, string> = {
    confirmed: 'Confirmed',
    conditional: 'Conditional',
    implicit: 'Implicit',
    missing: 'Missing',
};

export const STATUS_COLORS: Record<AssertionStatus, string> = {
    confirmed: 'bg-green-50 border-green-200 text-green-700',
    conditional: 'bg-amber-50 border-amber-200 text-amber-700',
    implicit: 'bg-orange-50 border-orange-200 text-orange-700',
    missing: 'bg-red-50 border-red-200 text-red-700',
};

export const CATEGORY_LABELS: Record<AssertionCategory, string> = {
    rate: 'Air Freight Rate',
    currency: 'Currency',
    validity: 'Validity/Expiry',
    routing: 'Routing',
    acceptance: 'Acceptance/Subject To',
    origin_charges: 'Origin Charges',
    dest_charges: 'Destination Charges',
    conditions: 'Special Conditions',
    transit_time: 'Transit Time',
};

export const MANDATORY_CATEGORIES: AssertionCategory[] = ['rate', 'currency'];

// =============================================================================
// STATE MACHINE TYPES
// =============================================================================

/** SPOT mode hook state */
export interface SpotModeState {
    flowState: SpotFlowState;
    spe: SpotPricingEnvelope | null;
    triggerResult: TriggerResult | null;
    error: string | null;
    isLoading: boolean;
    quoteResult: SPEComputeResponse | null;
}

/** SPOT mode hook actions */
export interface SpotModeActions {
    checkScope: (origin: string, destination: string) => Promise<boolean>;
    evaluateTrigger: (request: TriggerEvaluateRequest) => Promise<boolean>;
    createSPE: (request: CreateSPERequest) => Promise<SpotPricingEnvelope | null>;
    loadSPE: (id: string) => Promise<SpotPricingEnvelope | null>;
    submitAcknowledgement: () => Promise<boolean>;
    submitManagerApproval: (approved: boolean, comment?: string) => Promise<boolean>;
    computeSpotQuote: (request: SPEComputeRequest) => Promise<SPEComputeResponse | null>;
    reset: () => void;
}
