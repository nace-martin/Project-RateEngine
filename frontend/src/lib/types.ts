// This defines the structure of a single Client object
export interface Client {
  id: number;
  name: string;
  email: string;
  phone: string;
  org_type: string;
  created_at: string;
}

export interface Quote {
  id: number;
  client: Client; // The related client object
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

// Response shape from POST /api/quote/compute
// Backend currently returns either top-level sell_total or totals.sell_total
export interface ComputeQuoteResponse {
  quote_id: number;
  status: QuoteStatus;
  manual_reasons?: string[];
  sell_total?: Money;
  totals?: {
    sell_total: Money;
    buy_total?: Money;
    tax_total?: Money;
    margin_abs?: Money;
    // margin_pct uses currency '%'
    margin_pct?: Money;
  };
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
