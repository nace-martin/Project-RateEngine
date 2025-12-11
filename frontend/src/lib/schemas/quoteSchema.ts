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
  FCA: 'FCA',
  FOB: 'FOB',
  CPT: 'CPT',
  DAP: 'DAP',
  DDP: 'DDP',
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

/**
 * Get valid incoterms based on shipment direction, service scope, and payment term.
 * 
 * Logic based on ICC Incoterms® 2020:
 * 
 * EXPORT (Origin = PNG):
 * - D2A + PREPAID: EXW, FCA, CPT (seller delivers to airport, may include freight)
 * - D2A + COLLECT: EXW, FCA (agent pays freight)
 * - D2D + PREPAID: CPT, DAP, DDP (full service to door)
 * - D2D + COLLECT: DAP (agent covers origin country charges)
 * - A2A: EXW (airport to airport, minimal seller responsibility)
 * - A2D: CPT, DAP (destination delivery included)
 * 
 * IMPORT (Destination = PNG):
 * - A2D + PREPAID: DAP (agent delivers to airport, we deliver to door, freight prepaid)
 * - A2D + COLLECT: EXW, FCA (we collect at origin airport, pay freight)
 * - D2D + PREPAID: DAP, DDP (full door-to-door, seller covers freight)
 * - D2D + COLLECT: DAP (we pay freight collect)
 * - D2A + PREPAID: FCA, CPT (origin door to our airport, freight prepaid)
 * - D2A + COLLECT: EXW, FCA (we pay freight collect)
 * - A2A + PREPAID: FCA (airport to airport, freight prepaid)
 * - A2A + COLLECT: EXW (we collect at origin airport)
 * 
 * @param isImport - True if shipment is import (destination is PG)
 * @param serviceScope - The service scope (D2D, D2A, A2D, A2A)
 * @param paymentTerm - Optional payment term (PREPAID or COLLECT)
 * @returns Array of valid incoterm values
 */
export function getValidIncoterms(
  isImport: boolean,
  serviceScope: string,
  paymentTerm?: string
): string[] {

  // ===== IMPORT QUOTES (Destination = PNG) =====
  // For imports, overseas agent is "seller", we (PNG) are "buyer"
  if (isImport) {
    switch (serviceScope) {
      case 'A2D':
        // Agent delivers to their airport, we receive at POM and deliver to customer
        if (paymentTerm === 'COLLECT') {
          // We pay freight collect - seller only delivers to origin airport
          return ['EXW', 'FCA'];
        }
        // Prepaid: Agent pays freight, DAP (delivered at place)
        return ['DAP'];

      case 'D2D':
        // Full door-to-door import
        if (paymentTerm === 'COLLECT') {
          // We pay freight collect - still need DAP for destination delivery
          return ['DAP'];
        }
        // Prepaid: Full service, DAP or DDP
        return ['DAP', 'DDP'];

      case 'D2A':
        // Origin door to our airport
        if (paymentTerm === 'COLLECT') {
          // We pay freight collect
          return ['EXW', 'FCA'];
        }
        // Prepaid: Agent pays freight
        return ['FCA', 'CPT'];

      case 'A2A':
        // Airport to airport
        if (paymentTerm === 'COLLECT') {
          // We pay freight collect from origin airport
          return ['EXW'];
        }
        // Prepaid: Agent pays freight
        return ['FCA'];

      default:
        return ['DAP'];
    }
  }

  // ===== EXPORT QUOTES (Origin = PNG) =====
  switch (serviceScope) {
    case 'D2A':
      // Door to airport export
      if (paymentTerm === 'COLLECT') {
        // Agent pays freight, so EXW or FCA only
        return ['EXW', 'FCA'];
      }
      // Prepaid: We may cover freight (CPT)
      return ['EXW', 'FCA', 'CPT'];

    case 'D2D':
      // Door to door export
      if (paymentTerm === 'COLLECT') {
        // Agent handles destination charges
        return ['DAP'];
      }
      // Prepaid: Full control
      return ['CPT', 'DAP', 'DDP'];

    case 'A2D':
      // Airport to door (we deliver at destination)
      return ['CPT', 'DAP'];

    case 'A2A':
      // Airport to airport only
      return ['EXW'];

    default:
      // Default for export
      return ['EXW', 'FCA', 'CPT', 'DAP', 'DDP'];
  }
}

/**
 * Get the default incoterm for a given shipment configuration.
 * Used for auto-selection when user changes direction, scope, or payment term.
 * 
 * @param isImport - True if shipment is import
 * @param serviceScope - The service scope
 * @param paymentTerm - Optional payment term
 * @returns The recommended default incoterm
 */
export function getDefaultIncoterm(
  isImport: boolean,
  serviceScope: string,
  paymentTerm?: string
): string {

  // ===== IMPORT QUOTES =====
  if (isImport) {
    switch (serviceScope) {
      case 'A2D':
        // COLLECT: We pay freight, EXW is common
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'DAP';

      case 'D2D':
        return 'DAP';

      case 'D2A':
        // COLLECT: We pay freight
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'FCA';

      case 'A2A':
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'FCA';

      default:
        return 'DAP';
    }
  }

  // ===== EXPORT QUOTES =====
  switch (serviceScope) {
    case 'D2A':
      // For D2A exports, FCA is most common (Free Carrier to airport)
      return 'FCA';

    case 'D2D':
      // For D2D exports, DAP is most common (Delivered at Place)
      return 'DAP';

    case 'A2D':
      // Airport to door, DAP makes sense
      return 'DAP';

    case 'A2A':
      // Airport to airport, EXW
      return 'EXW';

    default:
      return 'EXW';
  }
}

export const V3_LOCATION_TYPES = {
  AIRPORT: 'AIRPORT',
  PORT: 'PORT',
  ADDRESS: 'ADDRESS',
  CITY: 'CITY',
} as const

export const V3_CARGO_TYPES = {
  GENERAL: 'General Cargo',
  DANGEROUS_GOODS: 'Dangerous Goods',
  PERISHABLE: 'Perishable / Cold Chain',
  LIVE_ANIMALS: 'Live Animals',
  VALUABLE: 'Valuable / High-Value',
  OVERSIZED: 'Oversized / OOG',
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
  package_type: z.string().min(1, 'Type is required').default('Box'),
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

    // --- Cargo Category ---
    cargo_type: z.nativeEnum(V3_CARGO_TYPES).default(V3_CARGO_TYPES.GENERAL),

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
