// --- AUTH TYPES ---

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

// --- PARTIES (COMPANY/CONTACT) TYPES ---

export interface Address {
  address_line_1: string;
  address_line_2?: string;
  city: string; // This comes from the City model
  country: string; // This comes from the Country model
  postal_code: string;
}

export interface Company {
  id: string; // UUID
  name: string;
  company_type: 'CUSTOMER' | 'SUPPLIER';
  tax_id: string;
  // These fields are from the old 'Customer' type, can be added if/when needed
  // primary_address: Address | null;
  // contacts: Contact[];
}

export interface Contact {
  id: string; // UUID
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  company: string; // Company UUID
}

export interface CompanySearchResult {
  id: string; // Company UUID
  name: string;
}

export interface RatecardFile {
  id: string; // This is a UUID
  name: string;
  supplier_name: string;
  currency_code: string;
  valid_from: string;
  valid_until: string;
  status: string;
  created_at: string; // ISO date string
}

// --- MISC HELPER TYPES ---

/**
 * Branded type for decimal strings (e.g., "12.34")
 */
export type DecimalString = string & { __decimalStringBrand: never };

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

// --- V3 QUOTE REQUEST TYPES ---
// These define the payload for POST /api/v3/quotes/compute/

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
}

export interface V3QuoteComputeRequest {
  customer_id: string;
  contact_id: string;
  mode: string;
  shipment_type: string;
  incoterm: string;
  origin_airport_code: string;
  destination_airport_code: string;
  dimensions: V3DimensionInput[];
  payment_term?: string;
  is_dangerous_goods?: boolean;
  overrides?: V3ManualOverride[];
  output_currency?: string;
}

// --- V3 QUOTE RESPONSE TYPES ---
// These define the response from GET /api/v3/quotes/:id
// and POST /api/v3/quotes/compute/

// Minimal type for the nested ServiceComponent
export interface V3ServiceComponent {
  id: string; // UUID
  code: string;
  description: string;
  category: string;
  unit: string;
}

export interface V3QuoteLine {
  id: string; // UUID
  service_component: V3ServiceComponent;
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

export interface V3QuoteTotal {
  total_sell_fcy: string;
  total_sell_fcy_incl_gst: string;
  total_sell_fcy_currency: string;
  has_missing_rates: boolean;
  notes?: string | null;
}

export interface V3QuoteVersion {
  id: string; // UUID
  version_number: number;
  status: string;
  created_at: string; // ISO date string
  lines: V3QuoteLine[];
  totals: V3QuoteTotal;
}

// This is the main type for the compute response
// and the GET /api/v3/quotes/:id response
export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: string; // Customer UUID
  contact: string; // Contact UUID
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