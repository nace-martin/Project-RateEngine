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

// --- NEW: Schema for a single dimension line ---
// This is the individual line schema
const dimensionLineSchema = z.object({
  pieces: z.number().positive("Pcs must be at least 1").int(),
  length_cm: z.number().positive("L must be positive"),
  width_cm: z.number().positive("W must be positive"),
  height_cm: z.number().positive("H must be positive"),
  gross_weight_kg: z.number().positive("Kg must be positive"),
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
export const V3_MODES = {
  AIR: "AIR",
  SEA: "SEA",
  ROAD: "ROAD",
} as const;
export const V3_SHIPMENT_TYPES = {
  IMPORT: "IMPORT",
  EXPORT: "EXPORT",
  DOMESTIC: "DOMESTIC",
} as const;
export const V3_INCOTERMS = {
  EXW: "EXW",
  FOB: "FOB",
  DAP: "DAP",
  DDP: "DDP",
  CPT: "CPT",
  CFR: "CFR",
} as const; // Add more as needed
export const V3_PAYMENT_TERMS = {
  PREPAID: "PREPAID",
  COLLECT: "COLLECT",
} as const;

// Optional schema for manual overrides (Spot Rates)
const manualCostOverrideSchema = z.object({
  service_component_id: z.number(),
  cost_fcy: z.number().positive(),
  currency: z.string().length(3),
  unit: z.string(),
  min_charge_fcy: z.number().positive().optional(),
});

// The main V3 Quote Request Schema
export const quoteFormSchemaV3 = z.object({
  // --- Step 1: Customer ---
  customer_id: z.number().min(1, { message: "Customer must be selected." }),
  contact_id: z.number().min(1, { message: "Contact must be selected." }),

  // --- Step 2: Shipment Type ---
  mode: z.enum(Object.values(V3_MODES), {
    error: "Mode of transport is required.",
  }),
  shipment_type: z.enum(Object.values(V3_SHIPMENT_TYPES), {
    error: "Shipment type is required.",
  }),
  incoterm: z.enum(Object.values(V3_INCOTERMS), {
    error: "Incoterm is required.",
  }),
  payment_term: z.enum(Object.values(V3_PAYMENT_TERMS)),

  // --- Step 3: Details ---
  origin_airport_code: z
    .string()
    .min(1, "Origin is required.")
    .length(3, "Must be a 3-letter IATA code."),
  destination_airport_code: z
    .string()
    .min(1, "Destination is required.")
    .length(3, "Must be a 3-letter IATA code."),

  is_dangerous_goods: z.boolean(),

  // --- Step 4: Dimensions (The Array) ---
  dimensions: z
    .array(dimensionLineSchema)
    .min(1, "You must add at least one dimension line."), // <-- THIS IS THE FIX

  // --- Spot Rate Overrides ---
  overrides: z.array(manualCostOverrideSchema).optional(),
});

// This creates a TypeScript type from our schema
export type QuoteFormSchemaV3 = z.infer<typeof quoteFormSchemaV3>;
