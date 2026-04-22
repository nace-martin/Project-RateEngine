import { z } from "zod";
import { SPOT_SUPPORTED_CURRENCIES } from "@/lib/spot-types";

export const chargeLineSchema = z.object({
    id: z.string().optional(),
    charge_line_id: z.string().optional(),
    code: z.string().optional(),
    description: z.string().min(1, "Description is required"),
    amount: z.string().refine((val) => !isNaN(parseFloat(val)) && parseFloat(val) > 0, {
        message: "Amount must be greater than 0",
    }),
    currency: z.enum(SPOT_SUPPORTED_CURRENCIES),
    unit: z.enum([
        "per_kg", "flat", "per_awb", "per_shipment", "min_or_per_kg", "percentage",
        "per_trip", "per_set", "per_man"
    ]),
    bucket: z.enum(["airfreight", "origin_charges", "destination_charges"]),
    is_primary_cost: z.boolean().default(false),
    conditional: z.boolean().default(false),
    source_reference: z.string().min(1, "Source reference is required"),
    min_charge: z.string().optional().nullable(), // Form handles as string, converted later
    percentage_basis: z.string().optional().nullable(),
    note: z.string().optional(),
    exclude_from_totals: z.boolean().optional(),
    source_label: z.string().optional(),
    normalized_label: z.string().optional(),
    normalization_status: z.enum(["MATCHED", "UNMAPPED", "AMBIGUOUS"]).optional().nullable(),
    normalization_method: z.string().optional().nullable(),
    matched_alias_id: z.number().int().optional().nullable(),
    resolved_product_code: z
        .object({
            id: z.number().int(),
            code: z.string(),
            description: z.string(),
        })
        .optional()
        .nullable(),
    manual_resolution_status: z.enum(["RESOLVED"]).optional().nullable(),
    manual_resolved_product_code: z
        .object({
            id: z.number().int(),
            code: z.string(),
            description: z.string(),
        })
        .optional()
        .nullable(),
    manual_resolution_by_user_id: z.string().optional().nullable(),
    manual_resolution_by_username: z.string().optional().nullable(),
    manual_resolution_at: z.string().optional().nullable(),
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

export type SpotFormInputValues = z.input<typeof spotFormSchema>;
export type SpotFormSubmitValues = z.output<typeof spotFormSchema>;
export type SpotFormValues = SpotFormInputValues;
export type SpotChargeLineValues = z.input<typeof chargeLineSchema>;
