// frontend/src/lib/types.ts

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// --- AUTH TYPES ---
export interface LoginData {
  username: string;
  password: string;
}

export interface User {
  id?: number;
  username: string;
  role: string;
}

export interface QuoteCustomerRef {
  id: string;
  name?: string | null;
  company_name?: string | null;
  email?: string | null;
}

export interface QuoteContactRef {
  id: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
}

// --- PARTIES (COMPANY/CONTACT) TYPES ---
export interface Company {
  id: string; // UUID
  name: string;
  is_customer: boolean;
  is_agent: boolean;
  is_carrier: boolean;
}

export interface Contact {
  id: string; // UUID
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
}

export interface CompanySearchResult {
  id: string; // Company UUID
  name: string;
}

export interface AirportSearchResult {
  iata_code: string;
  name: string;
  city_country: string;
}

export interface LocationSearchResult {
  id: string;            // Backend identifier (IATA, UUID, etc.)
  code: string;          // Display-friendly code (IATA, port code, etc.)
  display_name: string;  // "Brisbane (BNE), AU"
  country_code?: string; // "AU", "PG", etc.
}



export interface StationSummary {
  id: number;
  iata_code: string;
  name?: string;
  city_country?: string;
}

export interface CustomerAddress {
  address_line_1: string;
  address_line_2?: string;
  city: string;
  state_province?: string;
  postcode?: string;
  country: string;
}

export interface Customer {
  id: string;
  company_name: string;
  audience_type: string;
  address_description?: string | null;
  primary_address?: CustomerAddress | null;
  contact_person_name?: string;
  contact_person_email?: string;
  contact_person_phone?: string;
}

// --- MISC HELPER TYPES ---
export type DecimalString = string & { __decimalStringBrand: never };

// --- V3 QUOTE REQUEST TYPES ---
export interface V3DimensionInput {
  pieces: number;
  length_cm: string;
  width_cm: string;
  height_cm: string;
  gross_weight_kg: string;
}

export interface V3ManualOverride {
  service_component_id: string;
  cost_fcy: string;
  currency: string;
  unit: string;
  min_charge_fcy?: string;
  valid_until?: string;
}

export interface V3QuoteComputeRequest {
  quote_id?: string;
  customer_id: string;
  contact_id: string;
  mode: string;
  incoterm: string;
  service_scope: 'D2D' | 'D2A' | 'A2D' | 'A2A';
  origin_location_id: string;
  destination_location_id: string;
  dimensions: V3DimensionInput[];
  payment_term: string;
  is_dangerous_goods?: boolean;
  overrides?: V3ManualOverride[];
  output_currency?: string;
  origin_airport?: string;
  destination_airport?: string;
  spot_rates?: Record<string, unknown>;
}


// --- V3 QUOTE RESPONSE TYPES ---
export interface V3ServiceComponent {
  id: string; // UUID
  code: string;
  description: string;
  category: string;
  unit: string;
  leg: string;
}

export interface V3QuoteLine {
  id: string; // UUID
  service_component: V3ServiceComponent;
  leg?: string;
  cost_pgk: string;
  cost_fcy?: string | null;
  cost_fcy_currency?: string | null;
  sell_pgk: string;
  sell_pgk_incl_gst: string;
  sell_fcy: string;
  sell_fcy_incl_gst: string;
  sell_fcy_currency?: string | null;
  exchange_rate?: string | null;
  cost_source?: string | null;
  cost_source_description?: string | null;
  is_rate_missing: boolean;
}

/**
 * V3 Quote Total Response
 * 
 * MUST MATCH: backend/quotes/response_schemas.py::QuoteTotalsResponse
 * 
 * The `currency` field is the OUTPUT CURRENCY for display.
 */
export interface V3QuoteTotal {
  // OUTPUT CURRENCY (e.g., AUD, USD, PGK) - CRITICAL FIELD
  currency: string;

  // Cost totals (Manager/Finance only)
  total_cost_pgk?: string;

