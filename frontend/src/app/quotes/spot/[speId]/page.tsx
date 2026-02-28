"use client";

/**
 * SPOT Rate Entry Page
 * 
 * Streamlined 3-step flow:
 * 1. Intake (Submit) - Paste agent reply, AI analysis
 * 2. Review (Confirm) - Review assertions, fill missing fields, acknowledge
 * 3. Generate (Finalize) - View computed quote, finalize, generate PDF
 */

import { useState, useEffect, useMemo } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useSpotMode } from "@/hooks/use-spot-mode";
import {
    ExpiredBanner,
    RejectedBanner,
    ReplyPasteCard,
    QuoteVerificationPanel,
} from "@/components/spot";
import { SpotRateEntryForm } from "@/components/spot/SpotRateEntryForm";
import type { SPEChargeLine, SPECommodity } from "@/lib/spot-types";
import type { ReplyAnalysisResult } from "@/lib/spot-types";
import { getSpotStandardCharges } from "@/lib/api";
import {
    Breadcrumb,
    BreadcrumbItem,
    BreadcrumbLink,
    BreadcrumbList,
    BreadcrumbPage,
    BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";

// Streamlined 3-step workflow
type Step = "intake" | "review" | "generate";

const STEPS: { id: Step; label: string; description: string }[] = [
    { id: "intake", label: "1. Submit", description: "Paste agent reply" },
    { id: "review", label: "2. Confirm", description: "Review & acknowledge" },
    { id: "generate", label: "3. Finalize", description: "Generate quote" },
];

const EMPTY_COMPONENTS: string[] = [];
const EMPTY_CHARGES: SPEChargeLine[] = [];

export default function SpotRateEntryPage() {
    const params = useParams();
    const router = useRouter();
    const searchParams = useSearchParams();

    const speId = params.speId as string;
    const isNew = speId === "new";

    // Get shipment context from URL params (for new SPE)
    const originCode = searchParams.get("origin_code") || "";
    const destCode = searchParams.get("dest_code") || "";
    const commodity = (searchParams.get("commodity") || "GCR") as SPECommodity;
    const weight = parseFloat(searchParams.get("weight") || "0");
    const pieces = parseInt(searchParams.get("pieces") || "1");
    const originCountryParam = searchParams.get("origin_country") || "";
    const destCountryParam = searchParams.get("dest_country") || "";
    const triggerCode = searchParams.get("trigger_code") || "";
    const triggerText = searchParams.get("trigger_text") || "";
    const serviceScope = searchParams.get("service_scope") || "";
    const paymentTerm = searchParams.get("payment_term") || "PREPAID";
    const outputCurrency = searchParams.get("output_currency") || "PGK";
    const shipmentTypeParam = searchParams.get("shipment_type") as "EXPORT" | "IMPORT" | "DOMESTIC" | null;

    const { state, actions } = useSpotMode();
    const missingComponentsParam = searchParams.get("missing_components");
    const missingComponentsFromQuery = useMemo(() => {
        if (!missingComponentsParam) return null;
        return missingComponentsParam
            .split(",")
            .map((component) => component.trim())
            .filter(Boolean);
    }, [missingComponentsParam]);
    const missingComponents = useMemo(
        () => missingComponentsFromQuery || state.spe?.shipment.missing_components || EMPTY_COMPONENTS,
        [missingComponentsFromQuery, state.spe?.shipment.missing_components]
    );
    const { loadSPE } = actions;
    const [currentStep, setCurrentStep] = useState<Step>("intake");
    const [showAckModal, setShowAckModal] = useState(false);
    const [analysisResult, setAnalysisResult] = useState<ReplyAnalysisResult | null>(null);
    const [standardPrefillCharges, setStandardPrefillCharges] = useState<SPEChargeLine[]>([]);

    const inferShipmentType = (originCountry?: string, destinationCountry?: string): "EXPORT" | "IMPORT" | "DOMESTIC" => {
        if ((originCountry || "").toUpperCase() === "PG" && (destinationCountry || "").toUpperCase() === "PG") {
            return "DOMESTIC";
        }
        if ((originCountry || "").toUpperCase() === "PG") {
            return "EXPORT";
        }
        return "IMPORT";
    };

    const resolvedShipmentType =
        shipmentTypeParam ||
        (state.spe?.shipment
            ? inferShipmentType(state.spe.shipment.origin_country, state.spe.shipment.destination_country)
            : inferShipmentType(originCountryParam, destCountryParam));

    const formatMissingComponents = (components?: string[]) => {
        if (!components || components.length === 0) return null;
        const friendly = components.map((component) => {
            const normalized = component.toUpperCase();
            if (normalized === "DESTINATION_LOCAL") return "Destination Charges";
            if (normalized === "ORIGIN_LOCAL") return "Origin Charges";
            if (normalized === "FREIGHT") return "Freight Rate";
            return component.replace(/_/g, " ");
        });
        return Array.from(new Set(friendly));
    };

    // Load existing SPE
    useEffect(() => {
        if (speId && !isNew) {
            loadSPE(speId);
        }
    }, [isNew, speId, loadSPE]);

    // Determine current step from SPE state
    useEffect(() => {
        if (state.spe) {
            // Simplified 3-step flow logic
            if (state.flowState === "READY" || state.spe.acknowledgement) {
                setCurrentStep("generate");
            } else if (state.spe.charges.length > 0) {
                // If we have charges, we're in review step
                setCurrentStep(prev => prev === "review" ? prev : "review");
            } else {
                // Initial state - intake
                setCurrentStep("intake");
            }
        }
    }, [state.spe, state.flowState]);

    // Load hybrid standard DB charges (origin/freight/destination where coverage exists)
    useEffect(() => {
        const shipment = state.spe?.shipment;
        if (!shipment || !state.spe?.id) return;

        let cancelled = false;
        const run = async () => {
            try {
                const charges = await getSpotStandardCharges({
                    origin_code: shipment.origin_code,
                    destination_code: shipment.destination_code,
                    direction: resolvedShipmentType,
                    service_scope: shipment.service_scope || serviceScope || "D2D",
                    weight_kg: shipment.total_weight_kg || weight || 100,
                    commodity: shipment.commodity || commodity || "GCR",
                });

                // Only keep standard charges for components that are actually missing (if we know what's missing)
                const filteredCharges = charges.filter(c => {
                    if (missingComponents.length === 0) return true;
                    // c.code is FREIGHT, ORIGIN_LOCAL, DESTINATION_LOCAL
                    return missingComponents.includes(c.code);
                });

                if (!cancelled) {
                    setStandardPrefillCharges(filteredCharges);
                }
            } catch (err) {
                console.error("Failed to load standard SPOT charges:", err);
                if (!cancelled) setStandardPrefillCharges([]);
            }
        };

        run();
        return () => {
            cancelled = true;
        };
    }, [state.spe, serviceScope, weight, commodity, resolvedShipmentType, missingComponents]);

    const mergedFormCharges = useMemo(() => {
        const speCharges = state.spe?.charges || EMPTY_CHARGES;
        if (!standardPrefillCharges.length) return speCharges;

        const seen = new Set(
            speCharges.map(c => `${c.bucket}|${(c.code || "").toUpperCase()}|${(c.description || "").trim().toUpperCase()}`)
        );
        const merged = [...speCharges];
        for (const c of standardPrefillCharges) {
            const key = `${c.bucket}|${(c.code || "").toUpperCase()}|${(c.description || "").trim().toUpperCase()}`;
            if (seen.has(key)) continue;
            merged.push(c);
            seen.add(key);
        }
        return merged;
    }, [state.spe?.charges, standardPrefillCharges]);

    // Handle updating SPE with charges, auto-acknowledge, and auto-compute
    const handleSaveAndAcknowledge = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        if (state.spe) {
            // First update charges
            const spe = await actions.updateSPE(state.spe.id, {
                charges,
                conditions: {
                    space_not_confirmed: true,
                    airline_acceptance_not_confirmed: true,
                    rate_validity_hours: 72,
                    conditional_charges_present: charges.some(c => c.conditional),
                }
            });

            if (spe) {
                // Auto-acknowledge
                const success = await actions.submitAcknowledgement();
                if (success) {
                    // Auto-compute quote immediately (skip intermediate step)
                    setCurrentStep("generate");
                    const resolvedScope = serviceScope || "D2D";
                    const resolvedPaymentTerm = paymentTerm || "PREPAID";
                    const resolvedOutputCurrency = outputCurrency || "PGK";
                    await actions.computeQuote({
                        quote_request: {
                            payment_term: resolvedPaymentTerm,
                            service_scope: resolvedScope,
                            output_currency: resolvedOutputCurrency,
                        },
                    });
                }
            }
        }
    };

    // Handle analysis complete from intake step - move directly to review
    const handleAnalysisComplete = async (result: ReplyAnalysisResult) => {
        setAnalysisResult(result);
        if (speId && !isNew) {
            // Backend persists auto-populated charges (AI + standard DB suggestions) into the SPE.
            // Reload before entering review so the form displays the latest draft charges.
            await loadSPE(speId);
        }
        setCurrentStep("review");
    };

    // Handle compute
    const handleCompute = async () => {
        const resolvedScope = serviceScope || "D2D";
        const resolvedPaymentTerm = paymentTerm || "PREPAID";
        const resolvedOutputCurrency = outputCurrency || "PGK";
        const result = await actions.computeQuote({
            quote_request: {
                payment_term: resolvedPaymentTerm,
                service_scope: resolvedScope,
                output_currency: resolvedOutputCurrency,
            },
        });

        if (result?.is_complete && result.spe_id) {
            // Navigate to quote result
            // For now, we'd need to integrate with actual quote creation
            console.log("SPOT quote computed:", result);
        }
    };

    // Handle create quote from SPE
    const handleCreateQuote = async () => {
        const resolvedScope = serviceScope || "D2D";
        const resolvedPaymentTerm = paymentTerm || "PREPAID";
        const resolvedOutputCurrency = outputCurrency || "PGK";

        const result = await actions.createQuote({
            payment_term: resolvedPaymentTerm,
            service_scope: resolvedScope,
            output_currency: resolvedOutputCurrency,
        });

        if (result?.success && result.quote_id) {
            router.push(`/quotes/${result.quote_id}`);
        }
    };

    // Render step progress - clean, minimal design
    const renderProgress = () => (
        <div className="flex items-center justify-center gap-8 mb-8">
            {STEPS.map((step, index) => {
                const stepIndex = STEPS.findIndex(s => s.id === currentStep);
                const isCompleted = index < stepIndex;
                const isCurrent = step.id === currentStep;

                return (
                    <div key={step.id} className="flex items-center">
                        <div className={`
                            flex items-center justify-center w-8 h-8 rounded-full text-sm font-semibold
                            ${isCompleted ? "bg-emerald-600 text-white" :
                                isCurrent ? "bg-slate-900 text-white" :
                                    "bg-slate-200 text-slate-500"}
                        `}>
                            {isCompleted ? "✓" : index + 1}
                        </div>
                        <span className={`ml-2 text-sm ${isCurrent ? "font-semibold text-slate-900" : "text-slate-500"}`}>
                            {step.label}
                        </span>
                        {index < STEPS.length - 1 && (
                            <div className={`w-16 h-0.5 mx-6 ${isCompleted ? "bg-emerald-600" : "bg-slate-200"}`} />
                        )}
                    </div>
                );
            })}
        </div>
    );

    // Handle flow state banners
    if (state.flowState === "EXPIRED" && state.spe) {
        return (
            <div className="container mx-auto max-w-4xl p-6">
                <ExpiredBanner
                    expiresAt={state.spe.expires_at}
                    onClone={() => router.push("/quotes/new")}
                />
            </div>
        );
    }

    if (state.spe?.status === "rejected") {
        return (
            <div className="container mx-auto max-w-4xl p-6">
                <RejectedBanner
                    comment={state.spe?.manager_approval?.comment}
                    onRevise={() => router.push("/quotes/new")}
                />
            </div>
        );
    }

    return (
        <div className="container mx-auto max-w-5xl space-y-6 p-6">
            {/* Context Header - Clean notification */}
            {isNew && triggerCode && (
                <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
                    <p className="text-sm font-medium text-amber-900">
                        {triggerText || "This shipment requires manual rate sourcing from agents."}
                    </p>
                </div>
            )}

            {/* Header - Clean and minimal */}
            <div className="mb-6 space-y-4">
                <Breadcrumb>
                    <BreadcrumbList>
                        <BreadcrumbItem>
                            <BreadcrumbLink href="/dashboard">Dashboard</BreadcrumbLink>
                        </BreadcrumbItem>
                        <BreadcrumbSeparator />
                        <BreadcrumbItem>
                            <BreadcrumbLink href="/quotes">Quotes</BreadcrumbLink>
                        </BreadcrumbItem>
                        <BreadcrumbSeparator />
                        <BreadcrumbItem>
                            <BreadcrumbPage>{isNew ? "New SPOT" : "SPOT Quote"}</BreadcrumbPage>
                        </BreadcrumbItem>
                    </BreadcrumbList>
                </Breadcrumb>

                <div className="ml-1">
                    <h1 className="text-2xl font-bold text-slate-900">
                        {isNew ? "New SPOT Quote" : "SPOT Quote"}
                    </h1>
                </div>
            </div>

            {/* Progress */}
            {renderProgress()}

            {/* Shipment Summary (Always visible) */}
            <Card className="mb-6">
                <CardHeader className="pb-3">
                    <CardTitle className="text-base font-semibold">Shipment Summary</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-4 gap-6 text-sm">
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Route</span>
                            <span className="font-bold text-slate-900">
                                {originCode || state.spe?.shipment.origin_code} → {destCode || state.spe?.shipment.destination_code}
                            </span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Commodity</span>
                            <span className="font-bold text-slate-900">{commodity || state.spe?.shipment.commodity}</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Weight</span>
                            <span className="font-bold text-slate-900">{weight || state.spe?.shipment.total_weight_kg} kg</span>
                        </div>
                        <div className="flex flex-col gap-1">
                            <span className="text-muted-foreground font-medium">Pieces</span>
                            <span className="font-bold text-slate-900">{pieces || state.spe?.shipment.pieces}</span>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Error display */}
            {state.error && (
                <div className="mb-6 rounded-md border border-red-200 bg-red-50 p-4">
                    <p className="text-sm font-medium text-red-800">{state.error}</p>
                    {state.quoteResult?.has_missing_rates && (
                        <div className="mt-2 text-sm text-red-700">
                            {formatMissingComponents(state.quoteResult.missing_components)?.length ? (
                                <p>
                                    Missing required components:{" "}
                                    <span className="font-semibold">
                                        {formatMissingComponents(state.quoteResult.missing_components)?.join(", ")}
                                    </span>
                                </p>
                            ) : null}
                            {state.quoteResult.completeness_notes && (
                                <p className="mt-1">{state.quoteResult.completeness_notes}</p>
                            )}
                        </div>
                    )}
                </div>
            )}

            {/* Step Content */}

            {/* Step 1: Intake - Paste agent reply, AI analysis */}
            {currentStep === "intake" && (
                <ReplyPasteCard
                    speId={speId as string}
                    missingComponents={missingComponents}
                    onAnalysisComplete={handleAnalysisComplete}
                />
            )}

            {/* Step 2: Review - Rate entry form with AI suggestions, acknowledge */}
            {currentStep === "review" && (
                <div className="space-y-6">
                    {/* Back button */}
                    <Button
                        variant="outline"
                        onClick={() => setCurrentStep("intake")}
                        className="mb-4"
                    >
                        ← Back to Agent Reply
                    </Button>

                    {/* Rate Entry Form with AI-suggested charges */}
                    <SpotRateEntryForm
                        onSubmit={handleSaveAndAcknowledge}
                        isLoading={state.isLoading}
                        initialCharges={mergedFormCharges}
                        suggestedCharges={isNew ? (analysisResult?.assertions || []) : []}
                        shipmentType={resolvedShipmentType}
                        serviceScope={serviceScope}
                        missingComponents={missingComponents}
                    />

                    {/* Acknowledgement checkbox */}
                    <Card>
                        <CardContent className="pt-4">
                            <div className="flex items-center gap-3">
                                <input
                                    type="checkbox"
                                    id="ack-checkbox"
                                    className="h-5 w-5 rounded border-gray-300"
                                    checked={showAckModal}
                                    onChange={(e) => setShowAckModal(e.target.checked)}
                                />
                                <label htmlFor="ack-checkbox" className="text-sm text-muted-foreground">
                                    I acknowledge this is a conditional SPOT quote and rates are not guaranteed until confirmed by carrier.
                                </label>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            )}

            {/* Step 3: Generate - Quote Verification & Finalization */}
            {currentStep === "generate" && (
                <>
                    {!state.quoteResult ? (
                        <div className="max-w-4xl mx-auto py-12 text-center">
                            <p className="text-lg font-semibold text-slate-900 mb-2">Processing Quote</p>
                            <p className="text-slate-500 mb-6">Computing charges and applying rates...</p>
                            <Button
                                onClick={handleCompute}
                                disabled={state.isLoading}
                                className="bg-slate-900 hover:bg-slate-800"
                                size="lg"
                            >
                                {state.isLoading ? "Computing..." : "Generate Quote"}
                            </Button>
                        </div>
                    ) : (
                        <div className="space-y-4">
                            <QuoteVerificationPanel
                                rawText={analysisResult?.raw_text || ""}
                                extractedCharges={analysisResult?.assertions}
                                initialCharges={state.spe?.charges || []}
                                onSubmit={handleSaveAndAcknowledge}
                                isLoading={state.isLoading}
                                shipmentType={resolvedShipmentType}
                                serviceScope={serviceScope}
                            />
                            <div className="flex justify-end gap-3">
                                <Button
                                    variant="outline"
                                    onClick={() => router.push("/quotes")}
                                    disabled={state.isLoading}
                                >
                                    Save Draft
                                </Button>
                                <Button
                                    onClick={handleCreateQuote}
                                    disabled={state.isLoading}
                                    className="bg-slate-900 hover:bg-slate-800"
                                >
                                    Create Quote
                                </Button>
                            </div>
                        </div>
                    )}
                </>
            )
            }
        </div >
    );
}
