"use client";

import React, { useState } from "react";
import { CheckCircle, ChevronDown, ChevronUp, Info, ShieldAlert, FileText, ArrowLeft } from "lucide-react";
import { DraftQuote } from "../../lib/draft-quote-types";
import { humanizeRate, friendlyStatus } from "@/lib/spot-workspace-helpers";
import { MapExistingForm } from "./workspace/MapExistingForm";
import { RequestProductCodeForm } from "./workspace/RequestProductCodeForm";
import { AddChargeForm } from "./workspace/AddChargeForm";
import { useSpotResolutionWorkflow } from "./workspace/useSpotResolutionWorkflow";
import { NeedsAttentionPanel } from "./workspace/NeedsAttentionPanel";
import { ReviewDecisionsPanel } from "./workspace/ReviewDecisionsPanel";
import { VerificationWarningsPanel } from "./workspace/VerificationWarningsPanel";
import { IgnoredItemsPanel } from "./workspace/IgnoredItemsPanel";
import { FinalReviewPanel } from "./workspace/FinalReviewPanel";

export function ExceptionWorkspace({ initialData, isLive = false, envelopeId }: { initialData: DraftQuote; isLive?: boolean; envelopeId?: string }) {
    const [draftQuote] = useState(initialData);
    const [explainTotals, setExplainTotals] = useState(false);

    // Accordions local UI state
    const [showSuggested, setShowSuggested] = useState(false);
    const [showTerms, setShowTerms] = useState(false);
    const [showTotalsPanel, setShowTotalsPanel] = useState(false);

    // Consume the custom workflow hook
    const { state, derived, actions } = useSpotResolutionWorkflow({
        initialData,
        isLive,
        envelopeId
    });

    const {
        suggestedCharges,
        ignoredItems,
        decisions,
        reviewSession,
        selectedActionType,
        actionMessage,
        prototypeOverride,
        productCodes,
        isLoadingProductCodes,
        productCodeLoadError
    } = state;

    const {
        combinedUnresolved,
        currentIssue,
        uniqueCurrencies,
        subtotals,
        checklistIssuesResolved,
        checklistNoUnknown,
        checklistProductCodesVerified,
        canFinishReview,
        isReviewLocked,
        canUsePrototypeOverride,
        nextStepGuidance
    } = derived;

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
                        <button onClick={actions.dismissActionMessage} className="text-emerald-500 hover:text-emerald-300 font-bold">Dismiss</button>
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
                                onClick={actions.toggleHelpText}
                                className="text-xs text-indigo-400 font-semibold hover:underline flex items-center gap-1"
                            >
                                {state.showHelpText ? "Hide explanation" : "Why am I seeing this?"}
                            </button>
                            {state.showHelpText && (
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
                                                        onClick={actions.openMapExisting}
                                                        className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Map to existing ProductCode
                                                    </button>
                                                    <button
                                                        onClick={() => actions.openRequestProductCode(currentIssue.charge!)}
                                                        className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-200 rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Edit and resubmit request
                                                    </button>
                                                    <button
                                                        onClick={() => actions.ignoreCharge(currentIssue.id, currentIssue.charge!)}
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
                                                        onClick={() => actions.useApprovedProductCode(currentIssue.id, currentIssue.charge!)}
                                                        className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition text-xs"
                                                    >
                                                        Use Approved ProductCode ({currentIssue.charge.approved_product_code})
                                                    </button>
                                                </div>
                                            </div>
                                        )}

                                        <div className="flex flex-wrap gap-2">
                                            <button
                                                onClick={actions.openMapExisting}
                                                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition"
                                            >
                                                Map to Existing ProductCode
                                            </button>
                                            <button
                                                onClick={() => actions.openRequestProductCode(currentIssue.charge!)}
                                                className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-200 rounded-lg text-xs font-semibold transition"
                                            >
                                                Request New ProductCode
                                            </button>
                                            {currentIssue.charge.suggested_product_code && !currentIssue.charge.correction_actions?.includes("APPROVED_PRODUCTCODE_AVAILABLE") && (
                                                <button
                                                    onClick={() => actions.acceptSuggestedMapping(currentIssue.id, currentIssue.title, currentIssue.charge!.suggested_product_code!)}
                                                    className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold transition"
                                                >
                                                    Accept Suggested Mapping ({currentIssue.charge.suggested_product_code})
                                                </button>
                                            )}
                                            <button
                                                onClick={() => actions.ignoreCharge(currentIssue.id, currentIssue.charge!)}
                                                className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-red-400 rounded-lg text-xs font-semibold transition"
                                            >
                                                Ignore as Non-Commercial
                                            </button>
                                        </div>
                                    </div>
                                ) : currentIssue.type === "unknown_charge" ? (
                                    /* Unknown Charge Guided flow wizard */
                                    <div className="flex flex-col gap-4">
                                        {state.unknownWizard.step === 1 ? (
                                            <div className="flex flex-col gap-2.5">
                                                <div className="text-xs font-semibold text-slate-300">Step 1: What is this text block?</div>
                                                <div className="flex flex-col sm:flex-row gap-2">
                                                    <button
                                                        onClick={() => actions.classifyUnknown("charge")}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs font-semibold text-slate-200 text-left grow"
                                                    >
                                                        A real charge line
                                                    </button>
                                                    <button
                                                        onClick={() => actions.classifyUnknown("note")}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs font-semibold text-slate-200 text-left grow"
                                                    >
                                                        A notes annotation or cargo condition
                                                    </button>
                                                    <button
                                                        onClick={() => actions.ignoreUnknownCharge(currentIssue.id, currentIssue.itemDetails!.raw_text)}
                                                        className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-red-900 hover:text-red-400 rounded-lg text-xs font-semibold text-red-400 text-left grow"
                                                    >
                                                        Not relevant (Ignore)
                                                    </button>
                                                </div>
                                            </div>
                                        ) : state.unknownWizard.step === 2 ? (
                                            <div className="flex flex-col gap-3">
                                                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                                                    <button onClick={actions.returnToUnknownClassification} className="hover:underline flex items-center gap-0.5 text-indigo-400 font-semibold">
                                                        <ArrowLeft className="h-3.5 w-3.5" /> Back
                                                    </button>
                                                    <span>| Classification: {state.unknownWizard.classification}</span>
                                                </div>
                                                
                                                {state.unknownWizard.classification === "charge" ? (
                                                    <div className="flex flex-col gap-2.5">
                                                        <div className="text-xs font-semibold text-slate-300">Step 2: How should it be mapped?</div>
                                                        <div className="flex flex-col sm:flex-row gap-2">
                                                            <button
                                                                onClick={actions.openMapExisting}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs text-left grow text-slate-200"
                                                            >
                                                                Map to an existing billing code
                                                            </button>
                                                            <button
                                                                onClick={() => actions.openUnknownProductCodeRequest(currentIssue.itemDetails!.raw_text)}
                                                                className="px-4 py-2 bg-slate-950 border border-slate-800 hover:border-slate-600 rounded-lg text-xs text-left grow text-slate-200"
                                                            >
                                                                Request new billing code
                                                            </button>
                                                            <button
                                                                onClick={() => actions.openAddUnknownCharge("New Charge", "0")}
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
                                                                onClick={() => actions.approveUnknownNote(currentIssue.id, currentIssue.itemDetails!.raw_text)}
                                                                className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 rounded text-xs text-white font-semibold"
                                                            >
                                                                Approve & File Note
                                                            </button>
                                                            <button
                                                                onClick={() => actions.ignoreUnknownCharge(currentIssue.id, currentIssue.itemDetails!.raw_text)}
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
                            <MapExistingForm
                                productCodes={productCodes}
                                isLoadingProductCodes={isLoadingProductCodes}
                                productCodeLoadError={productCodeLoadError}
                                onRetry={actions.retryProductCodeLoad}
                                onMap={(productCode) =>
                                    currentIssue.type === "unknown_charge"
                                        ? actions.classifyUnknownAsExistingCharge(
                                              currentIssue.id,
                                              productCode,
                                              currentIssue.title
                                          )
                                        : actions.mapProductCode(
                                              currentIssue.id,
                                              productCode,
                                              currentIssue.title
                                          )
                                }
                                onCancel={actions.cancelAction}
                            />
                        ) : selectedActionType === "request_product_code" ? (
                            <RequestProductCodeForm
                                reqLabel={state.requestForm.label}
                                onReqLabelChange={(val) => actions.updateRequestForm({ label: val })}
                                reqSource={state.requestForm.source}
                                onReqSourceChange={(val) => actions.updateRequestForm({ source: val })}
                                reqCurrency={state.requestForm.currency}
                                onReqCurrencyChange={(val) => actions.updateRequestForm({ currency: val })}
                                reqAmount={state.requestForm.amount}
                                onReqAmountChange={(val) => actions.updateRequestForm({ amount: val })}
                                reqBucket={state.requestForm.bucket}
                                onReqBucketChange={(val) => actions.updateRequestForm({ bucket: val })}
                                reqUnit={state.requestForm.unit}
                                onReqUnitChange={(val) => actions.updateRequestForm({ unit: val })}
                                onSubmit={() =>
                                    actions.submitProductCodeRequest(currentIssue.id)
                                }
                                onCancel={actions.cancelAction}
                            />
                        ) : selectedActionType === "add_charge" ? (
                            <AddChargeForm
                                addName={state.addChargeForm.name}
                                onAddNameChange={(val) => actions.updateAddChargeForm({ name: val })}
                                addBucket={state.addChargeForm.bucket}
                                onAddBucketChange={(val) => actions.updateAddChargeForm({ bucket: val })}
                                addCurrency={state.addChargeForm.currency}
                                onAddCurrencyChange={(val) => actions.updateAddChargeForm({ currency: val })}
                                addAmount={state.addChargeForm.amount}
                                onAddAmountChange={(val) => actions.updateAddChargeForm({ amount: val })}
                                addUnit={state.addChargeForm.unit}
                                onAddUnitChange={(val) => actions.updateAddChargeForm({ unit: val })}
                                addProductCode={state.addChargeForm.productCode}
                                onAddProductCodeChange={(val) => actions.updateAddChargeForm({ productCode: val })}
                                productCodes={productCodes}
                                isLoadingProductCodes={isLoadingProductCodes}
                                productCodeLoadError={productCodeLoadError}
                                onRetryProductCodes={actions.retryProductCodeLoad}
                                onAdd={() =>
                                    actions.addUnknownAsCharge(currentIssue.id)
                                }
                                onCancel={actions.cancelAction}
                            />
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
                <NeedsAttentionPanel
                    items={combinedUnresolved}
                    onSelectIssue={actions.selectIssue}
                />

                {/* decisions Log / Review Decisions Panel */}
                <ReviewDecisionsPanel
                    decisions={decisions}
                    onUndoDecision={actions.undoDecision}
                />

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
                                                onChange={() => actions.toggleIncludeInTotals(charge.id)}
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
                <VerificationWarningsPanel
                    showTotalsPanel={showTotalsPanel}
                    onToggleTotalsPanel={() => setShowTotalsPanel(!showTotalsPanel)}
                    uniqueCurrencies={uniqueCurrencies}
                    subtotals={subtotals}
                    totalsValidation={draftQuote.totals_validation}
                    explainTotals={explainTotals}
                    onToggleExplainTotals={() => setExplainTotals(!explainTotals)}
                />

                {/* Muted Ignored Items */}
                <IgnoredItemsPanel
                    ignoredItems={ignoredItems}
                    onUndoDecision={actions.undoDecision}
                />

                {/* Final Checklist Review */}
                <FinalReviewPanel
                    checklistIssuesResolved={checklistIssuesResolved}
                    checklistNoUnknown={checklistNoUnknown}
                    checklistProductCodesVerified={checklistProductCodesVerified}
                    unresolvedCount={combinedUnresolved.length}
                    canFinishReview={canFinishReview}
                    canUsePrototypeOverride={canUsePrototypeOverride}
                    isLive={isLive}
                    isReviewLocked={isReviewLocked}
                    prototypeOverride={prototypeOverride}
                    onTogglePrototypeOverride={actions.togglePrototypeOverride}
                    onFinalizeReview={actions.finalizeReview}
                />

            </div>
        </div>
    );
}
