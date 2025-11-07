// frontend/src/lib/schemas/quoteSchema.ts

import { z } from 'zod';

// --- V3 Schemas ---

// Define enums for our dropdowns
// These should match the choices in the backend models
export const V3_MODES = {
  AIR: 'AIR',
  SEA: 'SEA',
  ROAD: 'ROAD',
} as const;
export const V3_SHIPMENT_TYPES = {
  IMPORT: 'IMPORT',
  EXPORT: 'EXPORT',
  DOMESTIC: 'DOMESTIC',
} as const;
export const V3_INCOTERMS = {
  EXW: 'EXW',
  FOB: 'FOB',
  DAP: 'DAP',
  DDP: 'DDP',
  CPT: 'CPT',
  CFR: 'CFR',
} as const; // Add more as needed
export const V3_PAYMENT_TERMS = {
  PREPAID: 'PREPAID',
  COLLECT: 'COLLECT',
} as const;

// This is the individual dimension line schema
// Updated to use string coercion to match V3DimensionInput type
const dimensionLineSchema = z.object({
  pieces: z.coerce
    .number({ invalid_type_error: 'Must be a number' })
    .min(1, 'Pcs must be at least 1')
    .int(),
  length_cm: z.coerce
    .string()
    .min(1, 'L is required')
    .refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) > 0, {
      message: 'L must be > 0',
    }),
  width_cm: z.coerce
    .string()
    .min(1, 'W is required')
    .refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) > 0, {
      message: 'W must be > 0',
    }),
  height_cm: z.coerce
    .string()
    .min(1, 'H is required')
    .refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) > 0, {
      message: 'H must be > 0',
    }),
  gross_weight_kg: z.coerce
    .string()
    .min(1, 'Kg is required')
    .refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) > 0, {
      message: 'Kg must be > 0',
    }),
});

// Optional schema for manual overrides (Spot Rates)
// Updated service_component_id to string (for UUID)
const manualCostOverrideSchema = z.object({
  service_component_id: z.string().min(1, 'Service must be selected.'),
  cost_fcy: z.coerce.string().min(1, 'Cost is required'),
  currency: z.string().length(3, 'Must be 3-letter code'),
  unit: z.string().min(1, 'Unit is required'),
  min_charge_fcy: z.coerce.string().optional(),
});

// The main V3 Quote Request Schema
export const quoteFormSchemaV3 = z.object({
  // --- Step 1: Customer ---
  customer_id: z.string().uuid({ message: 'Customer must be selected.' }),
  contact_id: z.string().uuid({ message: 'Contact must be selected.' }),

  // --- Step 2: Shipment Type ---
  mode: z.nativeEnum(V3_MODES, {
    error: 'Mode of transport is required.',
  }),
  shipment_type: z.nativeEnum(V3_SHIPMENT_TYPES, {
    error: 'Shipment type is required.',
  }),
  incoterm: z.nativeEnum(V3_INCOTERMS, {
    error: 'Incoterm is required.',
  }),
  payment_term: z.nativeEnum(V3_PAYMENT_TERMS),

  // --- Step 3: Details ---
  origin_airport_code: z
    .string()
    .min(1, 'Origin is required.')
    .length(3, 'Must be a 3-letter IATA code.')
    .toUpperCase(),
  destination_airport_code: z
    .string()
    .min(1, 'Destination is required.')
    .length(3, 'Must be a 3-letter IATA code.')
    .toUpperCase(),

  is_dangerous_goods: z.boolean().default(false),
  output_currency: z.string().length(3).optional(),

  // --- Step 4: Dimensions (The Array) ---
  dimensions: z
    .array(dimensionLineSchema)
    .min(1, 'You must add at least one dimension line.'),

  // --- Spot Rate Overrides ---
  overrides: z.array(manualCostOverrideSchema).optional(),
});

// This creates a TypeScript type from our schema
export type QuoteFormSchemaV3 = z.infer<typeof quoteFormSchemaV3>;