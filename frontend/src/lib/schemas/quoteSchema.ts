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