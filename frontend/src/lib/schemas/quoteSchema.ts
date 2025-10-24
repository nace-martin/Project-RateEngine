// frontend/src/lib/schemas/quoteSchema.ts

import { z } from "zod";

// --- Base Types ---
const PartySchema = z.string().uuid({ message: "Please select a valid company." });

const PieceSchema = z.object({
  pieces: z.coerce.number().min(1, "Must have at least 1 piece"),
  length: z.coerce.number().positive("Length must be positive"),
  width: z.coerce.number().positive("Width must be positive"),
  height: z.coerce.number().positive("Height must be positive"),
  weight: z.coerce.number().positive("Weight must be positive"),
});

// --- NEW: Schema for a single charge line ---
const ChargeLineSchema = z.object({
  description: z.string().min(1, "Description is required."),
  currency: z.string().length(3, "Currency must be 3 letters."), // Could refine with z.enum later
  amount: z.coerce.number().positive("Amount must be positive."),
});
// ---

// --- Mode-Specific Schemas ---

const AirModeSchema = z.object({
  mode: z.literal("AIR"),
  scenario: z.enum([
    "IMPORT_D2D_COLLECT", 
    "EXPORT_D2D_PREPAID", 
    "IMPORT_A2D_AGENT_AUD",
    // Add other scenarios as needed
  ]),
  bill_to_id: PartySchema,
  shipper_id: PartySchema,
  consignee_id: PartySchema,
  contact_id: z.string().uuid().optional(), // Optional contact associated with Bill To
  origin_code: z.string().length(3, "Origin must be a 3-letter code").toUpperCase(),
  destination_code: z.string().length(3, "Destination must be a 3-letter code").toUpperCase(),
  pieces: z.array(PieceSchema).min(1, "At least one piece is required."),
  
  // --- ADD THESE FIELDS ---
  buy_lines: z.array(ChargeLineSchema).optional(), // Origin/Freight charges
  agent_dest_lines_aud: z.array(ChargeLineSchema).optional(), // Destination charges (AUD for exports)
  // ---
});

// --- Discriminated Union ---
export const QuoteFormSchema = z.discriminatedUnion("mode", [
  AirModeSchema,
  // z.object({ mode: z.literal("SEA"), ... }),
  // z.object({ mode: z.literal("CUSTOMS"), ... }), 
]);

// Infer the TypeScript type from the schema
export type QuoteFormData = z.infer<typeof QuoteFormSchema>;

// --- V3 Schemas ---

// Define enums for our dropdowns
// These should match the choices in the backend models
export const V3_MODES = ["AIR", "SEA", "ROAD"] as const;
export const V3_SHIPMENT_TYPES = ["IMPORT", "EXPORT", "DOMESTIC"] as const;
export const V3_INCOTERMS = [
  "EXW",
  "FOB",
  "DAP",
  "DDP",
  "CPT",
  "CFR",
] as const; // Add more as needed
export const V3_PAYMENT_TERMS = ["PREPAID", "COLLECT"] as const;

// Optional schema for manual overrides (Spot Rates)
const manualCostOverrideSchema = z.object({
  service_component_id: z.number(),
  cost_fcy: z.number().positive(),
  currency: z.string().length(3),
  unit: z.string(),
  min_charge_fcy: z.number().positive().optional(),
});

// The main V3 Quote Request Schema
// This matches our V3QuoteComputeRequestSerializer on the backend
export const quoteFormSchemaV3 = z.object({
  // --- Step 1: Customer ---
  customer_id: z.number({ required_error: "Customer must be selected." }),
  contact_id: z.number({ required_error: "Contact must be selected." }),

  // --- Step 2: Shipment Type ---
  mode: z.nativeEnum(V3_MODES, {
    required_error: "Mode of transport is required.",
  }),
  shipment_type: z.nativeEnum(V3_SHIPMENT_TYPES, {
    required_error: "Shipment type is required.",
  }),
  incoterm: z.nativeEnum(V3_INCOTERMS, {
    required_error: "Incoterm is required.",
  }),
  payment_term: z.nativeEnum(V3_PAYMENT_TERMS).default("PREPAID"),
  output_currency: z.string().length(3).optional(), // e.g. "USD"

  // --- Step 3: Details ---
  origin_airport_code: z
    .string({ required_error: "Origin is required." })
    .length(3, "Must be a 3-letter IATA code."),
  destination_airport_code: z
    .string({ required_error: "Destination is required." })
    .length(3, "Must be a 3-letter IATA code."),

  pieces: z
    .number({ required_error: "Number of pieces is required." })
    .positive("Pieces must be at least 1.")
    .int(),
  gross_weight_kg: z
    .number({ required_error: "Gross weight is required." })
    .positive("Weight must be positive."),
  volume_cbm: z
    .number({ required_error: "Volume is required." })
    .positive("Volume must be positive."),

  is_dangerous_goods: z.boolean().default(false),

  // --- Spot Rate Overrides ---
  overrides: z.array(manualCostOverrideSchema).optional(),
});

// This creates a TypeScript type from our schema
export type QuoteFormSchemaV3 = z.infer<typeof quoteFormSchemaV3>;