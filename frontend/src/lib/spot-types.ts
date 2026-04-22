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

/** SPOT Mode UI flow states (state machine) - simplified 3-step flow */
export type SpotFlowState =
    | 'NORMAL'           // Not SPOT, use normal quote flow
    | 'OUT_OF_SCOPE'     // Hard reject (non-PNG lane)
    | 'SPOT_REQUIRED'    // Banner displayed, starting SPE
    | 'INTAKE'           // Step 1: Paste reply, AI analysis
    | 'REVIEW'           // Step 2: Review assertions, fill missing, acknowledge
    | 'GENERATE'         // Step 3: Finalize quote, generate PDF
    | 'READY'            // Can call pricing
    | 'EXPIRED';         // SPE expired

/** Charge buckets */
export type SPEChargeBucket = 'airfreight' | 'origin_charges' | 'destination_charges';

/** Charge units */
export type SPEChargeUnit = 'per_kg' | 'flat' | 'per_awb' | 'per_shipment' | 'min_or_per_kg' | 'percentage' | 'per_trip' | 'per_set' | 'per_man';

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

export const SPOT_SUPPORTED_CURRENCIES = [
    'USD', 'AUD', 'PGK', 'SGD', 'NZD', 'FJD', 'SBD', 'VUV',
    'EUR', 'GBP', 'HKD', 'JPY', 'CNY', 'PHP', 'IDR', 'MYR',
    'THB', 'INR',
] as const;

export type SpotCurrency = typeof SPOT_SUPPORTED_CURRENCIES[number];

export type ChargeNormalizationStatus = 'MATCHED' | 'UNMAPPED' | 'AMBIGUOUS';

export interface SPEProductCodeSummary {
    id: number;
    code: string;
    description: string;
}

// =============================================================================
// API REQUEST/RESPONSE TYPES
// =============================================================================

/** Scope validation request */
export interface ScopeValidateRequest {
    origin_country: string;
    destination_country: string;
    origin_code?: string;
    destination_code?: string;
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
    payment_term: 'PREPAID' | 'COLLECT';
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
    missing_product_codes?: string[];
    spot_required_product_codes?: string[];
    manual_required_product_codes?: string[];
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
    customer_name?: string;
    commodity: SPECommodity;
    total_weight_kg: number;
    pieces: number;
    volume_cbm?: number;
    service_scope?: string;
    payment_term?: 'prepaid' | 'collect';
    missing_components?: string[];
}

/** SPE charge line */
export interface SPEChargeLine {
    id?: string;
    source_batch_id?: string | null;
    source_batch_label?: string | null;
    code: string;
    description: string;
    amount: string;
    currency: SpotCurrency;
    unit: SPEChargeUnit;
    bucket: SPEChargeBucket;
    is_primary_cost?: boolean;
    conditional?: boolean;
    source_reference: string;

