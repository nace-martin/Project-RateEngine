// This defines the structure of a single Client object
export interface LoginData {
  username: string;
  password: string;
}

export interface User {
  id: number;
  username: string;
  role: string;
}

export interface CustomerAddress {
  address_line_1: string;
  address_line_2?: string;
  city: string;
  state_province: string;
  postcode: string;
  country: string;
}

export interface Customer {
  id: number;
  company_name: string;
  audience_type: string;
  primary_address: CustomerAddress | null;
  contact_person_name: string;
  contact_person_email: string;
  contact_person_phone: string;
  created_at?: string;
  // Legacy fields kept optional for older screens still referencing them
  name?: string;
  email?: string;
  phone?: string;
  org_type?: string;
}

export interface Contact {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  company: string;
}

export interface CompanySearchResult {
  id: string;
  name: string;
}

export interface QuoteV2LineRequest {
  currency: string;
  amount: string;
  description: string;
}

export interface QuoteV2AgentLineRequest {
  amount: string;
  description: string;
}

export interface QuoteV2Request {
  scenario: string;
  chargeable_kg: string;
  bill_to_id: string;
  shipper_id: string;
  consignee_id: string;
  origin_code: string;
  destination_code: string;
  buy_lines: QuoteV2LineRequest[];
  agent_dest_lines_aud: QuoteV2AgentLineRequest[];
}

export interface QuoteV2Totals {
  grand_total_pgk?: number;
  [key: string]: unknown;
}

export interface QuoteV2Line {
  section?: string;
  description?: string;
  sell_amount_pgk?: number | string;
  [key: string]: unknown;
}

export interface QuoteV2Response {
  id: string | number;
  quote_number?: string;
  totals?: QuoteV2Totals;
  scenario?: string;
  status?: string;
  lines?: QuoteV2Line[];
  [key: string]: unknown;
}

export interface Quote {
  id: number;
  client: Customer; // The related client object
  origin: string;
  destination: string;
  mode: string;
  status?: QuoteStatus;
  actual_weight_kg: string;
  volume_cbm: string;
  chargeable_weight_kg: string;
  rate_used_per_kg: string;
  base_cost: string; // COGS data - only visible to Manager and Finance roles
  margin_pct: string;
  total_sell: string; // We'll use string for decimals for now
  created_at: string;
}

// Quote/compute status values returned by backend
export enum QuoteStatus {
  COMPLETE = 'COMPLETE',
  PENDING_RATE = 'PENDING_RATE',
}

// Minimal money shape used across API responses
export interface Money {
  amount: string;
  currency: string;
}

export interface QuoteTotals {
  sell_total: Money;
  buy_total?: Money;
  tax_total?: Money;
  margin_abs?: Money;
  // margin_pct uses currency '%'
  margin_pct?: Money;
}

// Response shape from POST /api/quote/compute
// Backend currently returns either top-level sell_total or totals.sell_total
export interface ComputeQuoteResponse {
  quote_id: number;
  status: QuoteStatus;
  manual_reasons?: string[];
  sell_total?: Money;
  totals?: QuoteTotals;
}

export interface QuoteLine {
  code: string;
  desc: string;
  qty: string;
  unit: string;
  unit_price: Money;
  amount: Money;
  is_buy: boolean;
  is_sell: boolean;
  manual_rate_required: boolean;
  meta?: Record<string, unknown>;
}

export interface QuoteDetail {
  id: number;
  status: QuoteStatus;
  totals: QuoteTotals;
  currency: string;
  snapshot?: Record<string, unknown>;
  buy_lines: QuoteLine[];
  sell_lines: QuoteLine[];
  manual_reasons?: string[];
}

export interface ShipmentPiece {
  /**
   * Quantity is expected to be an integer
   */
  quantity: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  /**
   * Weight in kg, as a decimal string (to match Quote)
   */
  weight_kg: DecimalString;
}

/**
 * Branded type for decimal strings (e.g., "12.34")
 */
export type DecimalString = string & { __decimalStringBrand: never };

export interface RatecardFile {
  id: number;
  name: string;
  file: string;
  file_type: 'CSV' | 'HTML';
  created_at: string;
  updated_at: string;
}

export interface Piece {
  weight_kg: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  count?: number;
}

export interface QuoteContext {
  customer_id?: number;
  origin_iata: string;
  dest_iata: string;
  pieces: Piece[];
}

export interface QuoteVersion {
  id: number;
  quote: number;
  version_number?: number;
  origin?: number;
  destination?: number;
  pieces: Piece[];
  charges: {
    stage: string;
    code: string;
    description: string;
    basis: string;
    qty: number;
    unit_price: number;
    side: string;
    currency: string;
  }[];
  created_at?: string;
}

// This should mirror the BuyOffer dataclass from the backend
export interface BuyOffer {
  lane: {
    origin: string;
    dest: string;
  };
  ccy: string;
  breaks: {
    from_kg: number;
    rate_per_kg: number;
    total?: number;
  }[];
  fees: {
    code: string;
    rate: number;
  }[];
  // ... any other fields you expect from the backend
}

// --- V3 QUOTE REQUEST TYPES ---
export interface V3DimensionInput {
  pieces: number;
  length_cm: number;
  width_cm: number;
  height_cm: number;
  gross_weight_kg: number;
}

export interface V3ManualOverride {
  service_component_id: number;
  cost_fcy: number;
  currency: string;
  unit: string;
  min_charge_fcy?: number;
}

export interface V3QuoteComputeRequest {
  customer_id: string;
  contact_id: string;
  mode: string;
  shipment_type: string;
  incoterm: string;
  payment_term: string;
  origin_airport_code: string;
  destination_airport_code: string;
  dimensions: V3DimensionInput[];
  is_dangerous_goods: boolean;
  overrides?: V3ManualOverride[];
  output_currency?: string;
}

// --- ADD V3 QUOTE RESPONSE TYPES ---
// These should match the V3QuoteComputeResponseSerializer structure

interface V3QuoteLine {
  id: string;
  service_component: {
    id: number;
    name: string;
    category: string;
    unit: string;
  };
  cost_pgk: string; // Decimals come as strings
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

interface V3QuoteTotal {
  total_sell_fcy: string;
  total_sell_fcy_incl_gst: string;
  total_sell_fcy_currency: string;
  has_missing_rates: boolean;
  notes?: string | null;
}

interface V3QuoteVersion {
  id: string;
  version_number: number;
  status: string;
  created_at: string; // ISO date string
  lines: V3QuoteLine[];
  totals: V3QuoteTotal;
}

// This is the main type for the compute response
export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: number; // Customer ID
  contact: number; // Contact ID
  mode: string;
  shipment_type: string;
  incoterm: string;
  payment_term: string;
  output_currency: string;
  origin_code: string;
  destination_code: string;
  status: string;
  valid_until: string; // Date string (YYYY-MM-DD)
  created_at: string; // ISO date string
  latest_version: V3QuoteVersion;
}
// --- END ADD ---
