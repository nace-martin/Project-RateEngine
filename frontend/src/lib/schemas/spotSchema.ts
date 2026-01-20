import { z } from "zod";

export const chargeLineSchema = z.object({
    id: z.string().optional(),
    code: z.string().optional(),
    description: z.string().min(1, "Description is required"),
    amount: z.string().refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) >= 0, {
        message: "Amount must be a positive number",
    }),
    currency: z.enum(["SGD", "USD", "AUD", "PGK", "NZD", "HKD"]),
    unit: z.enum([
        "per_kg", "flat", "per_awb", "per_shipment", "min_or_per_kg", "percentage",
        "per_trip", "per_set", "per_man"
    ]),
    bucket: z.enum(["airfreight", "origin_charges", "destination_charges"]),
    is_primary_cost: z.boolean().default(false),
    conditional: z.boolean().default(false),
    source_reference: z.string().min(1, "Source reference is required"),
    min_charge: z.string().optional().nullable(), // Form handles as string, converted later
    note: z.string().optional(),
});

export const spotFormSchema = z.object({
    charges: z.array(chargeLineSchema).refine(
        (charges) => charges.length > 0,
        { message: "At least one charge line is required." }
    ).refine(
        (charges) => {
            // If airfreight bucket is present (implied by context usually, but here we check existence)
            // Check if any charge is in airfreight bucket
            const airfreightCharges = charges.filter(c => c.bucket === 'airfreight');
            if (airfreightCharges.length > 0) {
                // Must have exactly one primary
                const primary = airfreightCharges.filter(c => c.is_primary_cost);
                return primary.length === 1;
            }
            return true;
        },
        { message: "Exactly one primary airfreight charge is required." }
    ),
});

export type SpotFormValues = z.infer<typeof spotFormSchema>;
export type SpotChargeLineValues = z.infer<typeof chargeLineSchema>;
