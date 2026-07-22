import type { DraftCharge, DraftQuote, TotalsValidation } from "./draft-quote-types";

class DraftQuoteNumericNormalizationError extends Error {
    constructor(message: string) {
        super(message);
        this.name = "DraftQuoteNumericNormalizationError";
    }
}

function isEmptyOptionalValue(value: unknown): boolean {
    return value === null || value === undefined || (typeof value === "string" && value.trim() === "");
}

function parseFiniteNumber(value: unknown, fieldPath: string): number {
    const numericValue = typeof value === "number" ? value : Number(String(value).trim());
    if (!Number.isFinite(numericValue)) {
        throw new DraftQuoteNumericNormalizationError(`Invalid numeric value for ${fieldPath}.`);
    }
    return numericValue;
}

function normalizeOptionalFiniteNumber(value: unknown, fieldPath: string): number | null {
    if (isEmptyOptionalValue(value)) return null;
    return parseFiniteNumber(value, fieldPath);
}

function normalizeRequiredFiniteNumber(value: unknown, fieldPath: string): number {
    if (isEmptyOptionalValue(value)) {
        throw new DraftQuoteNumericNormalizationError(`Missing required numeric value for ${fieldPath}.`);
    }
    return parseFiniteNumber(value, fieldPath);
}

function normalizeDraftCharge(charge: DraftCharge, index: number): DraftCharge {
    const fieldPrefix = `suggested_charges[${index}]`;
    return {
        ...charge,
        amount: normalizeRequiredFiniteNumber(charge.amount, `${fieldPrefix}.amount`),
        rate: normalizeOptionalFiniteNumber(charge.rate, `${fieldPrefix}.rate`),
        minimum_charge: normalizeOptionalFiniteNumber(charge.minimum_charge, `${fieldPrefix}.minimum_charge`),
        quantity: normalizeOptionalFiniteNumber(charge.quantity, `${fieldPrefix}.quantity`),
    };
}

function normalizeTotalsValidation(totalsValidation: TotalsValidation): TotalsValidation {
    return {
        ...totalsValidation,
        extracted_total: normalizeOptionalFiniteNumber(totalsValidation.extracted_total, "totals_validation.extracted_total"),
        calculated_total: normalizeOptionalFiniteNumber(totalsValidation.calculated_total, "totals_validation.calculated_total"),
        difference: normalizeOptionalFiniteNumber(totalsValidation.difference, "totals_validation.difference"),
        tolerance: normalizeRequiredFiniteNumber(totalsValidation.tolerance, "totals_validation.tolerance"),
    };
}

export function normalizeDraftQuotePayload(payload: DraftQuote): DraftQuote {
    return {
        ...payload,
        suggested_charges: (payload.suggested_charges || []).map(normalizeDraftCharge),
        totals_validation: normalizeTotalsValidation(payload.totals_validation),
    };
}
