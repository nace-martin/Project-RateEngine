// frontend/src/lib/schemas/quoteSchema.ts

import { z } from 'zod'

// --- V3 Schemas ---

// Define enums for our dropdowns
// These should match the choices in the backend models
export const V3_MODES = {
  AIR: 'AIR',
} as const

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
 * IMPORTANT CONCEPTS:
 * - Service Scope (D2D, D2A, A2D, A2A) = Physical route we're quoting (what's included)
 * - Incoterm = Who bears risk/responsibility at each point (not what's quoted)
 * 
 * Therefore, most incoterms are valid for most scopes. The scope tells us WHAT to quote,
 * the incoterm tells us WHO bears risk.
 * 
 * SCOPE DEFINITIONS (vary by direction):
 * 
 * EXPORT (Origin = PNG):
 * - D2D: Origin Door (PNG) → Destination Door (overseas)
 * - D2A: Origin Door (PNG) → Destination Airport (overseas)
 * - A2D: Origin Airport (PNG) → Destination Door (overseas) - includes freight + dest delivery
 * - A2A: Origin Airport (PNG) → Destination Airport (overseas)
 * 
 * IMPORT (Destination = PNG):
 * - D2D: Origin Door (overseas) → Destination Door (PNG)
 * - D2A: Origin Door (overseas) → Destination Airport (PNG)
 * - A2D: Destination Airport (PNG) → Destination Door (PNG) - DEST CHARGES ONLY (clearance + delivery)
 * - A2A: Origin Airport (overseas) → Destination Airport (PNG)
 * 
 * Note: For Import A2D, the "Airport" refers to OUR airport (POM), not the origin.
 * This is for quoting destination clearance and delivery charges only - freight already shipped.
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
  // Overseas agent is "seller", our customer (PNG) is "buyer"
  if (isImport) {
    switch (serviceScope) {
      case 'A2D':
        // IMPORT A2D = Destination Airport (POM) → Consignee's Door in PNG
        // This is for DESTINATION CHARGES ONLY - clearance and delivery
        // Freight has already been shipped by overseas agent
        if (paymentTerm === 'COLLECT') {
          // We receive at our airport, clear and deliver - buyer pays
          return ['EXW', 'FCA'];
        }
        // Prepaid: Agent has prepaid, we clear and deliver
        return ['DAP', 'DDP'];

      case 'D2D':
        // Full door-to-door import - all incoterms possible
        if (paymentTerm === 'COLLECT') {
          // We pay freight - EXW/FCA typical
          return ['EXW', 'FCA', 'DAP'];
        }
        // Prepaid: Full range
        return ['EXW', 'FCA', 'CPT', 'DAP', 'DDP'];

      case 'D2A':
        // Origin Door (overseas) → Our Airport (POM)
        // Agent picks up from shipper and flies to us - we receive at airport
        if (paymentTerm === 'COLLECT') {
          return ['EXW', 'FCA'];
        }
        return ['FCA', 'CPT'];

      case 'A2A':
        // Origin Airport (overseas) → Destination Airport (POM)
        if (paymentTerm === 'COLLECT') {
          return ['EXW'];
        }
        return ['EXW', 'FCA'];

      default:
        return ['DAP'];
    }
  }

  // ===== EXPORT QUOTES (Origin = PNG) =====
  // Our customer (PNG) is "seller", overseas consignee is "buyer"
  switch (serviceScope) {
    case 'D2D':
      // Full door-to-door export
      // EXW is valid: seller makes available at door, buyer/agent arranges everything
      // All incoterms are technically valid for D2D
      if (paymentTerm === 'COLLECT') {
        // Agent pays freight - EXW most common
        return ['EXW', 'FCA', 'DAP'];
      }
      // Prepaid: Full range, EXW to DDP
      return ['EXW', 'FCA', 'CPT', 'DAP', 'DDP'];

    case 'D2A':
      // Origin Door to Destination Airport
      if (paymentTerm === 'COLLECT') {
        // Agent pays freight
        return ['EXW', 'FCA'];
      }
      // Prepaid: May include freight (CPT)
      return ['EXW', 'FCA', 'CPT'];

    case 'A2D':
      // Origin Airport to Destination Door
      // Seller covers destination delivery
      return ['CPT', 'DAP', 'DDP'];

    case 'A2A':
      // Airport to Airport only
      return ['EXW', 'FCA'];

    default:
      return ['EXW', 'FCA', 'CPT', 'DAP', 'DDP'];
  }
}

/**
 * Get the default incoterm for a given shipment configuration.
 * 
 * Defaults are based on most common usage:
 * - D2D: EXW (buyer arranges full logistics, common for commercial exports)
 * - D2A: FCA (seller delivers to carrier at airport)
 * - A2D: DAP (seller delivers to destination)
 * - A2A: EXW (minimal seller responsibility)
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
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'DAP';

      case 'D2D':
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'DAP';

      case 'D2A':
        if (paymentTerm === 'COLLECT') return 'EXW';
        return 'FCA';

      case 'A2A':
        return 'EXW';

      default:
        return 'DAP';
    }
  }

  // ===== EXPORT QUOTES =====
  switch (serviceScope) {
    case 'D2D':
      // EXW is most common for D2D exports - buyer arranges logistics
      if (paymentTerm === 'COLLECT') return 'EXW';
      return 'EXW';  // Changed from DAP to EXW per user guidance

    case 'D2A':
      // FCA common for D2A (seller delivers to carrier)
      return 'FCA';

    case 'A2D':
      // DAP for A2D (seller covers destination)
      return 'DAP';

    case 'A2A':
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

export const V3_PACKAGE_TYPES = {
  BOX: 'Box',
  PALLET: 'Pallet',
  SKID: 'Skid',
  CRATE: 'Crate',
  CARTON: 'Carton',
  DRUM: 'Drum',
  BAG: 'Bag',
  OTHER: 'Other',
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
  package_type: z.nativeEnum(V3_PACKAGE_TYPES).default(V3_PACKAGE_TYPES.BOX),
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
    quote_id: z.string().optional(),
    customer_id: z.string().uuid({ message: 'Customer must be selected.' }),
    contact_id: z.string().uuid({ message: 'Contact must be selected.' }),

    // --- Step 2: Shipment Type ---
    mode: z.nativeEnum(V3_MODES, {
      error: 'Mode of transport is required.',
    }),
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
