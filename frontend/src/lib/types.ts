// frontend/src/lib/types.ts

// --- AUTH TYPES ---
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
export interface Company {
  id: string; // UUID
  name: string;
  company_type: 'CUSTOMER' | 'SUPPLIER';
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
}

// --- THIS IS THE UPDATED INTERFACE ---
export interface V3QuoteComputeRequest {
  customer_id: string;
  contact_id: string;
  mode: string;
  incoterm: string;
  
  // These fields are new
  origin_airport: string;       // e.g., "BNE"
  destination_airport: string;  // e.g., "POM"
  // TODO: Add port fields when sea is ready
  
  // These fields were removed:
  // shipment_type: string;
  // origin_airport_code: string;
  // destination_airport_code: string;

  dimensions: V3DimensionInput[];
  payment_term?: string;
  is_dangerous_goods?: boolean;
  overrides?: V3ManualOverride[];
  output_currency?: string;
}
// --- END UPDATE ---


// --- V3 QUOTE RESPONSE TYPES ---
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

export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: string; // Customer UUID
  contact: string; // Contact UUID
  mode: string;
  shipment_type: string; // The backend calculates and returns this
  incoterm: string;
  payment_term: string;
  output_currency: string;
  
  // The backend now returns the validated objects
  origin_airport: string; // "BNE"
  destination_airport: string; // "POM"
  // TODO: Add port fields
  
  status: string;
  valid_until: string; // Date string (YYYY-MM-DD)
  created_at: string; // ISO date string
  latest_version: V3QuoteVersion;
}