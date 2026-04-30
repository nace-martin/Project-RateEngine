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

export interface UserBrandingRef {
  display_name: string;
  primary_color?: string | null;
  accent_color?: string | null;
  logo_url?: string | null;
}

export interface UserOrganizationRef {
  id: string;
  name: string;
  slug: string;
  branding?: UserBrandingRef | null;
}

export interface User {
  id?: number;
  username: string;
  email?: string | null;
  role: string;
  organization?: UserOrganizationRef | null;
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

export interface QuoteBrandingRef {
  display_name: string;
  support_email?: string | null;
  support_phone?: string | null;
  website_url?: string | null;
  address_lines?: string[];
  public_quote_tagline?: string | null;
  primary_color?: string | null;
  accent_color?: string | null;
  logo_url?: string | null;
}

export interface OrganizationBrandingSettings {
  organization_name: string;
  organization_slug: string;
  display_name: string;
  legal_name?: string;
  support_email?: string;
  support_phone?: string;
  website_url?: string;
  address_lines?: string;
  quote_footer_text?: string;
  public_quote_tagline?: string;
  email_signature_text?: string;
  primary_color?: string;
  accent_color?: string;
  logo_primary?: string | null;
  logo_primary_url?: string | null;
  logo_primary_missing?: boolean;
  logo_small?: string | null;
  logo_small_url?: string | null;
  logo_small_missing?: boolean;
  is_active: boolean;
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

// --- CRM TYPES ---
export type InteractionType = 'CALL' | 'MEETING' | 'EMAIL' | 'SITE_VISIT' | 'SYSTEM';

export interface Opportunity {
  id: string;
  company: string;
  company_name?: string;
  title: string;
  service_type: 'AIR' | 'SEA' | 'CUSTOMS' | 'DOMESTIC' | 'MULTIMODAL' | string;
  direction?: 'IMPORT' | 'EXPORT' | 'DOMESTIC' | string;
  scope?: string;
  origin?: string;
  destination?: string;
  estimated_weight_kg?: string | number | null;
  estimated_volume_cbm?: string | number | null;
  estimated_fcl_count?: number | null;
  estimated_frequency?: string;
  estimated_revenue?: string | number | null;
  estimated_currency?: string;
  status: 'NEW' | 'QUALIFIED' | 'QUOTED' | 'WON' | 'LOST' | string;
  priority: 'LOW' | 'MEDIUM' | 'HIGH' | string;
  owner?: number | null;
  owner_username?: string | null;
  next_action?: string;
  next_action_date?: string | null;
  last_activity_at?: string | null;
  won_at?: string | null;
  won_by?: number | null;
  won_by_username?: string | null;
  won_reason?: string;
  lost_reason?: string;
  is_active?: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface Interaction {
  id: string;
  company: string;
  company_name?: string;
  contact?: string | null;
  opportunity?: string | null;
  author?: number | null;
  author_username?: string | null;
  interaction_type: InteractionType;
  summary: string;
  outcomes?: string;
  next_action?: string;
  next_action_date?: string | null;
  is_system_generated?: boolean;
  system_event_type?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CreateInteractionPayload {
  company: string;
  contact?: string | null;
  opportunity?: string | null;
  interaction_type: Exclude<InteractionType, 'SYSTEM'>;
  summary: string;
  outcomes?: string;
  next_action?: string;
  next_action_date?: string | null;
}

export interface Task {
  id: string;
  company?: string | null;
  opportunity?: string | null;
  description: string;
  owner: number;
  owner_username?: string | null;
  due_date: string;
  status: 'PENDING' | 'COMPLETED' | 'CANCELLED' | string;
  completed_at?: string | null;
  completed_by?: number | null;
  completed_by_username?: string | null;
  created_at?: string;
  updated_at?: string;
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
  city_id?: string;
  city: string;
  state_province?: string;
  postcode?: string;
  country: string;
  country_name?: string;
}

export interface CustomerCommercialProfile {
  preferred_quote_currency: string;
  default_margin_percent?: string;
  min_margin_percent?: string;
  payment_term_default?: string;
}

export interface Customer {
  id: string;
  company_name: string;
  is_active?: boolean;
  audience_type: string;
  address_description?: string | null;
  primary_address?: CustomerAddress | null;
  contact_person_name?: string;
  contact_person_email?: string;
  contact_person_phone?: string;
  commercial_profile?: CustomerCommercialProfile | null;
}

export interface CountryOption {
  code: string;
  name: string;
}

export interface CityOption {
  id: string;
  name: string;
  country_code: string;
  country_name: string;
  display_name: string;
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
  package_type: string;
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
  // Internal/admin override inputs only. Standard quote UI does not send these.
  agent_id?: number | null;
  carrier_id?: number | null;
  buy_currency?: string;
  commodity_code?: string;
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
  component?: string | null;
  product_code?: string | null;
  description?: string | null;
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

export interface CanonicalQuoteFxApplied {
  applied: boolean;
  rate: string | null;
  source: string | null;
  snapshot_date: string | null;
  caf_percent: string | null;
  currency: string | null;
}

export interface CanonicalQuoteTaxBreakdown {
  gst_percent: string;
  gst_amount: string;
  tax_basis: string | null;
  by_code: Record<string, string>;
}

export interface CanonicalQuoteLineItem {
  line_id: string;
  product_code: string;
  description: string;
  component: string;
  basis: string;
  rule_family: string;
  service_family?: string | null;
  unit_type: string;
  quantity: string;
  currency: string;
  cost_currency?: string;
  sell_currency?: string;
  rate: string | null;
  cost_amount: string;
  sell_amount: string;
  tax_code: string;
  tax_amount: string;
  included_in_total: boolean;
  cost_source: string;
  rate_source: string;
  calculation_notes: string | null;
  is_spot_sourced: boolean;
  is_manual_override: boolean;
  sort_order: number;
}

export interface CanonicalQuoteResult {
  quote_id: string;
  status: string | null;
  customer_name: string | null;
  service_scope: string | null;
  mode: string | null;
  origin: string;
  destination: string;
  incoterm: string | null;
  cargo_type: string | null;
  pieces: number;
  actual_weight: string;
  volumetric_weight: string;
  chargeable_weight: string;
  dimensions_summary: string | null;
  line_items: CanonicalQuoteLineItem[];
  currency: string;
  sell_total: string;
  total_cost_pgk: string;
  total_sell_pgk: string;
  margin_amount: string;
  margin_percent: string;
  fx_applied: CanonicalQuoteFxApplied;
  tax_breakdown: CanonicalQuoteTaxBreakdown;
  warnings: string[];
  missing_components: string[];
  spot_required: boolean;
  engine_name: string | null;
  rate_source: string;
  service_notes: string | null;
  customer_notes: string | null;
  internal_notes: string | null;
  prepared_by: string | null;
  created_at: string | null;
  calculated_at: string | null;
  quote_version: number | null;
  payment_term?: string | null;
  valid_until?: string | null;
}

export interface V3QuoteComputeResponse {
  id: string; // UUID
  quote_number: string;
  customer: string | QuoteCustomerRef;
  contact: string | QuoteContactRef;
  branding?: QuoteBrandingRef | null;
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
  request_details_json?: Record<string, unknown> | null;
  created_by?: string | null; // Assigned Agent (Sales Rep)
  rate_provider?: string | null; // Agent who provided rates
  latest_version: V3QuoteVersion;
  quote_result?: CanonicalQuoteResult | null;
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
  quote_result?: CanonicalQuoteResult | null;
}

export interface Tier1Stats {
  active_customers: number;
  repeat_customers_pct: number;
  top_customers: { name: string; value: number }[];
}
