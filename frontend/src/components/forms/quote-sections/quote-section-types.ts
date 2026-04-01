"use client";

import type { QuoteFormSchemaV3 } from "../../../lib/schemas/quoteSchema.ts";

export type QuoteFormData = QuoteFormSchemaV3;

export type QuoteValidationState = {
  customer: boolean;
  route: boolean;
  terms: boolean;
  cargo: boolean;
};

export type QuoteSectionStatus = "active" | "completed";
export type QuoteSectionIndex = 0 | 1 | 2 | 3 | 4;

export const DEFAULT_QUOTE_VALIDATION_STATE: QuoteValidationState = {
  customer: false,
  route: false,
  terms: false,
  cargo: false,
};

const hasText = (value: unknown) =>
  typeof value === "string" && value.trim().length > 0;

const isPositiveValue = (value: unknown) => {
  const numericValue =
    typeof value === "number" ? value : Number.parseFloat(String(value ?? ""));
  return Number.isFinite(numericValue) && numericValue > 0;
};

export const getCompletedFieldClass = (isComplete: boolean) =>
  isComplete
    ? "border-primary bg-primary text-white ring-1 ring-primary/25 hover:border-primary hover:bg-primary/95 focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 [&_svg]:text-white/80"
    : "";

export const getSequentialQuoteStep = (
  validationState: QuoteValidationState,
): QuoteSectionIndex => {
  if (!validationState.customer) return 0;
  if (!validationState.route) return 1;
  if (!validationState.terms) return 2;
  if (!validationState.cargo) return 3;
  return 4;
};

export const getQuoteValidationState = (
  formData: Partial<QuoteFormData> | undefined,
  validIncoterms: string[],
): QuoteValidationState => ({
  customer:
    hasText(formData?.customer_id) && hasText(formData?.contact_id),
  route:
    hasText(formData?.mode) &&
    hasText(formData?.service_scope) &&
    hasText(formData?.origin_location_id) &&
    hasText(formData?.destination_location_id) &&
    /^[A-Z]{3}$/.test((formData?.origin_airport || "").trim().toUpperCase()) &&
    /^[A-Z]{3}$/.test((formData?.destination_airport || "").trim().toUpperCase()),
  terms:
    hasText(formData?.payment_term) &&
    hasText(formData?.incoterm) &&
    validIncoterms.includes(formData?.incoterm || ""),
  cargo:
    hasText(formData?.cargo_type) &&
    Array.isArray(formData?.dimensions) &&
    formData.dimensions.length > 0 &&
    formData.dimensions.every((dimension) => (
      isPositiveValue(dimension?.pieces) &&
      isPositiveValue(dimension?.length_cm) &&
      isPositiveValue(dimension?.width_cm) &&
      isPositiveValue(dimension?.height_cm) &&
      isPositiveValue(dimension?.gross_weight_kg) &&
      hasText(dimension?.package_type)
    )),
});

export const calculateCargoMetrics = (
  dimensions: QuoteFormData["dimensions"] | undefined,
) => {
  if (!dimensions || dimensions.length === 0) {
    return { pieces: 0, actualWeight: 0, volumetricWeight: 0, chargeableWeight: 0 };
  }

  let totalPieces = 0;
  let totalActual = 0;
  let totalVolumetric = 0;

  for (const dim of dimensions) {
    const pieces = Number.parseInt(String(dim?.pieces ?? 0), 10) || 0;
    const length = Number.parseFloat(String(dim?.length_cm ?? 0)) || 0;
    const width = Number.parseFloat(String(dim?.width_cm ?? 0)) || 0;
    const height = Number.parseFloat(String(dim?.height_cm ?? 0)) || 0;
    const grossWeight = Number.parseFloat(String(dim?.gross_weight_kg ?? 0)) || 0;

    totalPieces += pieces;
    totalActual += grossWeight * pieces;
    totalVolumetric += (length * width * height / 6000) * pieces;
  }

  const chargeableRaw = Math.max(totalActual, totalVolumetric);

  return {
    pieces: totalPieces,
    actualWeight: Math.round(totalActual * 10) / 10,
    volumetricWeight: Math.round(totalVolumetric * 10) / 10,
    chargeableWeight: chargeableRaw > 0 ? Math.ceil(chargeableRaw) : 0,
  };
};
