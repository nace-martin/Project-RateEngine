import type { SPEChargeLine, SPEProductCodeSummary } from "@/lib/spot-types";

const GENERIC_SPOT_LABELS = new Set(
    [
        "Spot Origin Charge",
        "Spot Freight Charge",
        "Spot Destination Charge",
        "Spot Charge",
    ].map((label) => label.trim().toUpperCase())
);

const cleanText = (value?: string | null) => String(value || "").trim();

export const isGenericSpotLabel = (value?: string | null) => {
    const normalized = cleanText(value).toUpperCase();
    return Boolean(normalized) && GENERIC_SPOT_LABELS.has(normalized);
};

export const getEffectiveProductCode = (
    charge: Pick<
        SPEChargeLine,
        | "manual_resolution_status"
        | "manual_resolved_product_code"
        | "effective_resolved_product_code"
        | "resolved_product_code"
    >
): SPEProductCodeSummary | null => {
    if (charge.manual_resolution_status === "RESOLVED") {
        return (
            charge.manual_resolved_product_code ||
            charge.effective_resolved_product_code ||
            charge.resolved_product_code ||
            null
        );
    }

    return charge.effective_resolved_product_code || charge.resolved_product_code || null;
};

export const formatProductCodeDisplay = (
    productCode?: SPEProductCodeSummary | null,
    options: { includeCode?: boolean } = {}
) => {
    if (!productCode?.code) return "";
    const description = cleanText(productCode.description);
    if (!description) return productCode.code;
    return options.includeCode === false ? description : `${description} (${productCode.code})`;
};

export const getSpotChargeDisplayLabel = (
    charge: Pick<
        SPEChargeLine,
        | "description"
        | "source_label"
        | "normalized_label"
        | "manual_resolution_status"
        | "manual_resolved_product_code"
        | "effective_resolved_product_code"
        | "resolved_product_code"
    >,
    options: { includeProductCode?: boolean } = {}
) => {
    const productCodeLabel = formatProductCodeDisplay(getEffectiveProductCode(charge), {
        includeCode: options.includeProductCode !== false,
    });
    if (productCodeLabel) return productCodeLabel;

    const candidates = [charge.source_label, charge.description, charge.normalized_label]
        .map(cleanText)
        .filter(Boolean);
    const nonGeneric = candidates.find((candidate) => !isGenericSpotLabel(candidate));
    return nonGeneric || candidates[0] || "Imported charge";
};
