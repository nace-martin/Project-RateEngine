// frontend/src/lib/schemas/quoteSchema.ts

import { z } from 'zod'

// --- V3 Schemas ---

// Define enums for our dropdowns
// These should match the choices in the backend models
export const V3_MODES = {
  AIR: 'AIR',
  // SEA: 'SEA', // Add when sea is ready
  // ROAD: 'ROAD',
} as const

// This is no longer needed, as the backend auto-detects it.
// export const V3_SHIPMENT_TYPES = { ... };

export const V3_INCOTERMS = {
  EXW: 'EXW',
  FOB: 'FOB',
  DAP: 'DAP',
  DDP: 'DDP',
  CPT: 'CPT',
  CFR: 'CFR',
} as const
export const V3_PAYMENT_TERMS = {
  PREPAID: 'PREPAID',
  COLLECT: 'COLLECT',
} as const
export const V3_SERVICE_SCOPES = {
  D2D: 'D2D',
  D2A: 'D2A',
  A2D: 'A2D',
  A2A: 'A2A',
} as const

export const V3_LOCATION_TYPES = {
  AIRPORT: 'AIRPORT',
  PORT: 'PORT',
  ADDRESS: 'ADDRESS',
  CITY: 'CITY',
} as const

const airportCodeSchema = z
  .string()
  .trim()
  .transform((val) => val.toUpperCase())
  .refine(
    (val) => val === '' || /^[A-Z]{3}$/.test(val),
    'Must be a 3-letter IATA code or empty.',
  )

// This is the individual dimension line schema
const dimensionLineSchema = z.object({
  pieces: z.coerce
    .number()
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
})

// Optional schema for manual overrides (Spot Rates)
const manualCostOverrideSchema = z.object({
  service_component_id: z.string().min(1, 'Service must be selected.'),
  cost_fcy: z.coerce.string().min(1, 'Cost is required'),
  currency: z.string().length(3, 'Must be 3-letter code'),
  unit: z.string().min(1, 'Unit is required'),
  min_charge_fcy: z.coerce.string().optional(),
  valid_until: z.string().optional(),
})

// The main V3 Quote Request Schema
export const quoteFormSchemaV3 = z
  .object({
    // --- Step 1: Customer ---
    customer_id: z.string().uuid({ message: 'Customer must be selected.' }),
    contact_id: z.string().uuid({ message: 'Contact must be selected.' }),

    // --- Step 2: Shipment Type ---
    mode: z.nativeEnum(V3_MODES, {
      error: 'Mode of transport is required.',
    }),
    // --- REMOVED 'shipment_type' ---
    incoterm: z.nativeEnum(V3_INCOTERMS, {
      error: 'Incoterm is required.',
    }),
    payment_term: z.nativeEnum(V3_PAYMENT_TERMS),
    service_scope: z.nativeEnum(V3_SERVICE_SCOPES, {
      error: 'Service scope is required.',
    }),

    // --- Step 3: Details ---
    // --- UPDATED: Legacy airport fields are optional ---
    origin_airport: airportCodeSchema.default(''),
    destination_airport: airportCodeSchema.default(''),
    // --- END UPDATE ---
    origin_location_type: z.nativeEnum(V3_LOCATION_TYPES).default('AIRPORT'),
    origin_location_id: z
      .string()
      .min(1, 'Origin is required.'),
    destination_location_type: z.nativeEnum(V3_LOCATION_TYPES).default('AIRPORT'),
    destination_location_id: z
      .string()
      .min(1, 'Destination is required.'),

    is_dangerous_goods: z.boolean().default(false),
    output_currency: z.string().length(3).optional(),

    // --- Step 4: Dimensions (The Array) ---
    dimensions: z
      .array(dimensionLineSchema)
      .min(1, 'You must add at least one dimension line.'),

    // --- Spot Rate Overrides ---
    overrides: z.array(manualCostOverrideSchema).optional(),
  })
  .superRefine((data, ctx) => {
    const ensureAirportCode = (
      locationType: string,
      airportField: 'origin_airport' | 'destination_airport',
      value: string,
    ) => {
      if (locationType === V3_LOCATION_TYPES.AIRPORT && value.length !== 3) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: [airportField],
          message: 'Select an airport or provide a valid IATA code.',
        });
      }
    };

    ensureAirportCode(
      data.origin_location_type,
      'origin_airport',
      data.origin_airport,
    );
    ensureAirportCode(
      data.destination_location_type,
      'destination_airport',
      data.destination_airport,
    );
  })

// This creates a TypeScript type from our schema
export type QuoteFormSchemaV3 = z.infer<typeof quoteFormSchemaV3>
