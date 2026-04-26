"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Combobox } from "@/components/ui/combobox";
import {
    Sheet,
    SheetContent,
    SheetDescription,
    SheetFooter,
    SheetHeader,
    SheetTitle,
} from "@/components/ui/sheet";
import { Alert, AlertDescription } from "@/components/ui/alert";
import type { SPEChargeLine } from "@/lib/spot-types";
import { getProductCodes, type ProductCodeOption } from "@/lib/api";
import { getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";

interface SpotChargeLineManualReviewSheetProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    chargeLine: SPEChargeLine | null;
    productDomain?: string;
    isSaving?: boolean;
    saveError?: string | null;
    onSave: (productCodeId: string) => Promise<void>;
}

const formatProductCode = (productCode?: SPEChargeLine["resolved_product_code"] | null) => {
    if (!productCode) return "None";
    return productCode.description
        ? `${productCode.code} - ${productCode.description}`
        : productCode.code;
};

const humanizeEnum = (value?: string | null) => {
    const normalized = String(value || "").trim();
    if (!normalized) return "Not recorded";
    return normalized
        .split("_")
        .filter(Boolean)
        .map((part) => part.charAt(0) + part.slice(1).toLowerCase())
        .join(" ");
};

export function SpotChargeLineManualReviewSheet({
    open,
    onOpenChange,
    chargeLine,
    productDomain,
    isSaving = false,
    saveError = null,
    onSave,
}: SpotChargeLineManualReviewSheetProps) {
    const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
    const [loadingProducts, setLoadingProducts] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [selectedProductCodeId, setSelectedProductCodeId] = useState<string>("");

    useEffect(() => {
        if (!open || !chargeLine) return;

        const currentManualId = chargeLine.manual_resolved_product_code?.id;
        setSelectedProductCodeId(currentManualId ? String(currentManualId) : "");
    }, [chargeLine, open]);

    useEffect(() => {
        if (!open) return;

        let cancelled = false;
        const loadProductCodes = async () => {
            setLoadingProducts(true);
            setLoadError(null);
            try {
                const data = await getProductCodes(productDomain ? { domain: productDomain } : undefined);
                if (!cancelled) {
                    setProductCodes(data);
                }
            } catch (error) {
                if (!cancelled) {
                    setLoadError(error instanceof Error ? error.message : "Failed to load product codes.");
                }
            } finally {
                if (!cancelled) {
                    setLoadingProducts(false);
                }
            }
        };

        void loadProductCodes();
        return () => {
            cancelled = true;
        };
    }, [open, productDomain]);

    const productOptions = useMemo(
        () =>
            productCodes.map((productCode) => ({
                value: String(productCode.id),
                label: `${productCode.code} - ${productCode.description}`,
            })),
        [productCodes]
    );

    const canSave = Boolean(chargeLine && selectedProductCodeId && !loadingProducts && !isSaving);

    return (
        <Sheet open={open} onOpenChange={onOpenChange}>
            <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-xl">
                <SheetHeader className="space-y-3 border-b border-slate-200 pb-6">
                    <div className="inline-flex w-fit items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-800">
                        <Search className="h-3.5 w-3.5" />
                        Manual charge review
                    </div>
                    <div>
                        <SheetTitle>Resolve this charge line</SheetTitle>
                        <SheetDescription className="mt-2 leading-6">
                            Keep the deterministic audit trail unchanged and attach a manual ProductCode only for this SPOT line.
                        </SheetDescription>
                    </div>
                </SheetHeader>

                {chargeLine ? (
                    <div className="space-y-6 py-6">
                        <section className="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50/70 p-4">
                            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                Current normalization
                            </div>
                            <div className="grid gap-3">
                                <div>
                                    <div className="text-xs font-semibold text-slate-600">Source label</div>
                                    <div className="mt-1 text-sm text-slate-900">
                                        {getSpotChargeDisplayLabel(chargeLine, { includeProductCode: true })}
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs font-semibold text-slate-600">Normalized label</div>
                                    <div className="mt-1 text-sm text-slate-900">{chargeLine.normalized_label || "Not recorded"}</div>
                                </div>
                                <div className="grid gap-3 sm:grid-cols-2">
                                    <div>
                                        <div className="text-xs font-semibold text-slate-600">Deterministic status</div>
                                        <div className="mt-1 text-sm text-slate-900">{chargeLine.normalization_status || "Not recorded"}</div>
                                    </div>
                                    <div>
                                        <div className="text-xs font-semibold text-slate-600">Method</div>
                                        <div className="mt-1 text-sm text-slate-900">{humanizeEnum(chargeLine.normalization_method)}</div>
                                    </div>
                                </div>
                                <div>
                                    <div className="text-xs font-semibold text-slate-600">Deterministic ProductCode</div>
                                    <div className="mt-1 text-sm text-slate-900">{formatProductCode(chargeLine.resolved_product_code)}</div>
                                </div>
                            </div>
                        </section>

                        {chargeLine.manual_resolution_status === "RESOLVED" ? (
                            <section className="rounded-2xl border border-sky-200 bg-sky-50/80 p-4">
                                <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-sky-800">
                                    Existing manual review
                                </div>
                                <div className="mt-3 space-y-2 text-sm text-sky-950">
                                    <div>{formatProductCode(chargeLine.manual_resolved_product_code)}</div>
                                    <div>
                                        Reviewed by {chargeLine.manual_resolution_by_username || "Unknown"} on{" "}
                                        {chargeLine.manual_resolution_at
                                            ? new Date(chargeLine.manual_resolution_at).toLocaleString()
                                            : "Unknown time"}
                                    </div>
                                </div>
                            </section>
                        ) : null}

                        {loadError ? (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription>{loadError}</AlertDescription>
                            </Alert>
                        ) : null}

                        {saveError ? (
                            <Alert variant="destructive">
                                <AlertCircle className="h-4 w-4" />
                                <AlertDescription>{saveError}</AlertDescription>
                            </Alert>
                        ) : null}

                        <section className="space-y-3">
                            <div>
                                <div className="text-sm font-semibold text-slate-950">Select canonical ProductCode</div>
                                <p className="mt-1 text-sm text-slate-600">
                                    Search the current {productDomain || "relevant"} ProductCode list and save the manual mapping for this line only.
                                </p>
                            </div>
                            <Combobox
                                options={productOptions}
                                value={selectedProductCodeId}
                                onChange={setSelectedProductCodeId}
                                placeholder={loadingProducts ? "Loading product codes..." : "Search product codes"}
                                emptyMessage={loadingProducts ? "Loading product codes..." : "No product codes found."}
                                disabled={loadingProducts || isSaving}
                            />
                        </section>
                    </div>
                ) : null}

                <SheetFooter className="border-t border-slate-200 pt-4">
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
                        Cancel
                    </Button>
                    <Button
                        type="button"
                        onClick={() => void onSave(selectedProductCodeId)}
                        disabled={!canSave}
                        loading={isSaving}
                        loadingText="Saving review..."
                    >
                        Save manual resolution
                    </Button>
                </SheetFooter>
            </SheetContent>
        </Sheet>
    );
}
