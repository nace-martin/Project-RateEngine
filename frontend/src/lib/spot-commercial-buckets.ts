/**
 * Commercial Bucket Helpers for SPOT Rate Review
 *
 * These helpers provide a frontend-only commercial grouping layer
 * on top of the backend 3-value bucket enum (airfreight, origin_charges,
 * destination_charges). The reviewed_bucket is NEVER sent to the backend
 * and does NOT alter pricing or component routing.
 */

import type { SPEChargeBucket } from "./spot-types";

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
    /\bdoc\b/i,
    /\bdox\b/i,
    /\borigin\b/i,
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

/**
 * Dynamically filter COMMERCIAL_BUCKETS based on shipment context
 * and current charges to prevent global bucket exposure.
 */
export function getVisibleCommercialBuckets(options: {
    missingComponents?: string[];
    serviceScope?: string;
    shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
    charges?: Array<{
        bucket?: string;
        description?: string;
        reviewed_bucket?: string | null;
        code?: string;
        resolved_product_code?: { code?: string; description?: string } | null;
        effective_resolved_product_code?: { code?: string; description?: string } | null;
    }>;
}): CommercialBucketDef[] {
    const missing = (options.missingComponents || []).map(c => c.toUpperCase());
    const scope = (options.serviceScope || "D2D").toUpperCase();
    const type = options.shipmentType || "EXPORT";
    const charges = options.charges || [];

    // 1. Map missing components or required components to backend buckets
    const missingBuckets = missing.length > 0
        ? missing.map(c => {
            if (c === "FREIGHT") return "airfreight" as SPEChargeBucket;
            if (c === "ORIGIN_LOCAL") return "origin_charges" as SPEChargeBucket;
            if (c === "DESTINATION_LOCAL") return "destination_charges" as SPEChargeBucket;
            return null;
        }).filter((b): b is SPEChargeBucket => b !== null)
        : [];

    const requiredComponents = type === "DOMESTIC"
        ? ["FREIGHT"]
        : scope === "A2A"
            ? ["FREIGHT"]
            : scope === "D2A"
                ? ["ORIGIN_LOCAL", "FREIGHT"]
                : scope === "A2D"
                    ? ["DESTINATION_LOCAL"]
                    : ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"];

    const requiredBuckets = requiredComponents.map(c => {
        if (c === "FREIGHT") return "airfreight" as SPEChargeBucket;
        if (c === "ORIGIN_LOCAL") return "origin_charges" as SPEChargeBucket;
        if (c === "DESTINATION_LOCAL") return "destination_charges" as SPEChargeBucket;
        return null;
    }).filter((b): b is SPEChargeBucket => b !== null);

    const activeBackendBuckets = new Set<string>();
    if (missing.length > 0) {
        missingBuckets.forEach(b => activeBackendBuckets.add(b));
    } else {
        requiredBuckets.forEach(b => activeBackendBuckets.add(b));
    }
    // Always include any backend bucket present in charges
    charges.forEach(c => {
        if (c.bucket) activeBackendBuckets.add(c.bucket);
    });

    // 2. Base commercial bucket mapping
    const allowedCommercial = new Set<CommercialBucket>();
    if (activeBackendBuckets.has("airfreight")) {
        allowedCommercial.add("freight");
    }
    if (activeBackendBuckets.has("origin_charges")) {
        allowedCommercial.add("origin");
    }
    if (activeBackendBuckets.has("destination_charges")) {
        allowedCommercial.add("destination");
    }

    // 3. Collect buckets that have at least one charge assigned/inferred
    const assignedBuckets = new Set<string>();
    charges.forEach(c => {
        const normalizedCharge = {
            bucket: c.bucket || "",
            description: c.description || "",
            code: c.code || "",
            resolved_product_code: c.resolved_product_code || null,
            effective_resolved_product_code: c.effective_resolved_product_code || null,
        };
        const rb = c.reviewed_bucket || inferCommercialBucket(normalizedCharge);
        if (rb) {
            assignedBuckets.add(rb);
        }
    });

    // 4. Filter: core buckets (freight/origin/destination) are visible when
    //    in scope OR assigned. Sub-buckets (security/customs/transport/other)
    //    are visible ONLY when a charge is already assigned/inferred to them.
    return COMMERCIAL_BUCKETS.filter(cb => {
        switch (cb.id) {
            case "freight":
                return allowedCommercial.has("freight") || assignedBuckets.has("freight");
            case "origin":
                return allowedCommercial.has("origin") || assignedBuckets.has("origin");
            case "destination":
                return allowedCommercial.has("destination") || assignedBuckets.has("destination");
            case "security":
            case "customs":
            case "transport":
            case "other":
                // Only visible if at least one charge is assigned/inferred to this bucket
                return assignedBuckets.has(cb.id);
            default:
                return false;
        }
    });
}

