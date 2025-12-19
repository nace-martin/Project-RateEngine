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
export type SPEChargeUnit = 'per_kg' | 'flat' | 'per_awb' | 'per_shipment' | 'percentage';

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
}

/** Trigger result from backend */
export interface TriggerResult {
    code: string;
    text: string;
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
}

/** SPE charge line */
export interface SPEChargeLine {
    id?: string;
    code: string;
    description: string;
    amount: string;
    currency: 'USD' | 'AUD' | 'PGK';
    unit: SPEChargeUnit;
    bucket: SPEChargeBucket;
    is_primary_cost: boolean;
    conditional: boolean;
    source_reference: string;
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
    shipment_context: SPEShipmentContext;
    shipment_context_hash?: string;
    conditions: SPEConditions;
    trigger_code: string;
    trigger_text: string;
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
// STATE MACHINE TYPES
// =============================================================================

/** SPOT mode hook state */
export interface SpotModeState {
    flowState: SpotFlowState;
    spe: SpotPricingEnvelope | null;
    triggerResult: TriggerResult | null;
    error: string | null;
    isLoading: boolean;
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