  // Sell totals in PGK
  sell_pgk?: string;
  sell_pgk_incl_gst?: string;
  total_sell_pgk?: string;
  total_sell_pgk_incl_gst?: string;
  total_sell_ex_gst?: string;
  total_quote_amount?: string;
  total_gst?: string;
  gst_pgk?: string;

  // Sell totals in FCY
  sell_fcy?: string;
  sell_fcy_incl_gst?: string;
  total_sell_fcy: string;
  total_sell_fcy_incl_gst: string;
  total_sell_fcy_currency: string;

  // Status
  has_missing_rates: boolean;
  notes?: string | null;
}

export interface V3QuoteVersion {
  id: string; // UUID
  version_number: number;
  status: string;
  created_at: string; // ISO date string
  payload_json?: V3QuoteComputeRequest;
  lines: V3QuoteLine[];
  totals: V3QuoteTotal;
  total_weight_kg?: number; // Added via serializer
}

export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: string | QuoteCustomerRef;
  contact: string | QuoteContactRef;
  mode: string;
  shipment_type: string; // The backend calculates and returns this
  spot_negotiation?: { id: string } | null;
  incoterm: string;
  payment_term: string;
  service_scope: string;
  output_currency: string;

  origin_location: string;
  destination_location: string;

  status: string;
  is_archived?: boolean;
  valid_until: string; // Date string (YYYY-MM-DD)
  created_at: string; // ISO date string
  updated_at?: string; // ISO date string
  created_by?: string | null; // Assigned Agent (Sales Rep)
  rate_provider?: string | null; // Agent who provided rates
  latest_version: V3QuoteVersion;
}

export type QuoteVersionChargeInput = V3ManualOverride;

export interface QuoteVersionCreatePayload {
  charges: QuoteVersionChargeInput[];
}

// --- CHARGE ENGINE TYPES (STEP 2) ---

export interface BuyCharge {
  component: string; // component_code
  source: string;
  supplier_id?: string | null;
  currency: string;
  method: string;
  unit?: string | null;
  min_charge: string;
  flat_amount?: string | null;
  rate_per_unit?: string | null;
  percent_value?: string | null;
  percent_of_component?: string | null;
  description: string;
}

export interface SellLine {
  line_type: 'COMPONENT' | 'CAF' | 'SURCHARGE';
  component?: string | null; // component_code
  description: string;
  leg?: 'ORIGIN' | 'MAIN' | 'DESTINATION' | string; // Add leg for categorization
  cost_pgk: string;
  sell_pgk: string;
  sell_pgk_incl_gst?: string;
  gst_amount?: string;
  sell_fcy: string;
  sell_fcy_incl_gst?: string;
  sell_currency: string;
  margin_percent: string;
  exchange_rate: string;
  source: string;
  is_informational?: boolean; // If true, shown as note, not in totals
}

export interface QuoteComputeTotals {
  cost_pgk: string;
  sell_pgk: string;
  sell_pgk_incl_gst?: string;
  gst_amount?: string;
  caf_pgk: string;
  currency: string;
  // FCY Totals
  total_sell_fcy?: string;
  total_sell_fcy_incl_gst?: string;
  total_sell_fcy_currency?: string;
  cost_aud?: string; // Legacy support
  [key: string]: string | undefined; // For dynamic keys
}

export interface RoutingViolation {
  piece_number: number;
  dimension: string;
  actual: string;
  limit: string;
  message: string;
}

export interface RoutingInfo {
  service_level: string;
  routing_reason?: string;
  requires_via_routing: boolean;
  violations: RoutingViolation[];
}

export interface QuoteComputeResult {
  quote_id: string;
  quote_number: string;
  buy_lines: BuyCharge[];
  sell_lines: SellLine[];
  totals: QuoteComputeTotals;
  exchange_rates: Record<string, string>;
  computation_date: string;
  routing?: RoutingInfo;
  notes: string[];
}

export interface Tier1Stats {
  active_customers: number;
  repeat_customers_pct: number;
  top_customers: { name: string; value: number }[];
  dormant_customers: {
    '30d': number;
    '60d': number;
    '90d': number;
  };
}