// ─── Core bucket IDs (always offered in dropdowns when in scope) ─────────────

const CORE_BUCKET_IDS: Set<CommercialBucket> = new Set(["freight", "origin", "destination"]);

// ─── Per-charge dropdown options ─────────────────────────────────────────────

/**
 * Returns the dropdown options for a single charge row's Reviewed Bucket
 * select. Unlike the global getVisibleCommercialBuckets, this is scoped to
 * the individual charge so that one customs charge does not leak "Customs"
 * into every other row's dropdown.
 *
 * Rules:
 * 1. Always include the charge's current selected/inferred bucket.
 * 2. Include core buckets (freight/origin/destination) when in scope.
 * 3. Include security/customs/transport/other ONLY if THIS charge is
 *    already assigned/inferred to that bucket.
 */
export function getDropdownBucketOptionsForCharge(
    charge: {
        bucket?: string;
        description?: string;
        reviewed_bucket?: string | null;
        code?: string;
        resolved_product_code?: { code?: string; description?: string } | null;
        effective_resolved_product_code?: { code?: string; description?: string } | null;
    },
    context: {
        missingComponents?: string[];
        serviceScope?: string;
        shipmentType?: "EXPORT" | "IMPORT" | "DOMESTIC";
    }
): CommercialBucketDef[] {
    const scope = (context.serviceScope || "D2D").toUpperCase();
    const type = context.shipmentType || "EXPORT";
    const missing = (context.missingComponents || []).map(c => c.toUpperCase());

    // Determine which core backend buckets are in scope
    const requiredComponents = missing.length > 0
        ? missing
        : type === "DOMESTIC"
            ? ["FREIGHT"]
            : scope === "A2A"
                ? ["FREIGHT"]
                : scope === "D2A"
                    ? ["ORIGIN_LOCAL", "FREIGHT"]
                    : scope === "A2D"
                        ? ["DESTINATION_LOCAL"]
                        : ["ORIGIN_LOCAL", "FREIGHT", "DESTINATION_LOCAL"];

    const inScopeCommercial = new Set<CommercialBucket>();
    for (const comp of requiredComponents) {
        if (comp === "FREIGHT") inScopeCommercial.add("freight");
        if (comp === "ORIGIN_LOCAL") inScopeCommercial.add("origin");
        if (comp === "DESTINATION_LOCAL") inScopeCommercial.add("destination");
    }

    // Infer this charge's bucket
    const normalizedCharge = {
        bucket: charge.bucket || "",
        description: charge.description || "",
        code: charge.code || "",
        resolved_product_code: charge.resolved_product_code || null,
        effective_resolved_product_code: charge.effective_resolved_product_code || null,
    };
    const currentBucket: CommercialBucket = (charge.reviewed_bucket as CommercialBucket) || inferCommercialBucket(normalizedCharge);

    // Build the allowed set
    const allowed = new Set<CommercialBucket>();

    // Always include current bucket
    allowed.add(currentBucket);

    // Include in-scope core buckets
    for (const cb of inScopeCommercial) {
        allowed.add(cb);
    }

    // Include core buckets from the charge's own backend bucket
    if (charge.bucket === "airfreight") allowed.add("freight");
    if (charge.bucket === "origin_charges") allowed.add("origin");
    if (charge.bucket === "destination_charges") allowed.add("destination");

    // Sub-buckets only if THIS charge is assigned to them (already handled
    // by including currentBucket above — no extra logic needed)

    return COMMERCIAL_BUCKETS.filter(cb => allowed.has(cb.id));
}

/**
 * Returns true if a commercial bucket is a "core" bucket that may show
 * as an empty section (add target) when required by the shipment scope.
 */
export function isCoreCommercialBucket(bucketId: CommercialBucket): boolean {
    return CORE_BUCKET_IDS.has(bucketId);
}
