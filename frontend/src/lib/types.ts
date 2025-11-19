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

export interface LocationSearchResult {
  id: string;            // Backend identifier (IATA, UUID, etc.)
  code: string;          // Display-friendly code (IATA, port code, etc.)
  display_name: string;  // "Brisbane (BNE), AU"
  type: string;          // e.g., "airport", "city", "port", "address"
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
  file_type?: string;
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
}


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
  payload_json?: V3QuoteComputeRequest;
  lines: V3QuoteLine[];
  totals: V3QuoteTotal;
}

export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: string | QuoteCustomerRef;
  contact: string | QuoteContactRef;
  mode: string;
  shipment_type: string; // The backend calculates and returns this
  incoterm: string;
  payment_term: string;
  service_scope: string;
  output_currency: string;
  
  origin_location: string;
  destination_location: string;
  
  status: string;
  valid_until: string; // Date string (YYYY-MM-DD)
  created_at: string; // ISO date string
  latest_version: V3QuoteVersion;
}

export type QuoteVersionChargeInput = V3ManualOverride;

export interface QuoteVersionCreatePayload {
  charges: QuoteVersionChargeInput[];
}
