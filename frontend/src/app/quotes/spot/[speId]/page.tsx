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
    RejectedBanner
} from "@/components/spot";
import { SpotRateEntryForm } from "@/components/spot/SpotRateEntryForm";
import type { SPEChargeLine, CreateSPERequest, SPEShipmentContext, SPECommodity } from "@/lib/spot-types";

// Progress steps
type Step = "entry" | "acknowledge" | "approval" | "compute";

const STEPS: { id: Step; label: string }[] = [
    { id: "entry", label: "Enter Rates" },
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

    const { state, actions, derived } = useSpotMode();
    const [currentStep, setCurrentStep] = useState<Step>("entry");
    const [showAckModal, setShowAckModal] = useState(false);
    const [chargeLines, setChargeLines] = useState<Omit<SPEChargeLine, 'id'>[]>([]);

    // Load existing SPE if not new
    useEffect(() => {
        if (!isNew && speId) {
            actions.loadSPE(speId);
        }
    }, [isNew, speId, actions]);

    // Determine current step from SPE state
    useEffect(() => {
        if (state.spe) {
            if (state.flowState === "READY") {
                setCurrentStep("compute");
            } else if (state.flowState === "AWAITING_MANAGER") {
                setCurrentStep("approval");
            } else if (state.spe.acknowledgement) {
                setCurrentStep("approval");
            } else if (state.spe.charges.length > 0) {
                setCurrentStep("acknowledge");
            }
        }
    }, [state]);

    // Handle creating new SPE with charges
    const handleCreateSPE = async (charges: Omit<SPEChargeLine, 'id'>[]) => {
        setChargeLines(charges);

        const shipmentContext: SPEShipmentContext = {
            origin_country: originCountry,
            destination_country: destCountry,
            origin_code: originCode,
            destination_code: destCode,
            commodity,
            total_weight_kg: weight,
            pieces,
        };

        const request: CreateSPERequest = {
            shipment_context: shipmentContext,
            charges: charges,
            trigger_code: triggerCode,
            trigger_text: triggerText,
            conditions: {
                space_not_confirmed: true,
                airline_acceptance_not_confirmed: true,
                rate_validity_hours: 72,
                conditional_charges_present: charges.some(c => c.conditional),
            },
        };

        const spe = await actions.createSPE(request);
        if (spe) {
            // Navigate to the non-new URL
            router.replace(`/quotes/spot/${spe.id}`);
            setCurrentStep("acknowledge");
        }
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
        const result = await actions.computeQuote({
            quote_request: {
                payment_term: "PREPAID",
                service_scope: "D2D",
                output_currency: "PGK",
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
        <div className="container mx-auto max-w-4xl p-6">
            {/* Header */}
            <div className="flex items-center gap-4 mb-6">
                <Button variant="ghost" size="icon" onClick={() => router.back()}>
                    <ArrowLeft className="h-5 w-5" />
                </Button>
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2">
                        <Package className="h-6 w-6 text-amber-600" />
                        SPOT Rate Entry
                    </h1>
                    <p className="text-muted-foreground">
                        {isNew ? "Create new SPOT quote" : `SPE: ${speId.slice(0, 8)}...`}
                    </p>
                </div>
                <Badge variant="outline" className="ml-auto text-amber-600 border-amber-400">
                    {triggerCode || state.spe?.trigger_code || "SPOT"}
                </Badge>
            </div>

            {/* Progress */}
            {renderProgress()}

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

            {/* Shipment Summary */}
            <Card className="mb-6">
                <CardHeader className="pb-3">
                    <CardTitle className="text-base">Shipment Summary</CardTitle>
                </CardHeader>
                <CardContent>
                    <div className="grid grid-cols-4 gap-4 text-sm">
                        <div>
                            <span className="text-muted-foreground">Route:</span>{" "}
                            <span className="font-medium">
                                {originCode || state.spe?.shipment_context.origin_code} → {destCode || state.spe?.shipment_context.destination_code}
                            </span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Commodity:</span>{" "}
                            <span className="font-medium">{commodity || state.spe?.shipment_context.commodity}</span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Weight:</span>{" "}
                            <span className="font-medium">{weight || state.spe?.shipment_context.total_weight_kg} kg</span>
                        </div>
                        <div>
                            <span className="text-muted-foreground">Pieces:</span>{" "}
                            <span className="font-medium">{pieces || state.spe?.shipment_context.pieces}</span>
                        </div>
                    </div>
                </CardContent>
            </Card>

            {/* Step Content */}
            {currentStep === "entry" && (
                <SpotRateEntryForm
                    onSubmit={handleCreateSPE}
                    isLoading={state.isLoading}
                    initialCharges={state.spe?.charges || []}
                />
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
                                <div key={i} className="flex justify-between text-sm">
                                    <span>{charge.description}</span>
                                    <span className="font-mono">{charge.amount} {charge.currency}</span>
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
