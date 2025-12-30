"use client";

/**
 * SPOT Rate Entry Page
 * 
 * Multi-step flow:
 * 1. Enter charge lines (airfreight, origin, destination)
 * 2. Sales acknowledgement
 * 3. Manager approval (if required)
 * 4. Compute SPOT quote
 */

import { useState, useEffect } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { ArrowLeft, Package, CheckCircle2, Clock, AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { useSpotMode } from "@/hooks/use-spot-mode";
import {
    SpotAcknowledgementModal,
    SpotManagerApproval,
    AwaitingManagerBanner,
    ExpiredBanner,
    RejectedBanner,
    ReplyPasteCard,
    AssertionReviewCard
} from "@/components/spot";
import { SpotRateEntryForm } from "@/components/spot/SpotRateEntryForm";
import type { SPEChargeLine, CreateSPERequest, SPEShipmentContext, SPECommodity } from "@/lib/spot-types";
import type { ReplyAnalysisResult } from "@/lib/spot-types";

// Progress steps
type Step = "intake" | "analysis" | "entry" | "acknowledge" | "approval" | "compute";

const STEPS: { id: Step; label: string }[] = [
    { id: "intake", label: "Intake" },
    { id: "analysis", label: "Analysis" },
    { id: "entry", label: "Entry" },
    { id: "acknowledge", label: "Acknowledge" },
    { id: "approval", label: "Approval" },
    { id: "compute", label: "Compute" },
];

export default function SpotRateEntryPage() {
    const params = useParams();
    const router = useRouter();
    const searchParams = useSearchParams();

    const speId = params.speId as string;
    const isNew = speId === "new";

    // Get shipment context from URL params (for new SPE)
    const originCountry = searchParams.get("origin_country") || "";
    const destCountry = searchParams.get("dest_country") || "";
    const originCode = searchParams.get("origin_code") || "";
    const destCode = searchParams.get("dest_code") || "";
    const commodity = (searchParams.get("commodity") || "GCR") as SPECommodity;
    const weight = parseFloat(searchParams.get("weight") || "0");
    const pieces = parseInt(searchParams.get("pieces") || "1");
    const triggerCode = searchParams.get("trigger_code") || "";
    const triggerText = searchParams.get("trigger_text") || "";
    const serviceScope = searchParams.get("service_scope") || "";
    const paymentTerm = searchParams.get("payment_term") || "PREPAID";
    const outputCurrency = searchParams.get("output_currency") || "PGK";
    const shipmentType = (searchParams.get("shipment_type") || "EXPORT") as "EXPORT" | "IMPORT" | "DOMESTIC";
    const missingComponents = searchParams.get("missing_components")?.split(",") || [];

    const { state, actions, derived } = useSpotMode();
    const { loadSPE } = actions;
    const [currentStep, setCurrentStep] = useState<Step>("intake");
    const [showAckModal, setShowAckModal] = useState(false);
    const [chargeLines, setChargeLines] = useState<Omit<SPEChargeLine, 'id'>[]>([]);
    const [analysisResult, setAnalysisResult] = useState<ReplyAnalysisResult | null>(null);

    // Load existing SPE
    useEffect(() => {
        if (speId && !isNew) {
            loadSPE(speId);
        }
    }, [isNew, speId, loadSPE]);

    // Determine current step from SPE state
    useEffect(() => {
        if (state.spe) {
            // Only auto-advance if we're not in a manual transition step (like analysis)
            // or if the backend state is significantly further ahead.
            if (state.flowState === "READY") {
                setCurrentStep("compute");
            } else if (state.flowState === "AWAITING_MANAGER") {
                setCurrentStep("approval");
            } else if (state.spe.acknowledgement) {
                setCurrentStep("approval");
            } else if (state.spe.charges.length > 0) {
                // If we have charges, we should at least be in Entry
                // But don't override analysis/acknowledge if we just finished them
                setCurrentStep(prev => {
                    if (prev === "acknowledge" || prev === "compute") return prev;
                    return "entry";
                });
            } else {
                // Initial state
                setCurrentStep(prev => (prev === "analysis" ? prev : "intake"));
            }
        }
    }, [state.spe, state.flowState]);

    // Handle updating SPE with charges
    const handleUpdateSPE = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        setChargeLines(charges);

        if (state.spe) {
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
                setCurrentStep("acknowledge");
            }
        }
    };

    // Handle analysis complete from intake step
    const handleAnalysisComplete = (result: ReplyAnalysisResult) => {
        setAnalysisResult(result);
        setCurrentStep("analysis");
    };

    // Handle assertion confirmation from analysis step
    const handleAssertionConfirm = (updatedResult: ReplyAnalysisResult) => {
        setAnalysisResult(updatedResult);
        setCurrentStep("entry");
    };

    // Handle acknowledgement
    const handleAcknowledge = async () => {
        const success = await actions.submitAcknowledgement();
        if (success) {
            setShowAckModal(false);
            if (state.spe?.requires_manager_approval) {
                setCurrentStep("approval");
            } else {
                setCurrentStep("compute");
            }
        }
    };

    // Handle manager approval
    const handleApproval = async (approved: boolean, comment?: string) => {
        await actions.submitManagerApproval(approved, comment);
        if (approved) {
            setCurrentStep("compute");
        }
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

    // Render step progress
    const renderProgress = () => (
        <div className="flex items-center justify-between mb-8">
            {STEPS.map((step, index) => {
                const stepIndex = STEPS.findIndex(s => s.id === currentStep);
                const isCompleted = index < stepIndex;
                const isCurrent = step.id === currentStep;

                return (
                    <div key={step.id} className="flex items-center">
                        <div className={`
              flex items-center justify-center w-8 h-8 rounded-full text-sm font-medium
              ${isCompleted ? "bg-green-500 text-white" :
                                isCurrent ? "bg-primary text-primary-foreground" :
                                    "bg-muted text-muted-foreground"}
            `}>
                            {isCompleted ? <CheckCircle2 className="h-5 w-5" /> : index + 1}
                        </div>
                        <span className={`ml-2 text-sm ${isCurrent ? "font-medium" : "text-muted-foreground"}`}>
                            {step.label}
                        </span>
                        {index < STEPS.length - 1 && (
                            <div className={`w-12 h-0.5 mx-4 ${isCompleted ? "bg-green-500" : "bg-muted"}`} />
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

    if (state.flowState === "REJECTED" && state.spe) {
        return (
            <div className="container mx-auto max-w-4xl p-6">
                <RejectedBanner
                    comment={state.spe.manager_approval?.comment}
                    onRevise={() => router.push("/quotes/new")}
                />
            </div>
        );
    }

    return (
        <div className="container mx-auto max-w-5xl space-y-6 p-6">
            {/* Context Header */}
            {isNew && triggerCode && (
                <div className="flex flex-col gap-2 rounded-lg border border-amber-200 bg-amber-50 p-4 shadow-sm">
                    <div className="flex items-center gap-2">
                        <Badge variant="outline" className="border-amber-500 bg-amber-100 text-amber-700">
                            SPOT Quote Required
                        </Badge>
                        <Badge variant="secondary" className="font-mono text-xs">
                            {triggerCode}
                        </Badge>
                    </div>
                    <p className="text-sm font-medium text-amber-900">
                        {triggerText || "This shipment requires manual rate sourcing."}
                    </p>
                </div>
            )}

            {/* Header */}
            <div className="flex items-center gap-4 mb-6">
                <Button variant="ghost" size="icon" onClick={() => router.back()}>
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Package className="h-6 w-6 text-amber-600" />
                        {isNew ? "SPOT Rate Request" : "SPOT Pricing"}
                    </h1>
                    <p className="text-muted-foreground">
                        {isNew ? "Solicit and process manual rates" : `SPE: ${speId.slice(0, 8)}...`}
                    </p>
                </div>
                <Badge variant="outline" className="ml-auto text-amber-600 border-amber-400">
                    {triggerCode || state.spe?.spot_trigger_reason_code || "SPOT"}
                </Badge>
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
                <Card className="mb-6 border-red-200 bg-red-50">
                    <CardContent className="pt-4">
                        <div className="flex items-start gap-2 text-red-700">
                            <AlertTriangle className="h-5 w-5 mt-0.5" />
                            <p>{state.error}</p>
                        </div>
                    </CardContent>
                </Card>
            )}

            {/* Step Content */}

            {currentStep === "intake" && (
                <ReplyPasteCard
                    speId={speId as string}
                    missingComponents={missingComponents}
                    onAnalysisComplete={(result) => {
                        setAnalysisResult(result);
                        setCurrentStep("analysis");
                    }}
                />
            )}

            {currentStep === "analysis" && analysisResult && (
                <AssertionReviewCard
                    result={analysisResult}
                    onConfirm={(refinedResult) => {
                        setAnalysisResult(refinedResult);
                        setCurrentStep("entry");
                    }}
                    onBack={() => setCurrentStep("intake")}
                />
            )}

            {currentStep === "entry" && (
                <div className="space-y-6">
                    {/* Rate Entry Form */}
                    <SpotRateEntryForm
                        onSubmit={handleUpdateSPE}
                        isLoading={state.isLoading}
                        initialCharges={state.spe?.charges || []}
                        suggestedCharges={analysisResult?.assertions}
                        shipmentType={shipmentType}
                        serviceScope={serviceScope}
                    />
                </div>
            )}

            {currentStep === "acknowledge" && (
                <Card>
                    <CardHeader>
                        <CardTitle>Review & Acknowledge</CardTitle>
                        <CardDescription>
                            Review the entered rates and acknowledge the conditional nature of this quote.
                        </CardDescription>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        {/* Show charges summary */}
                        <div className="rounded-lg border p-4 space-y-2">
                            <h4 className="font-medium">Charges Summary</h4>
                            {(state.spe?.charges || chargeLines).map((charge, i) => (
                                <div key={i} className="flex justify-between items-start text-sm py-1">
                                    <span className="mt-0.5">{charge.description}</span>
                                    <div className="text-right">
                                        <span className="font-mono block">
                                            {charge.amount} {charge.currency}
                                            <span className="text-muted-foreground text-xs ml-1">
                                                /{charge.unit === 'per_kg' ? 'kg' :
                                                    charge.unit === 'flat' ? 'flat' :
                                                        charge.unit.replace('per_', '')}
                                            </span>
                                        </span>
                                        {charge.min_charge && (
                                            <span className="text-xs text-muted-foreground block">
                                                Min: {charge.min_charge} {charge.currency}
                                            </span>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>

                        <Separator />

                        <Button
                            onClick={() => setShowAckModal(true)}
                            className="w-full bg-amber-600 hover:bg-amber-700"
                        >
                            Proceed to Acknowledgement
                        </Button>
                    </CardContent>
                </Card>
            )}

            {currentStep === "approval" && state.spe && (
                <>
                    {state.flowState === "AWAITING_MANAGER" ? (
                        <AwaitingManagerBanner speId={state.spe.id} />
                    ) : (
                        <SpotManagerApproval
                            spe={state.spe}
                            onApprove={handleApproval}
                            isLoading={state.isLoading}
                        />
                    )}
                </>
            )}

            {currentStep === "compute" && derived.canProceedToPricing && (
                <>
                    {!state.quoteResult ? (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                                    Ready to Compute
                                </CardTitle>
                                <CardDescription>
                                    All approvals complete. Click below to generate the SPOT quote.
                                </CardDescription>
                            </CardHeader>
                            <CardContent>
                                <Button
                                    onClick={handleCompute}
                                    disabled={state.isLoading}
                                    className="w-full"
                                    size="lg"
                                >
                                    {state.isLoading ? (
                                        <Clock className="h-4 w-4 mr-2 animate-spin" />
                                    ) : null}
                                    Compute SPOT Quote
                                </Button>
                            </CardContent>
                        </Card>
                    ) : (
                        <Card>
                            <CardHeader>
                                <CardTitle className="flex items-center gap-2">
                                    <CheckCircle2 className="h-5 w-5 text-green-500" />
                                    SPOT Quote Preview
                                </CardTitle>
                                <CardDescription>
                                    Breakdown of charges based on SPOT entry and pricing logic.
                                </CardDescription>
                            </CardHeader>
                            <CardContent className="space-y-6">
                                <div className="space-y-4">
                                    {[
                                        { title: "Origin Charges", bucket: "origin_charges", icon: "arrow-up" },
                                        { title: "Air Freight", bucket: ["freight_charges", "airfreight"], icon: "plane" },
                                        { title: "Destination Charges", bucket: "destination_charges", icon: "arrow-down" }
                                    ].map((group) => {
                                        const groupLines = state.quoteResult!.lines?.filter(
                                            l => !l.is_informational && (Array.isArray(group.bucket) ? group.bucket.includes(l.bucket) : l.bucket === group.bucket)
                                        );

                                        // Determine if we should show this group (always show if lines exist, 
                                        // maybe catch-all "Other" later?)
                                        if (!groupLines || groupLines.length === 0) return null;

                                        return (
                                            <div key={group.title} className="space-y-2">
                                                <div className="font-semibold text-xs uppercase tracking-wider text-muted-foreground border-b pb-1">
                                                    {group.title}
                                                </div>
                                                <div className="rounded-md divide-y border-x border-b border-t-0">
                                                    {groupLines.map((line, idx) => (
                                                        <div key={idx} className="flex justify-between p-3 text-sm bg-card hover:bg-accent/5 transition-colors">
                                                            <div>
                                                                <div className="font-medium">{line.description}</div>
                                                                <div className="text-xs text-muted-foreground">{line.source}</div>
                                                            </div>
                                                            <div className="text-right">
                                                                <div className="font-mono">{parseFloat(line.sell_pgk_incl_gst || "0").toLocaleString('en-US', { style: 'currency', currency: 'PGK' })}</div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        );
                                    })}

                                    {/* Catch-all for any lines not in the main groups */}
                                    {(() => {
                                        const mainBuckets = ["origin_charges", "freight_charges", "airfreight", "destination_charges"];
                                        const otherLines = state.quoteResult!.lines?.filter(
                                            l => !l.is_informational && !mainBuckets.includes(l.bucket)
                                        );

                                        if (!otherLines || otherLines.length === 0) return null;

                                        return (
                                            <div className="space-y-2">
                                                <div className="font-semibold text-xs uppercase tracking-wider text-muted-foreground border-b pb-1">
                                                    Other Charges
                                                </div>
                                                <div className="rounded-md divide-y border-x border-b border-t-0">
                                                    {otherLines.map((line, idx) => (
                                                        <div key={idx} className="flex justify-between p-3 text-sm bg-card">
                                                            <div>
                                                                <div className="font-medium">{line.description}</div>
                                                                <div className="text-xs text-muted-foreground">{line.source}</div>
                                                            </div>
                                                            <div className="text-right">
                                                                <div className="font-mono">{parseFloat(line.sell_pgk_incl_gst || "0").toLocaleString('en-US', { style: 'currency', currency: 'PGK' })}</div>
                                                            </div>
                                                        </div>
                                                    ))}
                                                </div>
                                            </div>
                                        );
                                    })()}
                                </div>

                                {state.quoteResult.lines?.some(l => l.is_informational) && (
                                    <div className="space-y-2">
                                        <div className="font-semibold text-sm text-amber-600 flex items-center gap-2">
                                            <AlertTriangle className="h-4 w-4" />
                                            Conditions & Notes (Excluded from Total)
                                        </div>
                                        <div className="bg-amber-50 border border-amber-200 rounded-md p-3 space-y-2">
                                            {state.quoteResult.lines?.filter(l => l.is_informational).map((line, idx) => (
                                                <div key={idx} className="text-sm text-amber-800 flex justify-between">
                                                    <span>{line.description}</span>
                                                    <span className="italic text-xs opacity-70">Note</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                )}

                                <Separator />

                                <div className="flex justify-between items-center text-lg font-bold">
                                    <div>Total (Inc. GST)</div>
                                    <div>
                                        {parseFloat(state.quoteResult.totals?.total_sell_pgk_incl_gst || "0").toLocaleString('en-US', { style: 'currency', currency: 'PGK' })}
                                    </div>
                                </div>

                                <div className="flex gap-2">
                                    <Button variant="outline" onClick={() => router.push('/quotes')} className="w-full">
                                        Back to Dashboard
                                    </Button>
                                    <Button className="w-full bg-blue-600 hover:bg-blue-700">
                                        Create Quote
                                    </Button>
                                </div>
                            </CardContent>
                        </Card>
                    )}
                </>
            )}

            {/* Acknowledgement Modal */}
            {state.spe && (
                <SpotAcknowledgementModal
                    open={showAckModal}
                    onOpenChange={setShowAckModal}
                    conditions={state.spe.conditions}
                    onAcknowledge={handleAcknowledge}
                    isLoading={state.isLoading}
                />
            )}
        </div>
    );
}
