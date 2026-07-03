// frontend/src/lib/draft-quote-types.ts

export interface Evidence {
    source_text: string;
    page: number | null;
    section: string | null;
    row_index: number | null;
    table_index: number | null;
    document_reference: string | null;
    bounding_box: number[] | null; // [x_min, y_min, x_max, y_max]
    extraction_note: string | null;
}

export type DraftChargeStatus = 'suggested' | 'needs_review' | 'unclassified' | 'ignored' | 'accepted_by_user' | 'pending_product_code';

export interface DraftCharge {
    id: string;
    status: DraftChargeStatus;
    display_label: string;
    raw_label: string;
    suggested_product_code: string | null;
    product_code_conflict: boolean;
    approved_product_code?: string | null;
    approved_product_code_id?: number | null;
    product_code_request_id?: number | null;
    bucket: string; // airfreight, origin_charges, destination_charges, unclassified
    currency: string;
    amount: number;
    rate: number | null;
    unit: string | null;
    calculation_basis: string | null;
    minimum_charge: number | null;
    percentage_base: string | null;
    quantity: number | null;
    include_in_totals: boolean;
    conditions: string[];
    warnings: string[];
    review_reason: string | null;
    evidence: Evidence | null;
    similarity_group_id: string | null;
    correction_actions: string[];
}

export interface CommercialTerm {
    type: string; // validity, density_ratio, carrier_acceptance, exclusion
    text: string;
    normalized_value: unknown;
    status: string;
    evidence: Evidence | null;
    review_reason: string | null;
}

export interface UnclassifiedItem {
    id: string;
    raw_text: string;
    evidence: Evidence | null;
    review_reason: string;
}

export interface IgnoredItem {
    id: string;
    raw_text: string;
    ignored_reason: string;
    evidence: Evidence | null;
}

export interface TotalsValidation {
    math_balances: boolean;
    currency_consistent: boolean;
    extracted_total: number | null;
    calculated_total: number | null;
    difference: number | null;
    tolerance: number;
    warnings: string[];
}

export interface DraftQuote {
    contract_version: string;
    quote_summary: string;
    shipment_context: {
        origin: string;
        destination: string;
        mode: string;
        pieces: number;
        actual_weight_kg: number;
        volumetric_weight_kg: number;
        chargeable_weight_kg: number;
        commodity: string;
        [key: string]: unknown;
    };
    supplier_context: {
        supplier_name: string;
        agent_code: string;
        [key: string]: unknown;
    };
    freight: {
        carrier: string;
        service_type: string;
        [key: string]: unknown;
    };
    suggested_charges: DraftCharge[];
    commercial_terms: CommercialTerm[];
    warnings: string[];
    unclassified_items: UnclassifiedItem[];
    ignored_items: IgnoredItem[];
    totals_validation: TotalsValidation;
    review_queue: Array<{
        id: string;
        type: string;
        message: string;
        [key: string]: unknown;
    }>;
    correction_actions: Array<{
        charge_id?: string;
        item_id?: string;
        action_type: string;
        options: string[];
        [key: string]: unknown;
    }>;
    metadata: {
        sender_domain?: string;
        historical_override_rules?: Record<string, unknown>;
        [key: string]: unknown;
    };
}

export interface AuditMetadata {
    user_id: number;
    timestamp: string;
}

export interface DecisionItem {
    decision_id: string;
    type: string;
    target_id: string;
    details: Record<string, unknown>;
    audit_metadata: AuditMetadata;
}

export interface DraftQuoteResolvePayload {
    idempotency_key: string;
    decisions: DecisionItem[];
}

export interface DecisionResult {
    decision_id: string;
    target_id: string;
    type: string;
    status: 'applied' | 'rejected' | 'skipped';
    message: string;
    error_code?: string | null;
}

export interface DraftQuoteResolveResponse {
    envelope_id: string;
    status: 'accepted' | 'partially_accepted' | 'rejected';
    message: string;
    applied_decisions: DecisionResult[];
    rejected_decisions: DecisionResult[];
}