    // Extended fields
    min_charge?: string | number;
    note?: string;
    exclude_from_totals?: boolean;
    percentage_basis?: string;
    source_label?: string;
    normalized_label?: string;
    normalization_status?: ChargeNormalizationStatus | null;
    normalization_method?: string | null;
    matched_alias_id?: number | null;
    resolved_product_code?: SPEProductCodeSummary | null;
    manual_resolution_status?: 'RESOLVED' | null;
    manual_resolved_product_code?: SPEProductCodeSummary | null;
    manual_resolution_by_user_id?: string | null;
    manual_resolution_by_username?: string | null;
    manual_resolution_at?: string | null;
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

/** SPE source batch */
export interface SPESourceBatch {
    id: string;
    source_kind: 'AIRLINE' | 'AGENT' | 'MANUAL' | 'OTHER';
    source_type: 'TEXT' | 'PDF' | 'EMAIL' | 'MANUAL';
    target_bucket: 'airfreight' | 'origin_charges' | 'destination_charges' | 'mixed';
    label: string;
    source_reference: string;
    file_name: string;
    file_content_type: string;
    analysis_summary_json: Record<string, unknown>;
    created_at: string;
    updated_at: string;
    charge_count: number;
    warnings: string[];
    assertion_count: number;
    ai_used: boolean;
    review_required: boolean;
    review_status: 'PENDING' | 'APPROVED' | 'NOT_REQUIRED';
    reviewed_safe_to_quote: boolean;
    reviewed_by_user_id: string | null;
    reviewed_at: string | null;
    review_note: string | null;
    detected_currencies: SpotCurrency[];
    risk_flags: string[];
    blocking_reasons: string[];
    risk_level: 'LOW' | 'MEDIUM' | 'HIGH';
    requires_review_note: boolean;
}

export interface SPEIntakeSafety {
    is_safe_to_quote: boolean;
    blocking_issues: string[];
    pending_source_batch_ids: string[];
    pending_source_labels: string[];
    review_note_required_batch_ids: string[];
}

/** Create SPE request */
export interface CreateSPERequest {
    shipment_context: SPEShipmentContext;
    charges: Omit<SPEChargeLine, 'id'>[];
    conditions?: Partial<SPEConditions>;
    trigger_code: string;
    trigger_text: string;
    quote_id?: string;
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
    updated_at?: string;
    expires_at: string;
    is_expired: boolean;
    context_integrity_valid?: boolean;
    acknowledgement: SPEAcknowledgement | null;
    missing_mandatory_fields: string[];  // 'rate', 'currency' if missing
    can_proceed: boolean;  // True if no missing mandatory fields
    intake_safety: SPEIntakeSafety;
    sources: SPESourceBatch[];
    charges: SPEChargeLine[];
    customer_name?: string; // from backend/quotes/spot_schemas.py
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
    has_missing_rates?: boolean;
    missing_components?: string[];
    completeness_notes?: string | null;
    pricing_mode?: 'SPOT' | 'NORMAL';
    spe_id?: string;
    fx_info?: {
        source_currency: string;
        target_currency: string;
        rate: string;
        as_of?: string;
    };
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
    percentage_basis?: string;
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
    mandatory_missing: string[];  // List of missing required field names
}

/** Full analysis of an agent reply */
export interface ReplyAnalysisResult {
    raw_text: string;
    assertions: ExtractedAssertion[];
    summary: AnalysisSummary;
    warnings: string[];
    safety_signals?: {
        raw_charge_count: number;
        normalized_charge_count: number;
        imported_charge_count: number;
        unmapped_line_count: number;
        low_confidence_line_count: number;
        conditional_charge_count: number;
        critic_safe_to_proceed?: boolean | null;
        critic_missed_charges: string[];
        critic_hallucinations: string[];
        pdf_fallback_used: boolean;
    };
    can_proceed: boolean;
    blocked_reason: string | null;
    source_batch_id?: string;
    source_batch_label?: string;
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
    percentage_basis?: string;
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
    updateSPE: (
        id: string,
        data: {
            charges?: Array<Omit<SPEChargeLine, 'id'> & { charge_line_id?: string }>;
            conditions?: Partial<SPEConditions>;
        }
    ) => Promise<SpotPricingEnvelope | null>;
    loadSPE: (id: string) => Promise<SpotPricingEnvelope | null>;
    manuallyResolveChargeLine: (
        chargeLineId: string,
        request: { product_code_id: number | string }
    ) => Promise<SPEChargeLine | null>;
    submitAcknowledgement: () => Promise<boolean>;
    reviewSourceBatch: (sourceBatchId: string, request: { reviewed_safe_to_quote: boolean; review_note?: string }) => Promise<SpotPricingEnvelope | null>;
    computeQuote: (request: SPEComputeRequest) => Promise<SPEComputeResponse | null>;
    createQuote: (request: { payment_term: string; service_scope: string; output_currency: string; customer_id?: string }) => Promise<{ success: boolean; quote_id: string } | null>;
    reset: () => void;
}
