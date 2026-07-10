"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle, ChevronDown, ChevronUp, Info, ShieldAlert, FileText, ArrowLeft } from "lucide-react";
import { hardCaseAirImportData } from "../../data/hardCaseAirImport";
import { DraftCharge, DraftChargeStatus, Evidence, DraftQuote } from "../../lib/draft-quote-types";

// Helper to convert rate specs into human-friendly text
function humanizeRate(rate: number | null, unit: string | null, label: string): string {
    if (label.includes("Min") && rate) {
        return `Minimum USD 230.00 or USD ${rate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Fuel") && rate) {
        return `USD ${rate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Security") && rate) {
        return `USD ${rate.toFixed(2)} per ${unit || "kg"}`;
    }
    if (label.includes("Handling") && rate) {
        return `SGD ${rate.toFixed(2)} per set`;
    }
    if (rate) {
        return `${rate.toFixed(2)} per ${unit || "unit"}`;
    }
    return "Flat fee";
}

function friendlyStatus(status: string): string {
    switch (status) {
        case "accepted_by_user": return "Accepted";
        case "suggested": return "Suggested";
        case "ignored": return "Ignored";
        case "pending_product_code": return "Pending Product Code";
        case "needs_review": return "Needs Attention";
        case "unclassified":
        case "unclassified_item": return "Unknown Charge";
        default: return status;
    }
}

// Stateful Decision type for Reopen/Undo logging
interface Decision {
    id: string; // charge id or item id
    type: "map" | "request" | "ignore" | "accept" | "add";
    description: string;
    originalState: {
        suggestedCharges: DraftCharge[];
        reviewQueue: Array<{ id: string; type: string; message: string }>;
        unclassifiedItems: Array<{ id: string; raw_text: string; evidence: Evidence | null; review_reason: string }>;
        ignoredItems: Array<{ id: string; raw_text: string; ignored_reason: string; evidence: Evidence | null }>;
    };
}

export function ExceptionWorkspace({ initialData = hardCaseAirImportData, isLive = false, envelopeId }: { initialData?: DraftQuote; isLive?: boolean; envelopeId?: string }) {
    // Single state containers for mock database updates
    const [draftQuote] = useState(initialData);
    const [explainTotals, setExplainTotals] = useState(false);
    const [suggestedCharges, setSuggestedCharges] = useState(initialData.suggested_charges);
    const [reviewQueue, setReviewQueue] = useState(initialData.review_queue);
    const [unclassifiedItems, setUnclassifiedItems] = useState(initialData.unclassified_items);
    const [ignoredItems, setIgnoredItems] = useState<Array<{ id: string; raw_text: string; ignored_reason: string; evidence: Evidence | null }>>(initialData.ignored_items || []);
    const [decisions, setDecisions] = useState<Decision[]>([]);
    const [reviewSession, setReviewSession] = useState(initialData.review_session || {
        status: "draft" as const,
        finalized_by: null,
        finalized_at: null,
        remaining_blockers: initialData.review_queue.length,
        available_actions: [] as string[]
    });

    // Guided resolving workflow states
    const [activeIssueId, setActiveIssueId] = useState<string | null>(initialData.review_queue?.[0]?.id || null);
    const [selectedActionType, setSelectedActionType] = useState<string | null>(null);
    const [showHelpText, setShowHelpText] = useState(false);

    // Accordions
    const [showSuggested, setShowSuggested] = useState(false);
    const [showTerms, setShowTerms] = useState(false);
    const [showTotalsPanel, setShowTotalsPanel] = useState(false);

    // Request new ProductCode fields
    const [reqLabel, setReqLabel] = useState("");
    const [reqSource, setReqSource] = useState("");
    const [reqCurrency, setReqCurrency] = useState("");
    const [reqAmount, setReqAmount] = useState("");

    // Add Unknown Charge wizard fields
    const [unknownStep, setUnknownStep] = useState(1);
    const [unknownClassification, setUnknownClassification] = useState<string | null>(null);
    const [addName, setAddName] = useState("");
    const [addBucket, setAddBucket] = useState("origin_charges");
    const [addCurrency, setAddCurrency] = useState("SGD");
    const [addAmount, setAddAmount] = useState("");
    const [addUnit, setAddUnit] = useState("set");
    const [addProductCode, setAddProductCode] = useState("");

    // Action message alert banner
    const [actionMessage, setActionMessage] = useState<string | null>(null);
    
    // Prototype override
    const [prototypeOverride, setPrototypeOverride] = useState(false);

    // Save snapshot state helper for Undos
    const captureSnapshot = (id: string, type: "map" | "request" | "ignore" | "accept" | "add", desc: string) => {
        const snapshot: Decision = {
            id,
            type,
            description: desc,
            originalState: {
                suggestedCharges: JSON.parse(JSON.stringify(suggestedCharges)),
                reviewQueue: JSON.parse(JSON.stringify(reviewQueue)),
                unclassifiedItems: JSON.parse(JSON.stringify(unclassifiedItems)),
                ignoredItems: JSON.parse(JSON.stringify(ignoredItems))
            }
        };
        setDecisions(prev => [...prev.filter(d => d.id !== id), snapshot]);
    };

    // Undo action decision helper
    const handleUndoDecision = (id: string) => {
        const targetDecision = decisions.find(d => d.id === id);
        if (targetDecision) {
            setSuggestedCharges(targetDecision.originalState.suggestedCharges);
            setReviewQueue(targetDecision.originalState.reviewQueue);
            setUnclassifiedItems(targetDecision.originalState.unclassifiedItems);
            setIgnoredItems(targetDecision.originalState.ignoredItems);
            setDecisions(prev => prev.filter(d => d.id !== id));
            setActionMessage(`Undone decision for ${targetDecision.description}.`);
            setActiveIssueId(id);
            setSelectedActionType(null);
            setUnknownStep(1);
        }
    };

    const submitLiveDecision = async (decisionItem: {
        decision_id: string;
        type: string;
        target_id: string;
        details: Record<string, unknown>;
        audit_metadata: { user_id: number; timestamp: string };
    }) => {
        if (reviewSession.status === "finalized") {
            throw new Error("Draft Quote review is finalized and locked.");
        }
        if (!isLive || !envelopeId) {
            return;
        }
        const { resolveDraftQuoteDecisions } = await import("../../lib/api");
        await resolveDraftQuoteDecisions(envelopeId, {
            idempotency_key: crypto.randomUUID ? crypto.randomUUID() : "3b128522-a89e-4055-bf51-199eecc5628b",
            decisions: [decisionItem]
        });
    };

    const handleFinalizeReview = async () => {
        if (!canFinishReview || reviewSession.status === "finalized") {
            return;
        }
        if (isLive && envelopeId) {
            try {
                const { finalizeDraftQuoteReview } = await import("../../lib/api");
                const result = await finalizeDraftQuoteReview(envelopeId, crypto.randomUUID ? crypto.randomUUID() : "47c7fa2d-8a4f-4cdb-9fbf-a396ed7f7f88");
                setReviewSession(prev => ({
                    ...prev,
                    status: result.review_status,
                    finalized_by: result.finalized_by ?? null,
                    finalized_at: result.finalized_at ?? null,
                    remaining_blockers: result.remaining_blockers,
                    available_actions: ["reopen"]
                }));
            } catch (err) {
                const errMsg = err instanceof Error ? err.message : String(err);
                setActionMessage(`API error finalizing review: ${errMsg}`);
                return;
            }
        } else {
            setReviewSession(prev => ({
                ...prev,
                status: "finalized",
                finalized_at: new Date().toISOString(),
                remaining_blockers: 0,
                available_actions: ["reopen"]
            }));
        }
        setActionMessage("Draft Quote review finalized and locked.");
    };

    const handleUseApprovedProductCode = async (chargeId: string, charge: DraftCharge) => {
        const reqId = charge.product_code_request_id;
        const pcId = charge.approved_product_code_id;
        const code = charge.approved_product_code || charge.suggested_product_code || "";

        if (!reqId || !pcId) {
            setActionMessage("Missing approved ProductCode request metadata.");
            return;
        }

        const decisionId = `dec-${Date.now()}`;
        const newDecisionItem = {
            decision_id: decisionId,
            type: "use_approved_product_code",
            target_id: chargeId,
            details: {
                product_code_request_id: Number(reqId),
                product_code_id: Number(pcId)
            },
            audit_metadata: {
                user_id: 1,
                timestamp: new Date().toISOString()
            }
        };

        try {
            await submitLiveDecision(newDecisionItem);
        } catch (err) {
            console.error("Failed to submit resolve decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            setActionMessage(`API error resolving mapping: ${errMsg}`);
            return;
        }

        // Apply locally
        captureSnapshot(chargeId, "map", `Used approved billing code ${code} for ${charge.display_label}`);
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, suggested_product_code: code, status: "accepted_by_user" as DraftChargeStatus } : c))
        );
        setReviewQueue(prev => prev.filter(q => q.id !== chargeId));
        setActionMessage(`Approved billing code ${code} applied successfully to ${charge.display_label}.`);
        setSelectedActionType(null);
    };

    // Action execution helpers
    const handleMapProductCode = async (chargeId: string, productCode: string, displayLabel: string) => {
        try {
            await submitLiveDecision({
                decision_id: `dec-${Date.now()}`,
                type: "map_to_product_code",
                target_id: chargeId,
                details: { product_code: productCode },
                audit_metadata: {
                    user_id: 1,
                    timestamp: new Date().toISOString()
                }
            });
        } catch (err) {
            console.error("Failed to submit resolve decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            setActionMessage(`API error resolving mapping: ${errMsg}`);
            return;
        }
        captureSnapshot(chargeId, "map", `Mapped ${displayLabel} to billing code ${productCode}`);
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, suggested_product_code: productCode, status: "accepted_by_user" as DraftChargeStatus } : c))
        );
        setReviewQueue(prev => prev.filter(q => q.id !== chargeId));
        setActionMessage(`${displayLabel} mapped to billing code ${productCode}. Resolved and included in draft.`);
        setSelectedActionType(null);
    };

    const handleOpenRequestProductCode = (charge: DraftCharge) => {
        setReqLabel(charge.display_label);
        setReqSource(charge.evidence?.source_text || charge.raw_label);
        setReqCurrency(charge.currency);
        setReqAmount(String(charge.amount));
        setSelectedActionType("request_product_code");
    };

    const handleSubmitProductCodeRequest = async (chargeId: string) => {
        try {
            await submitLiveDecision({
                decision_id: `dec-${Date.now()}`,
                type: "request_product_code",
                target_id: chargeId,
                details: {
                    proposed_code: reqLabel,
                    description: reqSource || reqLabel,
                    category: "destination_charges",
                    domain: "IMPORT",
                    reason: "Operator edited and resubmitted ProductCode request"
                },
                audit_metadata: {
                    user_id: 1,
                    timestamp: new Date().toISOString()
                }
            });
        } catch (err) {
            console.error("Failed to submit ProductCode request:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            setActionMessage(`API error submitting ProductCode request: ${errMsg}`);
            return;
        }
        captureSnapshot(chargeId, "request", `Requested new billing code for ${reqLabel}`);
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, status: "pending_product_code" as DraftChargeStatus } : c))
        );
        setReviewQueue(prev => prev.filter(q => q.id !== chargeId));
        setActionMessage(`New ProductCode request created for ${reqLabel}. Resolved locally and pending approval.`);
        setSelectedActionType(null);
    };

    const handleAcceptSuggestedMapping = async (chargeId: string, displayLabel: string, suggestedCode: string) => {
        if (isReviewLocked) return;
        try {
            await submitLiveDecision({
                decision_id: `dec-${Date.now()}`,
                type: "accept_suggestion",
                target_id: chargeId,
                details: {},
                audit_metadata: {
                    user_id: 1,
                    timestamp: new Date().toISOString()
                }
            });
        } catch (err) {
            console.error("Failed to submit accept suggestion decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            setActionMessage(`API error accepting suggested mapping: ${errMsg}`);
            return;
        }
        captureSnapshot(chargeId, "accept", `Accepted code ${suggestedCode} for ${displayLabel}`);
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, status: "accepted_by_user" as DraftChargeStatus } : c))
        );
        setReviewQueue(prev => prev.filter(q => q.id !== chargeId));
        setActionMessage(`Accepted suggested mapping ${suggestedCode} for ${displayLabel}.`);
        setSelectedActionType(null);
    };

    const handleIgnoreCharge = async (chargeId: string, charge: DraftCharge) => {
        try {
            await submitLiveDecision({
                decision_id: `dec-${Date.now()}`,
                type: "ignore",
                target_id: chargeId,
                details: { reason: "Operator ignored rejected ProductCode blocker as non-commercial" },
                audit_metadata: {
                    user_id: 1,
                    timestamp: new Date().toISOString()
                }
            });
        } catch (err) {
            console.error("Failed to submit ignore decision:", err);
            const errMsg = err instanceof Error ? err.message : String(err);
            setActionMessage(`API error ignoring charge: ${errMsg}`);
            return;
        }
        captureSnapshot(chargeId, "ignore", `Ignored ${charge.display_label}`);
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, status: "ignored" as DraftChargeStatus, include_in_totals: false } : c))
        );
        setIgnoredItems(prev => [
            ...prev,
            {
                id: chargeId,
                raw_text: charge.raw_label,
                ignored_reason: "Ignored by operator during quote review",
                evidence: charge.evidence
            }
        ]);
        setReviewQueue(prev => prev.filter(q => q.id !== chargeId));
        setActionMessage(`${charge.display_label} ignored and excluded from totals.`);
        setSelectedActionType(null);
    };

    const handleIgnoreUnknownCharge = (itemId: string, rawText: string) => {
        if (isReviewLocked) return;
        captureSnapshot(itemId, "ignore", "Ignored unknown text block");
        setIgnoredItems(prev => [
            ...prev,
            {
                id: itemId,
                raw_text: rawText,
                ignored_reason: "Operator ignored text block as non-commercial text",
                evidence: unclassifiedItems.find(i => i.id === itemId)?.evidence || null
            }
        ]);
        setUnclassifiedItems(prev => prev.filter(i => i.id !== itemId));
        setActionMessage(`Ignored unknown text block. Excluded from draft.`);
        setSelectedActionType(null);
        setUnknownStep(1);
    };

    const handleAddUnknownAsCharge = (itemId: string) => {
        if (isReviewLocked) return;
        const newChargeId = `chg-new-${Date.now()}`;
        const newCharge: DraftCharge = {
            id: newChargeId,
            status: (addProductCode ? "accepted_by_user" : "suggested") as DraftChargeStatus,
            display_label: addName,
            raw_label: addName,
            suggested_product_code: addProductCode || null,
            product_code_conflict: !addProductCode,
            bucket: addBucket,
            currency: addCurrency,
            amount: Number(addAmount) || 0,
            rate: null,
            unit: addUnit,
            calculation_basis: null,
            minimum_charge: null,
            percentage_base: null,
            quantity: 1,
            include_in_totals: true,
            conditions: [],
            warnings: [],
            review_reason: null,
            evidence: unclassifiedItems.find(i => i.id === itemId)?.evidence || null,
            similarity_group_id: null,
            correction_actions: []
        };

        captureSnapshot(itemId, "add", `Added unknown block as charge ${addName}`);
        setSuggestedCharges(prev => [...prev, newCharge]);
        setUnclassifiedItems(prev => prev.filter(i => i.id !== itemId));
        
        if (!addProductCode) {
            setReviewQueue(prev => [
                ...prev,
                {
                    id: newChargeId,
                    type: "charge_needs_review",
                    message: "Newly added charge line requires a valid ProductCode mapping."
                }
            ]);
        }

        setActionMessage(`Unknown block added as draft charge line: "${addName}".`);
        setSelectedActionType(null);
        setUnknownStep(1);
    };

    const toggleIncludeInTotals = (chargeId: string) => {
        if (isReviewLocked) return;
        setSuggestedCharges(prev =>
            prev.map(c => (c.id === chargeId ? { ...c, include_in_totals: !c.include_in_totals } : c))
        );
    };

    // Calculate dynamic lists matching live decisions
    const combinedUnresolved = [
        ...reviewQueue.map(item => {
            const charge = suggestedCharges.find(c => c.id === item.id);
            return {
                id: item.id,
                type: "review_item",
                title: charge?.display_label || "Needs Review",
                problem: charge?.review_reason || item.message || "Requires validation.",
                evidence: charge?.evidence,
                charge
            };
        }),
        ...unclassifiedItems.map(item => ({
            id: item.id,
            type: "unknown_charge",
            title: "Unknown Charge Block",
            problem: "Commercial text block extracted from quote document could not be safely mapped to a standard charge line.",
            evidence: item.evidence,
            itemDetails: item
        }))
    ];

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const currentIssue = (combinedUnresolved.find(i => i.id === activeIssueId) || combinedUnresolved[0] || null) as any;

    // Calculate totals split by currency
    const activeCharges = suggestedCharges.filter(c => c.include_in_totals && c.status !== "ignored");
    const uniqueCurrencies = Array.from(new Set(activeCharges.map(c => c.currency)));
    const subtotals = uniqueCurrencies.reduce((acc, curr) => {
        acc[curr] = activeCharges.filter(c => c.currency === curr).reduce((sum, c) => sum + c.amount, 0);
        return acc;
    }, {} as Record<string, number>);

    // Checklist validators
    const checklistIssuesResolved = combinedUnresolved.length === 0;
    const checklistNoUnknown = unclassifiedItems.length === 0;
    const checklistProductCodesVerified = suggestedCharges
        .filter(c => c.include_in_totals && c.status !== "ignored")
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        .every(c => c.suggested_product_code !== null && c.status !== ("pending_product_code" as any));

    const canFinishReview = checklistIssuesResolved && checklistNoUnknown && checklistProductCodesVerified;
    const isReviewLocked = reviewSession.status === "finalized";
    const canUsePrototypeOverride = !isLive && prototypeOverride;

    // Direct Next-Step instructions guidance
    let nextStepGuidance = "Review the remaining commercial term before finishing.";
    if (combinedUnresolved.length > 0) {
        const first = combinedUnresolved[0];
        if (first.type === "review_item") {
            nextStepGuidance = `Next step: Choose a ProductCode for ${first.title}.`;
        } else {
            nextStepGuidance = `Next step: Decide whether this unknown text is a real charge.`;
        }
    }

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
            <div className="max-w-4xl mx-auto flex flex-col gap-6">

                {isLive && (
                    <div className="bg-yellow-950/40 border border-yellow-900/60 text-yellow-300 p-4 rounded-xl text-xs flex items-center gap-3">
                        <Info className="w-5 h-5 text-yellow-400 shrink-0" />
                        <span className="font-medium">Live draft data loaded. Operator decisions are saved when you apply each action.</span>
                    </div>
                )}

                {isReviewLocked && (
                    <div className="bg-emerald-950/30 border border-emerald-900/60 text-emerald-200 p-4 rounded-xl text-xs flex items-center gap-3">
                        <CheckCircle className="w-5 h-5 text-emerald-400 shrink-0" />
                        <span className="font-medium">Draft Quote review finalized and locked{reviewSession.finalized_at ? ` at ${reviewSession.finalized_at}` : ""}.</span>
                    </div>
                )}

                {/* Brand Header */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                    <div>
                        <div className="text-xs uppercase tracking-wider font-bold text-indigo-400 mb-1">Express Freight Management</div>
                        <h1 className="text-xl font-bold text-slate-50">SPOT Draft Quote Review</h1>
                        <p className="text-sm text-slate-400 mt-0.5">{draftQuote.quote_summary}</p>
                    </div>
                    <div className="bg-slate-950 border border-slate-800 px-4 py-2.5 rounded-xl shrink-0 text-center sm:text-right">
                        <span className="text-xs text-slate-500 block">Remaining Blockers</span>
                        <span className="text-lg font-bold text-amber-400">{combinedUnresolved.length} Issues Left</span>
                    </div>
                </div>

                {/* "What should I do next?" banner */}
                <div className="bg-indigo-950/20 border border-indigo-900/60 rounded-xl p-4 flex items-center gap-3 text-xs text-indigo-300">
                    <Info className="h-5 w-5 text-indigo-400 shrink-0" />
                    <div>
                        <span className="font-bold block">Current Task</span>
                        <span>{nextStepGuidance}</span>
                    </div>
                </div>

                {/* Live Action Message Confirmations */}
                {actionMessage && (
                    <div className="bg-emerald-950/40 border border-emerald-900/60 text-emerald-300 p-4 rounded-xl text-xs flex justify-between items-center">
                        <span>{actionMessage}</span>
                        <button onClick={() => setActionMessage(null)} className="text-emerald-500 hover:text-emerald-300 font-bold">Dismiss</button>
                    </div>
                )}

                {/* Main Guided resolutions Panel */}
                {currentIssue ? (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
                        
                        {/* Title Row */}
                        <div className="flex justify-between items-center pb-3 border-b border-slate-800 mb-4">
                            <div>
                                <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block">Resolve Mode</span>
                                <h2 className="text-lg font-bold text-slate-50 mt-0.5">{currentIssue.title}</h2>
                            </div>
                            <span className="text-[10px] text-amber-400 font-semibold bg-amber-950/40 px-2.5 py-1 rounded border border-amber-900/40">
                                Needs Attention
                            </span>
                        </div>

                        {/* Collapsible Guidance Drawer */}
                        <div className="mb-4">
                            <button 
                                onClick={() => setShowHelpText(!showHelpText)} 
                                className="text-xs text-indigo-400 font-semibold hover:underline flex items-center gap-1"
                            >
                                {showHelpText ? "Hide explanation" : "Why am I seeing this?"}
                            </button>
                            {showHelpText && (
                                <div className="mt-2 bg-slate-950 border border-slate-850 rounded-xl p-3.5 text-xs text-slate-300 leading-relaxed">
                                    {currentIssue.type === "review_item" ? (
                                        "RateEngine extracted this charge from the supplier quote, but it could not safely match a billing code. Choosing the correct billing code ensures accurate reporting, margins, and customer invoicing."
                                    ) : (
                                        "The quote contains commercial-looking text blocks that did not match standard layout definitions. Decide whether this represents a real charge, a conditions note, or should be ignored."
                                    )}
                                </div>
                            )}
                        </div>

                        <p className="text-xs text-slate-400 mb-4">{currentIssue.problem}</p>

                        {/* Matched Evidence context */}
                        {currentIssue.evidence && (
                            <div className="bg-slate-950 border border-slate-855 rounded-xl p-4 mb-6">
                                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">Source Quote Text</div>
                                <p className="text-sm font-mono text-slate-200 italic mb-1.5">
                                    &quot;{currentIssue.evidence.source_text}&quot;
                                </p>
                                <span className="text-xs text-slate-400">
                                    Document Location: page {currentIssue.evidence.page || 1} ({currentIssue.evidence.document_reference || "attachment"})
                                </span>
                            </div>
                        )}

                        {/* Guided workflows */}
                        {selectedActionType === null ? (
                            <div className="flex flex-col gap-4">
                                {currentIssue.type === "review_item" && currentIssue.charge ? (
                                    <div className="flex flex-col gap-4">
                                        {currentIssue.charge.correction_actions?.includes("PRODUCTCODE_REJECTED") && (
                                            <div className="bg-red-950/20 border border-red-900/60 p-4 rounded-xl text-xs flex flex-col gap-2 mb-2">
                                                <div className="flex items-center gap-2 text-red-300 font-bold text-sm">
                                                    <ShieldAlert className="w-4 h-4" />
                                                    <span>ProductCode Request Rejected</span>
                                                </div>
                                                <p className="text-slate-300">
                                                    The requested billing code <strong className="font-mono text-red-200 bg-slate-950 px-1.5 py-0.5 rounded">{currentIssue.charge.rejected_product_code || currentIssue.charge.product_code_request_id}</strong> was rejected by admin.
                                                </p>
                                                <p className="text-slate-300">
                                                    Reason: {currentIssue.charge.product_code_rejection_reason || "No rejection reason was provided."}
                                                </p>
                                                <div className="text-[10px] text-slate-500 font-mono">
                                                    Request Context ID: {currentIssue.charge.product_code_request_id}
                                                    {currentIssue.charge.product_code_rejected_at ? ` | Rejected: ${currentIssue.charge.product_code_rejected_at}` : ""}
                                                </div>
                                                <div className="mt-2 flex flex-wrap gap-2">
                                                    <button
                                                        onClick={() => setSelectedActionType("map_existing")}
                                                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Map to existing ProductCode
                                                    </button>
                                                    <button
                                                        onClick={() => handleOpenRequestProductCode(currentIssue.charge!)}
                                                        className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-200 rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Edit and resubmit request
                                                    </button>
                                                    <button
                                                        onClick={() => handleIgnoreCharge(currentIssue.id, currentIssue.charge!)}
                                                        className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-red-300 rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Ignore / exclude
                                                    </button>
                                                </div>
                                            </div>
                                        )}
                                        {currentIssue.charge.correction_actions?.includes("APPROVED_PRODUCTCODE_AVAILABLE") && (
                                            <div className="bg-emerald-950/20 border border-emerald-900/60 p-4 rounded-xl text-xs flex flex-col gap-2 mb-2">
                                                <div className="flex items-center gap-2 text-emerald-400 font-bold text-sm">
                                                    <CheckCircle className="w-4 h-4" />
                                                    <span>ProductCode Request Approved!</span>
                                                </div>
                                                <p className="text-slate-300">
                                                    The requested billing code <strong className="font-mono text-indigo-300 bg-slate-950 px-1.5 py-0.5 rounded">{currentIssue.charge.approved_product_code}</strong> has been approved by admin. You can directly map and consume this approval.
                                                </p>
                                                <div className="text-[10px] text-slate-500 font-mono">
                                                    Request Context ID: {currentIssue.charge.product_code_request_id}
                                                </div>
                                                <div className="mt-2">
                                                    <button
                                                        onClick={() => handleUseApprovedProductCode(currentIssue.id, currentIssue.charge!)}
                                                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Use Approved ProductCode ({currentIssue.charge.approved_product_code})
                                                    </button>
                                                </div>
                                            </div>
                                        )}

                                        <div className="flex flex-wrap gap-2">
                                            <button
                                                onClick={() => setSelectedActionType("map_existing")}
                                                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition"
                                            >
                                                Map to Existing ProductCode
                                            </button>
                                            <button
                                                onClick={() => handleOpenRequestProductCode(currentIssue.charge!)}
                                                className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-200 rounded-lg text-xs font-semibold transition"
                                            >
                                                Request New ProductCode
                                            </button>
                                            {currentIssue.charge.suggested_product_code && !currentIssue.charge.correction_actions?.includes("APPROVED_PRODUCTCODE_AVAILABLE") && (
                                                <button
                                                    onClick={() => handleAcceptSuggestedMapping(currentIssue.id, currentIssue.title, currentIssue.charge!.suggested_product_code!)}
                                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition"
                                                >
                                                    Accept Suggested Mapping ({currentIssue.charge.suggested_product_code})
                                                </button>
                                            )}
                                            <button
                                                onClick={() => handleIgnoreCharge(currentIssue.id, currentIssue.charge!)}
                                                className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-red-400 rounded-lg text-xs font-semibold transition"
                                            >
                                                Ignore as Non-Commercial
                                            </button>
                                        </div>
                                    </div>
                                ) : currentIssue.itemDetails ? (
                                    /* Unknown Charge Guided flow wizard */
                                    <div className="flex flex-col gap-4">
                                        {unknownStep === 1 ? (
                                            <div className="flex flex-col gap-2.5">
                                                <div className="text-xs font-semibold text-slate-300">Step 1: What is this text block?</div>
                                                <div className="flex flex-col sm:flex-row gap-2">
                                                    <button
                                                        onClick={() => { setUnknownClassification("charge"); setUnknownStep(2); }}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs font-semibold text-slate-200 text-left grow"
                                                    >
                                                        A real charge line
                                                    </button>
                                                    <button
                                                        onClick={() => { setUnknownClassification("note"); setUnknownStep(2); }}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs font-semibold text-slate-200 text-left grow"
                                                    >
                                                        A notes annotation or cargo condition
                                                    </button>
                                                    <button
                                                        onClick={() => handleIgnoreUnknownCharge(currentIssue.id, currentIssue.itemDetails!.raw_text)}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-red-900 hover:text-red-400 rounded-lg text-xs font-semibold text-red-400 text-left grow"
                                                    >
                                                        Not relevant (Ignore)
                                                    </button>
                                                </div>
                                            </div>
                                        ) : unknownStep === 2 ? (
                                            <div className="flex flex-col gap-3">
                                                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                                                    <button onClick={() => setUnknownStep(1)} className="hover:underline flex items-center gap-0.5 text-indigo-400 font-semibold">
                                                        <ArrowLeft className="h-3.5 w-3.5" /> Back
                                                    </button>
                                                    <span>| Classification: {unknownClassification}</span>
                                                </div>
                                                
                                                {unknownClassification === "charge" ? (
                                                    <div className="flex flex-col gap-2.5">
                                                        <div className="text-xs font-semibold text-slate-300">Step 2: How should it be mapped?</div>
                                                        <div className="flex flex-col sm:flex-row gap-2">
                                                            <button
                                                                onClick={() => { setSelectedActionType("map_existing"); }}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs text-left grow text-slate-200"
                                                            >
                                                                Map to an existing billing code
                                                            </button>
                                                            <button
                                                                onClick={() => {
                                                                    setReqLabel("Unknown Charge Item");
                                                                    setReqSource(currentIssue.itemDetails!.raw_text);
                                                                    setReqCurrency("SGD");
                                                                    setReqAmount("0");
                                                                    setSelectedActionType("request_product_code");
                                                                }}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs text-left grow text-slate-200"
                                                            >
                                                                Request new billing code
                                                            </button>
                                                            <button
                                                                onClick={() => {
                                                                    setAddName("New Charge");
                                                                    setAddAmount("0");
                                                                    setSelectedActionType("add_charge");
                                                                }}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs text-left grow text-slate-200"
                                                            >
                                                                Add manually as draft charge line
                                                            </button>
                                                        </div>
                                                    </div>
                                                ) : (
                                                    <div className="flex flex-col gap-2.5">
                                                        <div className="text-xs font-semibold text-slate-300">Step 2: Handle condition note</div>
                                                        <p className="text-xs text-slate-400">Notes can be ignored in quote calculations but are preserved in commercial terms logs.</p>
                                                        <div className="flex gap-2">
                                                            <button
                                                                onClick={() => {
                                                                    captureSnapshot(currentIssue.id, "accept", `Accepted condition note: ${currentIssue.itemDetails!.raw_text}`);
                                                                    setUnclassifiedItems(prev => prev.filter(i => i.id !== currentIssue.id));
                                                                    setActionMessage("Note resolved and archived in quote details.");
                                                                    setUnknownStep(1);
                                                                }}
                                                                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded text-xs text-white font-semibold"
                                                            >
                                                                Approve & File Note
                                                            </button>
                                                            <button
                                                                onClick={() => handleIgnoreUnknownCharge(currentIssue.id, currentIssue.itemDetails!.raw_text)}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-850 hover:border-slate-700 rounded text-xs text-slate-400"
                                                            >
                                                                Ignore Note
                                                            </button>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        ) : null}
                                    </div>
                                ) : null}
                            </div>
                        ) : selectedActionType === "map_existing" ? (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
                                <h3 className="text-xs uppercase font-bold text-indigo-400">Map to Existing ProductCode</h3>
                                <p className="text-xs text-slate-400">Choose this if the billing code already exists in EFM RateEngine catalog.</p>
                                <div className="flex gap-2">
                                    <select
                                        onChange={e => {
                                            if (e.target.value) {
                                                handleMapProductCode(currentIssue.id, e.target.value, currentIssue.title);
                                            }
                                        }}
                                        className="text-xs bg-slate-900 border border-slate-800 rounded p-2 text-slate-200 grow"
                                    >
                                        <option value="">-- Choose Billing Code --</option>
                                        <option value="AF-FREIGHT">AF-FREIGHT (Air Freight Linehaul)</option>
                                        <option value="AF-FUEL">AF-FUEL (Fuel Surcharge)</option>
                                        <option value="AF-SEC">AF-SEC (Security Charge)</option>
                                        <option value="AF-HC">AF-HC (Handling Charge)</option>
                                    </select>
                                    <button
                                        onClick={() => setSelectedActionType(null)}
                                        className="px-3 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        ) : selectedActionType === "request_product_code" ? (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
                                <h3 className="text-xs uppercase font-bold text-indigo-400">Request New ProductCode</h3>
                                <p className="text-xs text-slate-400">Choose this if the charge is legitimate but the code is missing from the master EFM database.</p>
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                    <div>
                                        <label className="text-slate-500 block mb-1">Charge Name</label>
                                        <input type="text" value={reqLabel} onChange={e => setReqLabel(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Quote Extracted Text</label>
                                        <input type="text" value={reqSource} onChange={e => setReqSource(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Currency</label>
                                        <input type="text" value={reqCurrency} onChange={e => setReqCurrency(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Amount</label>
                                        <input type="text" value={reqAmount} onChange={e => setReqAmount(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                </div>
                                <div className="flex gap-2 justify-end mt-2">
                                    <button
                                        onClick={() => handleSubmitProductCodeRequest(currentIssue.id)}
                                        className="px-4 py-2 bg-indigo-600 text-white rounded text-xs font-semibold"
                                    >
                                        Submit Request
                                    </button>
                                    <button
                                        onClick={() => setSelectedActionType(null)}
                                        className="px-4 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        ) : selectedActionType === "add_charge" ? (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
                                <h3 className="text-xs uppercase font-bold text-indigo-400">Add manually as draft charge line</h3>
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                    <div>
                                        <label className="text-slate-500 block mb-1">Charge Name</label>
                                        <input type="text" value={addName} onChange={e => setAddName(e.target.value)} placeholder="e.g. Handling Fee" className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Section Bucket</label>
                                        <select value={addBucket} onChange={e => setAddBucket(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5">
                                            <option value="origin_charges">Origin Charges</option>
                                            <option value="destination_charges">Destination Charges</option>
                                            <option value="airfreight">Air Freight Linehaul</option>
                                        </select>
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Currency</label>
                                        <input type="text" value={addCurrency} onChange={e => setAddCurrency(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Amount</label>
                                        <input type="text" value={addAmount} onChange={e => setAddAmount(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Unit Spec</label>
                                        <input type="text" value={addUnit} onChange={e => setAddUnit(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Mapping Code (Optional)</label>
                                        <input type="text" value={addProductCode} onChange={e => setAddProductCode(e.target.value)} placeholder="Approved ProductCode" className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                </div>
                                <div className="flex gap-2 justify-end mt-2">
                                    <button
                                        onClick={() => handleAddUnknownAsCharge(currentIssue.id)}
                                        className="px-4 py-2 bg-indigo-600 text-white rounded text-xs font-semibold"
                                    >
                                        Confirm and Add
                                    </button>
                                    <button
                                        onClick={() => setSelectedActionType(null)}
                                        className="px-4 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        ) : null}

                    </div>
                ) : (
                    <div className="bg-emerald-950/20 border border-emerald-900/60 rounded-2xl p-6 shadow text-center flex flex-col items-center gap-3">
                        <CheckCircle className="h-10 w-10 text-emerald-400" />
                        <div>
                            <h2 className="text-base font-bold text-slate-50">All Issues Resolved</h2>
                            <p className="text-xs text-slate-400 mt-1">Checklist checks are verified. You can finalize review below.</p>
                        </div>
                    </div>
                )}

                {/* "Still Needs Attention" block list matches checklist issues */}
                {combinedUnresolved.length > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">Still Needs Attention</h2>
                        <div className="flex flex-col gap-2.5">
                            {combinedUnresolved.map(item => (
                                <div key={`${item.type}-${item.id}`} className="bg-slate-950 border border-slate-850 rounded-xl p-3 flex justify-between items-center text-xs">
                                    <div>
                                        <strong className="block text-slate-200">{item.title}</strong>
                                        <span className="text-slate-400 mt-0.5 block">{item.problem}</span>
                                    </div>
                                    <button
                                        onClick={() => {
                                            setActiveIssueId(item.id);
                                            setSelectedActionType(null);
                                            setUnknownStep(1);
                                        }}
                                        className="px-2.5 py-1.5 bg-indigo-600/30 hover:bg-indigo-600 border border-indigo-900 text-indigo-300 hover:text-white rounded font-semibold transition"
                                    >
                                        Resolve Now
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* decisions Log / Review Decisions Panel */}
                {decisions.length > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">Review Decisions</h2>
                        <div className="flex flex-col gap-2 text-xs">
                            {decisions.map(d => (
                                <div key={d.id} className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg flex justify-between items-center">
                                    <span className="text-slate-300">✓ {d.description}</span>
                                    <div className="flex gap-2">
                                        <button
                                            onClick={() => handleUndoDecision(d.id)}
                                            className="text-xs text-indigo-400 font-semibold hover:underline"
                                        >
                                            {d.type === "map" ? "Edit Mapping" : d.type === "request" ? "Edit Request" : "Reopen"}
                                        </button>
                                        <button
                                            onClick={() => handleUndoDecision(d.id)}
                                            className="text-xs text-slate-500 font-semibold hover:underline"
                                        >
                                            Undo
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Suggested Charges Accordion */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                    <button
                        onClick={() => setShowSuggested(!showSuggested)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
                    >
                        <div className="flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-indigo-400" />
                            <span>Suggested Charges ({suggestedCharges.length})</span>
                        </div>
                        {showSuggested ? <ChevronUp className="h-5 w-5 text-slate-400" /> : <ChevronDown className="h-5 w-5 text-slate-400" />}
                    </button>
                    
                    {showSuggested && (
                        <div className="border-t border-slate-800 p-5 bg-slate-900/40">
                            <div className="divide-y divide-slate-800/60 text-sm">
                                {suggestedCharges.map(charge => (
                                    <div key={charge.id} className="py-3 flex items-center justify-between gap-4">
                                        <div className="flex items-center gap-3">
                                            <input
                                                type="checkbox"
                                                checked={charge.include_in_totals}
                                                onChange={() => toggleIncludeInTotals(charge.id)}
                                                disabled={isReviewLocked}
                                                className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-indigo-500 w-4 h-4"
                                            />
                                            <div>
                                                <span className="font-semibold block text-slate-100">{charge.display_label}</span>
                                                <span className="text-xs text-slate-400 block mt-0.5">
                                                    Billing Code: <strong className="font-mono text-indigo-300">{charge.suggested_product_code || "Unmapped"}</strong>
                                                    {charge.rate && ` | ${humanizeRate(charge.rate, charge.unit, charge.display_label)}`}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <span className="font-bold text-slate-100">{charge.currency} {Number(charge.amount).toFixed(2)}</span>
                                            <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                                charge.status === "accepted_by_user" ? "bg-emerald-950/40 text-emerald-400 border border-emerald-900/60" :
                                                charge.status === "suggested" ? "bg-slate-805 text-slate-300 border border-slate-700" :
                                                charge.status === "ignored" ? "bg-red-950/40 text-red-400 border border-red-900/40" :
                                                charge.status === "pending_product_code" ? "bg-indigo-950/40 text-indigo-400 border border-indigo-900/60" :
                                                "bg-amber-950/40 text-amber-300 border border-amber-900/60"
                                            }`}>
                                                {friendlyStatus(charge.status)}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Commercial Terms Accordion */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                    <button
                        onClick={() => setShowTerms(!showTerms)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
                    >
                        <div className="flex items-center gap-2">
                            <FileText className="h-5 w-5 text-indigo-400" />
                            <span>Commercial Terms ({draftQuote.commercial_terms.length})</span>
                        </div>
                        {showTerms ? <ChevronUp className="h-5 w-5 text-slate-400" /> : <ChevronDown className="h-5 w-5 text-slate-400" />}
                    </button>
                    
                    {showTerms && (
                        <div className="border-t border-slate-800 p-5 bg-slate-900/40">
                            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                                {draftQuote.commercial_terms.map((term, i) => (
                                    <div key={i} className="bg-slate-950 border border-slate-800 p-4 rounded-xl">
                                        <div className="flex justify-between items-center gap-2 mb-2">
                                            <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">{term.type.replace("_", " ")}</span>
                                            <span className="text-[10px] text-slate-400">Value: {term.normalized_value ? String(term.normalized_value) : "Null"}</span>
                                        </div>
                                        <p className="text-xs text-slate-300 italic">&quot;{term.text}&quot;</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* Totals split display warnings */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                    <button
                        onClick={() => setShowTotalsPanel(!showTotalsPanel)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
                    >
                        <div className="flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-indigo-400" />
                            <span>Verification Warnings & Totals</span>
                        </div>
                        {showTotalsPanel ? <ChevronUp className="h-5 w-5 text-slate-400" /> : <ChevronDown className="h-5 w-5 text-slate-400" />}
                    </button>
                    
                    {showTotalsPanel && (
                        <div className="border-t border-slate-800 p-5 bg-slate-900/40 flex flex-col gap-4">
                            {uniqueCurrencies.length > 1 ? (
                                <div className="bg-amber-955 border border-amber-900/60 rounded-xl p-4 flex flex-col gap-2">
                                    <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                                        <AlertCircle className="h-4 w-4" />
                                        <span>Totals Need Review</span>
                                    </div>
                                    <p className="text-xs text-slate-300">
                                        Reason: This quote contains multiple currencies. A single calculations total is not safe to display.
                                    </p>
                                    
                                    <div className="mt-2 divide-y divide-slate-800 text-xs">
                                        {Object.entries(subtotals).map(([curr, sum]) => (
                                            <div key={curr} className="py-1.5 flex justify-between font-mono">
                                                <span className="text-slate-400">{curr} subtotal:</span>
                                                <span className="text-slate-200">{sum.toFixed(2)}</span>
                                            </div>
                                        ))}
                                        <div className="py-2 flex justify-between font-mono text-sm border-t border-slate-700">
                                            <span className="text-indigo-300 font-semibold">Supplier extracted total:</span>
                                            <span className="text-indigo-200 font-bold">USD {draftQuote.totals_validation.extracted_total?.toFixed(2)}</span>
                                        </div>
                                    </div>
                                </div>
                            ) : (
                                <div className="flex flex-col gap-3">
                                    <div className="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm">
                                        <span className="text-slate-400">Calculated sum difference:</span>
                                        <div className="flex items-center gap-2">
                                            <span className={`font-semibold ${draftQuote.totals_validation.difference ? "text-red-400" : "text-emerald-400"}`}>
                                                USD {draftQuote.totals_validation.difference?.toFixed(2) || "0.00"}
                                            </span>
                                            <button 
                                                onClick={() => setExplainTotals(!explainTotals)}
                                                className="text-xs text-indigo-400 font-semibold hover:underline"
                                            >
                                                [Explain]
                                            </button>
                                        </div>
                                    </div>

                                    {explainTotals && (
                                        <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-2 text-xs">
                                            <div className="flex justify-between">
                                                <span className="text-slate-400">Calculated Sum:</span>
                                                <span>USD {draftQuote.totals_validation.calculated_total?.toFixed(2)}</span>
                                            </div>
                                            <div className="flex justify-between">
                                                <span className="text-slate-400">Extracted Total from document:</span>
                                                <span>USD {draftQuote.totals_validation.extracted_total?.toFixed(2)}</span>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    )}
                </div>

                {/* Muted Ignored Items */}
                {ignoredItems.length > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">Ignored Items</h2>
                        <div className="flex flex-col gap-2.5">
                            {ignoredItems.map(item => (
                                <div key={item.id} className="bg-slate-950 border border-slate-850 rounded-xl p-3 text-xs flex justify-between items-center">
                                    <div>
                                        <span className="text-[10px] text-slate-500 font-bold block uppercase tracking-wider">Reason: {item.ignored_reason}</span>
                                        <p className="text-slate-400 italic font-mono mt-1">&quot;{item.raw_text}&quot;</p>
                                    </div>
                                    <button
                                        onClick={() => handleUndoDecision(item.id)}
                                        className="text-xs text-indigo-400 font-semibold hover:underline"
                                    >
                                        Reopen
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Final Checklist Review */}
                <div className="mt-4 flex flex-col items-center gap-4 border-t border-slate-800 pt-6">
                    
                    <div className="w-full bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs flex flex-col gap-2.5">
                        <h3 className="font-bold text-slate-300 uppercase tracking-wider mb-1">Final Review Checklist</h3>
                        
                        <div className="flex items-center justify-between border-b border-slate-850 pb-2">
                            <div>
                                <span className="text-slate-200 block font-semibold">All review items resolved</span>
                                <span className="text-slate-400 text-[10px]">{checklistIssuesResolved ? "Complete" : `${combinedUnresolved.length} charges still need action.`}</span>
                            </div>
                            <span className={checklistIssuesResolved ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistIssuesResolved ? "Complete" : "Pending"}
                            </span>
                        </div>
                        
                        <div className="flex items-center justify-between border-b border-slate-850 pb-2">
                            <div>
                                <span className="text-slate-200 block font-semibold">No unknown commercial charges remain</span>
                                <span className="text-slate-400 text-[10px]">{checklistNoUnknown ? "Complete" : "Unmapped extracted charge block exists."}</span>
                            </div>
                            <span className={checklistNoUnknown ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistNoUnknown ? "Complete" : "Pending"}
                            </span>
                        </div>

                        <div className="flex items-center justify-between pb-2">
                            <div>
                                <span className="text-slate-200 block font-semibold">No included charge is missing a ProductCode mapping</span>
                                <span className="text-slate-400 text-[10px]">{checklistProductCodesVerified ? "Complete" : "Include charge has no mapped billing code."}</span>
                            </div>
                            <span className={checklistProductCodesVerified ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistProductCodesVerified ? "Complete" : "Pending"}
                            </span>
                        </div>
                    </div>

                    {!canFinishReview && !canUsePrototypeOverride && (
                        <div className="w-full bg-red-950/20 border border-red-900/60 rounded-xl p-4 text-xs text-red-200">
                            <span className="font-bold block mb-1">Finish Review unavailable</span>
                            <span>Resolve all pending issues and verify ProductCode mappings to complete review.</span>
                        </div>
                    )}

                    <div className="w-full flex flex-col sm:flex-row justify-between items-center gap-4">
                        <div className="flex items-center gap-2 text-xs">
                            <input 
                                type="checkbox" 
                                id="proto-override" 
                                checked={prototypeOverride}
                                onChange={() => setPrototypeOverride(!prototypeOverride)}
                                className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-indigo-500 w-4.5 h-4.5"
                            />
                            <label htmlFor="proto-override" className="text-slate-400 cursor-pointer font-medium select-none">
                                Prototype override only — not available for production.
                            </label>
                        </div>

                        <button
                            disabled={isReviewLocked || (!canFinishReview && !canUsePrototypeOverride)}
                            onClick={handleFinalizeReview}
                            className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-xl font-bold text-sm shadow-xl shadow-indigo-900/40 w-full sm:w-auto text-center transition"
                        >
                            {isReviewLocked ? "Review Finalized" : "Finalize Review"}
                        </button>
                    </div>
                    
                    <div className="text-center text-xs text-slate-500 mt-2">
                        Prototype only — Changes made will not be permanently saved.
                    </div>
                </div>

            </div>
        </div>
    );
}
