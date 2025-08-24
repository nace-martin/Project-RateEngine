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
  client: number; // The ID of the related client
  origin: string;
  destination: string;
  mode: string;
  actual_weight_kg: string;
  total_sell: string; // We'll use string for decimals for now
  created_at: string;
}