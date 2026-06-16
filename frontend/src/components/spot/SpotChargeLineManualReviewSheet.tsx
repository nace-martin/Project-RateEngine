"use client";

import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Search } from "lucide-react";
import Link from "next/link";
import { usePermissions } from "@/hooks/usePermissions";

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
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import type { SPEChargeLine } from "@/lib/spot-types";
import { getProductCodes, type ProductCodeOption, createProductCodeRequest } from "@/lib/api";
import { getSpotChargeDisplayLabel } from "@/lib/spot-charge-display";
import { humanizeEnum } from "@/lib/spot-workspace-helpers";

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



export function SpotChargeLineManualReviewSheet({
    open,
    onOpenChange,
    chargeLine,
    productDomain,
    isSaving = false,
    saveError = null,
    onSave,
}: SpotChargeLineManualReviewSheetProps) {
    const { isAdmin } = usePermissions();

    const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
    const [loadingProducts, setLoadingProducts] = useState(false);
    const [loadError, setLoadError] = useState<string | null>(null);
    const [selectedProductCodeId, setSelectedProductCodeId] = useState<string>("");

    // Request new ProductCode state
    const [showRequestForm, setShowRequestForm] = useState(false);
    const [requestSourceLabel, setRequestSourceLabel] = useState("");
    const [requestSuggestedName, setRequestSuggestedName] = useState("");
    const [requestSuggestedBucket, setRequestSuggestedBucket] = useState("HANDLING");
    const [requestSuggestedBasis, setRequestSuggestedBasis] = useState("SHIPMENT");
    const [requestSuggestedReason, setRequestSuggestedReason] = useState("");
    const [isSubmittingRequest, setIsSubmittingRequest] = useState(false);
    const [requestSuccessMessage, setRequestSuccessMessage] = useState<string | null>(null);
    const [requestErrorMessage, setRequestErrorMessage] = useState<string | null>(null);
    const [requestSubmitted, setRequestSubmitted] = useState(false);
    const [showSelectorAfterSubmit, setShowSelectorAfterSubmit] = useState(false);

    useEffect(() => {
        if (!open || !chargeLine) {
            setSelectedProductCodeId("");
            setShowRequestForm(false);
            setRequestSuccessMessage(null);
            setRequestErrorMessage(null);
            setRequestSubmitted(false);
            setShowSelectorAfterSubmit(false);
            return;
        }

        const currentManualId = chargeLine.manual_resolved_product_code?.id;
        setSelectedProductCodeId(currentManualId ? String(currentManualId) : "");

        const sourceLabelText = chargeLine.normalized_label || chargeLine.description || "";
        setRequestSourceLabel(sourceLabelText);
        setRequestSuggestedName(chargeLine.description || "");
        
        if (chargeLine.bucket === "airfreight") {
            setRequestSuggestedBucket("FREIGHT");
        } else {
            setRequestSuggestedBucket("HANDLING");
        }

        if (chargeLine.unit === "per_kg") {
            setRequestSuggestedBasis("KG");
        } else if (chargeLine.unit === "percentage") {
            setRequestSuggestedBasis("PERCENT");
        } else {
            setRequestSuggestedBasis("SHIPMENT");
        }

        setRequestSuggestedReason("Requested from SPOT review UI");
        setRequestSuccessMessage(null);
        setRequestErrorMessage(null);
        setRequestSubmitted(false);
        setShowRequestForm(false);
        setShowSelectorAfterSubmit(false);
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

    const handleSubmitRequest = async () => {
        setIsSubmittingRequest(true);
        setRequestErrorMessage(null);
        setRequestSuccessMessage(null);
        try {
            const res = await createProductCodeRequest({
                source_label: requestSourceLabel,
                suggested_name: requestSuggestedName,
                suggested_bucket: requestSuggestedBucket,
                suggested_basis: requestSuggestedBasis,
                suggested_reason: requestSuggestedReason,
            });

            if (res.duplicate_reused) {
                setRequestSuccessMessage(`Existing pending ProductCode request found.|Request ID: ${res.id}`);
            } else {
                setRequestSuccessMessage(`ProductCode request submitted successfully.|Request ID: ${res.id}`);
            }
            setRequestSubmitted(true);
            setShowRequestForm(false);
            setShowSelectorAfterSubmit(false);
        } catch (error) {
            setRequestErrorMessage(error instanceof Error ? error.message : "Failed to create product code request");
        } finally {
            setIsSubmittingRequest(false);
        }
    };

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
                        <SheetTitle>
                            {requestSubmitted ? "ProductCode request pending review" : "Resolve this charge line"}
                        </SheetTitle>
                        <SheetDescription className="mt-2 leading-6">
                            {requestSubmitted
                                ? "This charge cannot be resolved until the requested ProductCode is approved or linked by an admin."
                                : "Keep the deterministic audit trail unchanged and attach a manual ProductCode only for this SPOT line."}
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

                        {(!requestSubmitted || showSelectorAfterSubmit) && (
                            <section className="space-y-3">
                                <div>
                                    <div className="text-sm font-semibold text-slate-950">Select canonical ProductCode</div>
                                    <p className="mt-1 text-sm text-slate-600">
                                        Search the current {productDomain || "relevant"} ProductCode list and save the manual mapping for this line only. Manual resolution requires selecting an existing ProductCode.
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
                        )}

                        {requestSubmitted && requestSuccessMessage ? (
                            <div className="space-y-4">
                                <div className="rounded-2xl border border-amber-200 bg-amber-50/50 p-4 text-sm text-slate-800 space-y-2">
                                    <div className="flex flex-col gap-1">
                                        <p className="font-semibold text-emerald-800">
                                            {requestSuccessMessage.split('|')[0]}
                                        </p>
                                        <p className="text-xs font-mono font-semibold text-slate-700">
                                            {requestSuccessMessage.split('|')[1]}
                                        </p>
                                    </div>
                                    <div className="border-t border-amber-200/50 pt-2 space-y-1">
                                        <p className="font-medium text-slate-900">This charge is not resolved yet.</p>
                                        <p className="text-xs text-slate-600">
                                            An admin must review it in Settings → ProductCode Requests.
                                        </p>
                                    </div>
                                </div>

                                {!showSelectorAfterSubmit && (
                                    <div className="space-y-2">
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            className="w-full text-slate-700 hover:text-slate-900"
                                            onClick={() => setShowSelectorAfterSubmit(true)}
                                        >
                                            Resolve now with an existing ProductCode instead
                                        </Button>

                                        {isAdmin && (
                                            <Button
                                                type="button"
                                                variant="outline"
                                                size="sm"
                                                className="w-full text-emerald-700 hover:text-emerald-800 hover:bg-emerald-50 border-emerald-200"
                                                asChild
                                            >
                                                <Link href="/settings/product-code-requests" onClick={() => onOpenChange(false)}>
                                                    Go to Settings → ProductCode Requests
                                                </Link>
                                            </Button>
                                        )}
                                    </div>
                                )}
                            </div>
                        ) : (
                            <>
                                {requestErrorMessage ? (
                                    <Alert variant="destructive">
                                        <AlertCircle className="h-4 w-4" />
                                        <AlertDescription>{requestErrorMessage}</AlertDescription>
                                    </Alert>
                                ) : null}

                                {!showRequestForm ? (
                                    <div className="pt-2">
                                        <Button
                                            type="button"
                                            variant="outline"
                                            size="sm"
                                            className="w-full text-slate-700 hover:text-slate-900"
                                            onClick={() => setShowRequestForm(true)}
                                            disabled={loadingProducts || isSaving}
                                        >
                                            Can&apos;t find a matching product code? Create ProductCode Request
                                        </Button>
                                    </div>
                                ) : (
                                    <section className="space-y-4 rounded-2xl border border-slate-200 bg-slate-50/50 p-4">
                                        <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">
                                            Request New ProductCode
                                        </div>
                                        <div className="space-y-3">
                                            <div className="grid gap-1.5">
                                                <Label htmlFor="req-source-label" className="text-xs font-semibold text-slate-600">Source Label</Label>
                                                <Input
                                                    id="req-source-label"
                                                    value={requestSourceLabel}
                                                    onChange={(e) => setRequestSourceLabel(e.target.value)}
                                                    placeholder="e.g. Local Handling Fee"
                                                    className="bg-white"
                                                />
                                            </div>
                                            <div className="grid gap-1.5">
                                                <Label htmlFor="req-suggested-name" className="text-xs font-semibold text-slate-600">Suggested Name</Label>
                                                <Input
                                                    id="req-suggested-name"
                                                    value={requestSuggestedName}
                                                    onChange={(e) => setRequestSuggestedName(e.target.value)}
                                                    placeholder="e.g. Local Handling"
                                                    className="bg-white"
                                                />
                                            </div>
                                            <div className="grid gap-3 sm:grid-cols-2">
                                                <div className="grid gap-1.5">
                                                    <Label htmlFor="req-bucket" className="text-xs font-semibold text-slate-600">Category Bucket</Label>
                                                    <select
                                                        id="req-bucket"
                                                        value={requestSuggestedBucket}
                                                        onChange={(e) => setRequestSuggestedBucket(e.target.value)}
                                                        className="flex h-10 w-full rounded-md border border-input bg-white px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                                    >
                                                        <option value="FREIGHT">Freight</option>
                                                        <option value="HANDLING">Handling & Terminal</option>
                                                        <option value="CLEARANCE">Customs Clearance</option>
                                                        <option value="DOCUMENTATION">Documentation</option>
                                                        <option value="REGULATORY">Regulatory / Permit</option>
                                                        <option value="CARTAGE">Pickup & Delivery</option>
                                                        <option value="AGENCY">Agency Fees</option>
                                                        <option value="SCREENING">Security & Screening</option>
                                                        <option value="SURCHARGE">Surcharges</option>
                                                    </select>
                                                </div>
                                                <div className="grid gap-1.5">
                                                    <Label htmlFor="req-basis" className="text-xs font-semibold text-slate-600">Charge Basis</Label>
                                                    <select
                                                        id="req-basis"
                                                        value={requestSuggestedBasis}
                                                        onChange={(e) => setRequestSuggestedBasis(e.target.value)}
                                                        className="flex h-10 w-full rounded-md border border-input bg-white px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
                                                    >
                                                        <option value="SHIPMENT">Per Shipment</option>
                                                        <option value="KG">Per Kilogram</option>
                                                        <option value="PERCENT">Percentage</option>
                                                    </select>
                                                </div>
                                            </div>
                                            <div className="grid gap-1.5">
                                                <Label htmlFor="req-reason" className="text-xs font-semibold text-slate-600">Reason / Context</Label>
                                                <Textarea
                                                    id="req-reason"
                                                    value={requestSuggestedReason}
                                                    onChange={(e) => setRequestSuggestedReason(e.target.value)}
                                                    placeholder="Reason for requesting this product code..."
                                                    className="min-h-[60px] bg-white"
                                                />
                                            </div>
                                            <div className="flex gap-2 pt-2">
                                                <Button
                                                    type="button"
                                                    variant="outline"
                                                    size="sm"
                                                    onClick={() => setShowRequestForm(false)}
                                                    disabled={isSubmittingRequest}
                                                >
                                                    Cancel
                                                </Button>
                                                <Button
                                                    type="button"
                                                    size="sm"
                                                    onClick={handleSubmitRequest}
                                                    loading={isSubmittingRequest}
                                                    loadingText="Submitting..."
                                                    disabled={!requestSourceLabel.trim() || !requestSuggestedName.trim()}
                                                >
                                                    Submit Request
                                                </Button>
                                            </div>
                                        </div>
                                    </section>
                                )}
                            </>
                        )}
                    </div>
                ) : null}

                <SheetFooter className="border-t border-slate-200 pt-4">
                    <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={isSaving}>
                        {requestSubmitted ? "Close" : "Cancel"}
                    </Button>
                    {(!requestSubmitted || showSelectorAfterSubmit) && (
                        <Button
                            type="button"
                            onClick={() => void onSave(selectedProductCodeId)}
                            disabled={!canSave}
                            loading={isSaving}
                            loadingText="Saving review..."
                        >
                            Save manual resolution
                        </Button>
                    )}
                </SheetFooter>
            </SheetContent>
        </Sheet>
    );
}
