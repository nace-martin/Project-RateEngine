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
  actual_weight_kg: string;
  total_sell: string; // We'll use string for decimals for now
  created_at: string;
}

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
}