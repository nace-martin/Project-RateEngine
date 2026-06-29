/**
 * Commercial Bucket Helpers for SPOT Rate Review
 *
 * These helpers provide a frontend-only commercial grouping layer
 * on top of the backend 3-value bucket enum (airfreight, origin_charges,
 * destination_charges). The reviewed_bucket is NEVER sent to the backend
 * and does NOT alter pricing or component routing.
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export type CommercialBucket =
    | "freight"
    | "origin"
    | "destination"
    | "security"
    | "customs"
    | "transport"
    | "other";

export interface CommercialBucketDef {
    id: CommercialBucket;
    label: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const COMMERCIAL_BUCKETS: CommercialBucketDef[] = [
    { id: "freight", label: "Freight" },
    { id: "origin", label: "Origin Charges" },
    { id: "destination", label: "Destination Charges" },
    { id: "security", label: "Security / Screening" },
    { id: "customs", label: "Customs / Regulatory" },
    { id: "transport", label: "Transport" },
    { id: "other", label: "Other / Manual Review" },
];

export const COMMERCIAL_BUCKET_LABELS: Record<CommercialBucket, string> =
    Object.fromEntries(COMMERCIAL_BUCKETS.map((b) => [b.id, b.label])) as Record<CommercialBucket, string>;

// ─── Heuristic: infer commercial bucket from parser bucket + description ─────

/**
 * Keywords that indicate a charge should be reclassified from "freight"
 * (parser bucket: airfreight) to a more appropriate commercial bucket.
 *
 * IMPORTANT: This is frontend-only display grouping. The backend `bucket`
 * field is NEVER modified by this function.
 */
const ORIGIN_CHARGE_PATTERNS = [
    /\bawb\b/i,
    /\bair\s*waybill\b/i,
    /\bdocument/i,
    /\bhandling\b/i,
    /\bterminal\b/i,
    /\bwarehouse\b/i,
    /\bpalletis/i,
    /\bbreak\s*bulk/i,
    /\bbuild\s*up/i,
    /\bagency\b/i,
    /\blabel/i,
];

const SECURITY_PATTERNS = [
    /\bsecurity\b/i,
    /\bscreen/i,
    /\bx[\s-]?ray/i,
    /\bra\s*3/i,
];

const CUSTOMS_PATTERNS = [
    /\bcustom/i,
    /\bclearance\b/i,
    /\bduty\b/i,
    /\btariff\b/i,
    /\bregulatory\b/i,
    /\bexport\s+declaration/i,
    /\bimport\s+declaration/i,
];

const TRANSPORT_PATTERNS = [
    /\bpickup\b/i,
    /\bdelivery\b/i,
    /\bcollection\b/i,
    /\btransport/i,
    /\btruck/i,
    /\bcartage\b/i,
];

/**
 * Infer the commercial bucket for a charge based on its parser bucket,
 * description, and product code. Falls back to a 1:1 mapping from
 * the parser bucket.
 */
export function inferCommercialBucket(charge: {
    bucket: string;
    description?: string;
    code?: string;
    resolved_product_code?: { code?: string; description?: string } | null;
    effective_resolved_product_code?: { code?: string; description?: string } | null;
}): CommercialBucket {
    const desc = (charge.description || "").trim();
    const productCodeStr = charge.effective_resolved_product_code?.code
        || charge.resolved_product_code?.code
        || charge.code
        || "";
    const searchText = `${desc} ${productCodeStr}`;

    // Only reclassify charges currently in airfreight parser bucket
    if (charge.bucket === "airfreight") {
        if (SECURITY_PATTERNS.some((p) => p.test(searchText))) return "security";
        if (CUSTOMS_PATTERNS.some((p) => p.test(searchText))) return "customs";
        if (TRANSPORT_PATTERNS.some((p) => p.test(searchText))) return "transport";
        if (ORIGIN_CHARGE_PATTERNS.some((p) => p.test(searchText))) return "origin";
        return "freight";
    }

    // For origin/destination parser buckets, check for sub-category matches
    if (charge.bucket === "origin_charges") {
        if (SECURITY_PATTERNS.some((p) => p.test(searchText))) return "security";
        if (CUSTOMS_PATTERNS.some((p) => p.test(searchText))) return "customs";
        if (TRANSPORT_PATTERNS.some((p) => p.test(searchText))) return "transport";
        return "origin";
    }

    if (charge.bucket === "destination_charges") {
        if (SECURITY_PATTERNS.some((p) => p.test(searchText))) return "security";
        if (CUSTOMS_PATTERNS.some((p) => p.test(searchText))) return "customs";
        if (TRANSPORT_PATTERNS.some((p) => p.test(searchText))) return "transport";
        return "destination";
    }

    return "other";
}

// ─── Duplicate detection ─────────────────────────────────────────────────────

/**
 * Returns a Set of field-array indices where the charge description is
 * duplicated within the same quote. Detection is case-insensitive and
 * whitespace-normalized.
 *
 * A charge index is included only if at least one OTHER charge has the
 * same normalized description.
 */
export function getDuplicateChargeIndices(
    charges: Array<{ description?: string }>
): Set<number> {
    const normalized = charges.map((c) =>
        (c.description || "").trim().toUpperCase().replace(/\s+/g, " ")
    );

    // Count occurrences
    const counts = new Map<string, number[]>();
    for (let i = 0; i < normalized.length; i++) {
        const key = normalized[i];
        if (!key) continue;
        const existing = counts.get(key);
        if (existing) {
            existing.push(i);
        } else {
            counts.set(key, [i]);
        }
    }

    const dupeSet = new Set<number>();
    for (const indices of counts.values()) {
        if (indices.length > 1) {
            for (const idx of indices) {
                dupeSet.add(idx);
            }
        }
    }
    return dupeSet;
}
