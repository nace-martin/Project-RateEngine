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
  origin_code: z.string().length(3, "Origin must be a 3-letter code").toUpperCase(),
  destination_code: z.string().length(3, "Destination must be a 3-letter code").toUpperCase(),
  pieces: z.array(PieceSchema).min(1, "At least one piece is required."),
  // Add fields for DG, Door Pickup toggles later
  // dangerousGoods: z.boolean().optional(),
  // doorPickup: z.boolean().optional(),
});

// --- Discriminated Union ---
// This allows us to add SEA, CUSTOMS later
export const QuoteFormSchema = z.discriminatedUnion("mode", [
  AirModeSchema,
  // z.object({ mode: z.literal("SEA"), ... }), // Example for later
  // z.object({ mode: z.literal("CUSTOMS"), ... }), // Example for later
]);

// Infer the TypeScript type from the schema
export type QuoteFormData = z.infer<typeof QuoteFormSchema>;