import { SPEChargeLine, SPEShipmentContext } from "./spot-types";

export interface PreviewChargeLine extends SPEChargeLine {
    calculated_amount?: number;
    display_amount?: string;
    calculation_preview?: string;
    warnings?: string[];
}

export interface RecalculationResult {
    charges: PreviewChargeLine[];
    bucketTotals: Record<string, Record<string, number>>; // bucketId -> currency -> sum
    warnings: string[];
}

/** Normalize basis string to allow flexible matching */
export function normalizeBasisKey(basis: string): string {
    return (basis || "")
        .trim()
        .toLowerCase()
        .replace(/[-]/g, "_");
}

export function recalculateSpotCharges(
    visibleCharges: SPEChargeLine[],
    hiddenCharges: SPEChargeLine[],
    shipment: SPEShipmentContext | null
): RecalculationResult {
    const allCharges: PreviewChargeLine[] = [
        ...hiddenCharges.map(c => ({ ...c })),
        ...visibleCharges.map(c => ({ ...c }))
    ];

    const weight = shipment?.total_weight_kg || 0;

    // Basis totals dictionary: targetKey -> currency -> amount
    const basisTotals: Record<string, Record<string, number>> = {
        freight: {},
        origin: {},
        destination: {},
        total: {}
    };

    // Helper to add to a basis currency total
    const addToBasis = (basisKey: string, currency: string, amount: number) => {
        const normalizedKey = normalizeBasisKey(basisKey);
        if (!basisTotals[normalizedKey]) {
            basisTotals[normalizedKey] = {};
        }
        const cur = currency.toUpperCase();
        basisTotals[normalizedKey][cur] = (basisTotals[normalizedKey][cur] || 0) + amount;
    };

    // PASS 1: Calculate non-percentage charges and accumulate basis totals
    for (const charge of allCharges) {
        const warnings: string[] = [];
        charge.warnings = warnings;
        
        // Exclude unacknowledged conditional charges or explicit exclusions
        const isExcluded = charge.exclude_from_totals || (charge.conditional && !charge.conditional_acknowledged);
        if (isExcluded) {
            charge.calculated_amount = 0;
            charge.display_amount = "0.00";
            charge.calculation_preview = charge.exclude_from_totals ? "Excluded from totals" : "Conditional (Not Acknowledged)";
            continue;
        }

        const unit = (charge.unit || "").trim().toLowerCase();
        if (unit === "percentage" || charge.calculation_type === "percent_of") {
            // Percentage charge is calculated in Pass 2
            continue;
        }

        const rate = parseFloat(charge.amount || "0");
        if (isNaN(rate)) {
            charge.calculated_amount = 0;
            charge.display_amount = "0.00";
            warnings.push("Invalid rate amount");
            continue;
        }

        let calculated = 0;
        let preview = "";

        if (unit === "per_kg") {
            calculated = rate * weight;
            preview = `${rate.toFixed(2)} ${charge.currency}/KG × ${weight} KG`;
        } else if (unit === "min_or_per_kg") {
            const minCharge = parseFloat(String(charge.min_charge || "0"));
            const calculatedPerKg = rate * weight;
            calculated = Math.max(minCharge, calculatedPerKg);
            preview = `Max(${minCharge.toFixed(2)} Min, ${rate.toFixed(2)}/KG × ${weight} KG)`;
        } else if (["flat", "per_awb", "per_shipment", "per_trip", "per_set", "per_man"].includes(unit)) {
            calculated = rate;
            preview = `Flat rate`;
        } else {
            // Unknown or unsupported unit type
            calculated = rate;
            preview = `Flat rate (unknown unit: ${unit})`;
            warnings.push(`Unknown or unsupported unit: ${unit}`);
        }

        charge.calculated_amount = calculated;
        charge.display_amount = calculated.toFixed(2);
        charge.calculation_preview = `${preview} = ${calculated.toFixed(2)} ${charge.currency}`;

        // Accumulate basis totals
        const currency = (charge.currency || "USD").toUpperCase();
        addToBasis("total", currency, calculated);
        
        // Match code-specific basis (case-insensitive normalized)
        if (charge.code) {
            addToBasis(charge.code, currency, calculated);
        }

        const b = (charge.bucket || "").trim().toLowerCase();
        if (b === "airfreight") {
            addToBasis("freight", currency, calculated);
        } else if (b === "origin_charges") {
            addToBasis("origin", currency, calculated);
        } else if (b === "destination_charges") {
            addToBasis("destination", currency, calculated);
        }
    }

    // PASS 2: Calculate percentage charges
    for (const charge of allCharges) {
        const isExcluded = charge.exclude_from_totals || (charge.conditional && !charge.conditional_acknowledged);
        if (isExcluded) continue;

        const unit = (charge.unit || "").trim().toLowerCase();
        if (unit !== "percentage" && charge.calculation_type !== "percent_of") {
            continue;
        }

        const warnings: string[] = [];
        charge.warnings = warnings;

        const percent = parseFloat(String(charge.percent || "0"));
        const basisKey = normalizeBasisKey(charge.percent_basis || "");
        const currency = (charge.currency || "USD").toUpperCase();

        if (isNaN(percent)) {
            charge.calculated_amount = 0;
            charge.display_amount = "0.00";
            warnings.push("Invalid percentage rate");
            continue;
        }

        if (!basisKey) {
            charge.calculated_amount = 0;
            charge.display_amount = "0.00";
            warnings.push("Missing applies-to basis");
            continue;
        }

        // Retrieve base total for matching currency
        const curBases = basisTotals[basisKey] || {};
        const baseAmount = curBases[currency] || 0;

        // Check if there are other currencies in this basis that were ignored
        const otherCurrencies = Object.keys(curBases).filter(c => c !== currency);
        if (otherCurrencies.length > 0) {
            warnings.push(`Mixed currency base ignored: base has values in ${otherCurrencies.join(", ")}`);
        }

        if (baseAmount === 0 && !curBases[currency]) {
            warnings.push(`No matching base charges found for basis '${charge.percent_basis}' in ${currency}`);
        }

        let calculated = baseAmount * (percent / 100);
        let preview = `${percent.toFixed(2)}% of base ${charge.percent_basis} (${baseAmount.toFixed(2)} ${currency})`;

        // Apply min/max caps
        const minVal = charge.min_amount != null ? parseFloat(String(charge.min_amount)) : null;
        const maxVal = charge.max_amount != null ? parseFloat(String(charge.max_amount)) : null;

        if (minVal !== null && !isNaN(minVal) && calculated < minVal) {
            calculated = minVal;
            preview += ` (Floor clamp ${minVal.toFixed(2)} applied)`;
            warnings.push(`Minimum floor clamp applied: ${minVal.toFixed(2)} ${currency}`);
        }
        if (maxVal !== null && !isNaN(maxVal) && calculated > maxVal) {
            calculated = maxVal;
            preview += ` (Cap clamp ${maxVal.toFixed(2)} applied)`;
            warnings.push(`Maximum cap clamp applied: ${maxVal.toFixed(2)} ${currency}`);
        }

        charge.calculated_amount = calculated;
        charge.display_amount = calculated.toFixed(2);
        charge.calculation_preview = `${preview} = ${calculated.toFixed(2)} ${currency}`;

        // Add to total basis so other calculations (or final totals) see it
        addToBasis("total", currency, calculated);
    }

    // Compute Commercial Bucket Totals for display grouping (grouped by bucket -> currency -> sum)
    const bucketTotals: Record<string, Record<string, number>> = {};
    const globalWarnings: string[] = [];

    // Helper to infer bucket if empty or to get reviewed bucket label
    const getReviewedBucket = (c: SPEChargeLine): string => {
        // Return bucket ID from our commercial categories
        if (c.reviewed_bucket) return c.reviewed_bucket;
        
        // Fallback Heuristic
        const codeLower = (c.code || "").toLowerCase();
        const descLower = (c.description || "").toLowerCase();
        
        if (codeLower === "awb" || codeLower === "doc" || descLower.includes("awb") || descLower.includes("documentation") || descLower.includes("document")) {
            return "origin_charges";
        }
        if (c.bucket === "airfreight") return "freight";
        if (c.bucket === "destination_charges") return "destination_charges";
        return "origin_charges";
    };

    for (const charge of allCharges) {
        // Collect warnings
        if (charge.warnings && charge.warnings.length > 0) {
            globalWarnings.push(...charge.warnings.map(w => `${charge.description || charge.code}: ${w}`));
        }

        const isExcluded = charge.exclude_from_totals || (charge.conditional && !charge.conditional_acknowledged);
        if (isExcluded) continue;

        const bucketId = getReviewedBucket(charge);
        const currency = (charge.currency || "USD").toUpperCase();
        const amount = charge.calculated_amount || 0;

        if (!bucketTotals[bucketId]) {
            bucketTotals[bucketId] = {};
        }
        bucketTotals[bucketId][currency] = (bucketTotals[bucketId][currency] || 0) + amount;
    }

    // Only return the visible charges (with recalculated preview info attached) in the original order
    const visibleResultCharges = visibleCharges.map(vc => {
        const match = allCharges.find(ac => ac.id === vc.id || (ac.description === vc.description && ac.code === vc.code && ac.bucket === vc.bucket));
        return {
            ...vc,
            calculated_amount: match?.calculated_amount,
            display_amount: match?.display_amount,
            calculation_preview: match?.calculation_preview,
            warnings: match?.warnings
        };
    });

    return {
        charges: visibleResultCharges,
        bucketTotals,
        warnings: globalWarnings
    };
}
