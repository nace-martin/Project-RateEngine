"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle, ChevronDown, ChevronUp, ShieldAlert, FileText } from "lucide-react";
import { hardCaseAirImportData } from "../../data/hardCaseAirImport";
import { DraftCharge, DraftChargeStatus, Evidence } from "../../lib/draft-quote-types";

// Friendly display name helper for statuses
function friendlyStatus(status: string): string {
    switch (status) {
        case "accepted_by_user":
            return "Accepted";
        case "suggested":
            return "Suggested";
        case "needs_review":
            return "Needs Review";
        case "unclassified":
            return "Unknown Charge";
        case "ignored":
            return "Ignored";
        case "pending_product_code":
            return "Pending Product Code Approval";
        default:
            return status;
    }
}

// Humanized rate parser helper
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

interface ResolveIssue {
    id: string;
    type: "review_item" | "unknown_charge";
    title: string;
    problem: string;
    charge?: DraftCharge;
    itemDetails?: {
        id: string;
        raw_text: string;
        evidence: Evidence | null;
        review_reason: string;
    };
}

export function ExceptionWorkspace() {
    // Single source of truth state for mock data
    const [draftQuote, setDraftQuote] = useState(hardCaseAirImportData);
    
    // Accordion UI toggles
    const [showSuggested, setShowSuggested] = useState(false);
    const [showTerms, setShowTerms] = useState(false);
    const [showTotalsPanel, setShowTotalsPanel] = useState(false);
    const [explainTotals, setExplainTotals] = useState(false);

    // Resolution mode workflow states
    const [activeIssueIndex, setActiveIssueIndex] = useState(0);
    const [selectedActionType, setSelectedActionType] = useState<string | null>(null);

    // Request new ProductCode modal/inline form fields
    const [reqLabel, setReqLabel] = useState("");
    const [reqSource, setReqSource] = useState("");
    const [reqCurrency, setReqCurrency] = useState("");
    const [reqAmount, setReqAmount] = useState("");

    // Add Unknown Charge inline form fields
    const [addName, setAddName] = useState("");
    const [addBucket, setAddBucket] = useState("origin_charges");
    const [addCurrency, setAddCurrency] = useState("SGD");
    const [addAmount, setAddAmount] = useState("");
    const [addUnit, setAddUnit] = useState("set");
    const [addProductCode, setAddProductCode] = useState("");

    // Prototype override toggle
    const [prototypeOverride, setPrototypeOverride] = useState(false);

    // Dynamic resolution queue matching (only unresolved items from reviewQueue + unclassifiedItems)
    const combinedUnresolved: ResolveIssue[] = [
        ...draftQuote.review_queue.map(item => ({
            id: item.id,
            type: "review_item" as const,
            title: item.id === "chg-002" ? "Fuel Surcharge" : "Security Charge",
            problem: item.id === "chg-002" 
                ? "No matching ProductCode found in RateEngine." 
                : "Currency was inherited from shipment context and needs validation.",
            charge: draftQuote.suggested_charges.find(c => c.id === item.id)
        })),
        ...draftQuote.unclassified_items.map(item => ({
            id: item.id,
            type: "unknown_charge" as const,
            title: "Unknown Charge Block",
            problem: "Commercial text block extracted from quote document could not be safely mapped to a standard charge line.",
            itemDetails: item
        }))
    ];

    const currentIssue = combinedUnresolved[activeIssueIndex] || null;

    // Actions
    const handleMapProductCode = (chargeId: string, productCode: string) => {
        setDraftQuote(prev => {
            const updated = prev.suggested_charges.map(c => 
                c.id === chargeId ? { ...c, suggested_product_code: productCode, status: "accepted_by_user" as DraftChargeStatus } : c
            );
            return {
                ...prev,
                suggested_charges: updated,
                review_queue: prev.review_queue.filter(q => q.id !== chargeId)
            };
        });
        setSelectedActionType(null);
    };

    const handleOpenRequestProductCode = (charge: DraftCharge) => {
        setReqLabel(charge.display_label);
        setReqSource(charge.evidence?.source_text || charge.raw_label);
        setReqCurrency(charge.currency);
        setReqAmount(String(charge.amount));
        setSelectedActionType("request_product_code");
    };

    const handleSubmitProductCodeRequest = (chargeId: string) => {
        setDraftQuote(prev => {
            const updated = prev.suggested_charges.map(c => 
                c.id === chargeId ? { ...c, status: "pending_product_code" as DraftChargeStatus } : c
            );
            return {
                ...prev,
                suggested_charges: updated,
                review_queue: prev.review_queue.filter(q => q.id !== chargeId)
            };
        });
        setSelectedActionType(null);
        alert(`Product code request submitted locally for ${reqLabel}. This charge is now pending code approval.`);
    };

    const handleIgnoreCharge = (chargeId: string, charge: DraftCharge) => {
        setDraftQuote(prev => {
            const updatedSuggested = prev.suggested_charges.map(c => 
                c.id === chargeId ? { ...c, status: "ignored" as DraftChargeStatus, include_in_totals: false } : c
            );
            const updatedIgnored = [
                ...prev.ignored_items,
                {
                    id: chargeId,
                    raw_text: charge.raw_label,
                    ignored_reason: "Operator chose to exclude this charge line during review",
                    evidence: charge.evidence
                }
            ];
            return {
                ...prev,
                suggested_charges: updatedSuggested,
                ignored_items: updatedIgnored,
                review_queue: prev.review_queue.filter(q => q.id !== chargeId)
            };
        });
        setSelectedActionType(null);
    };

    const handleIgnoreUnknownCharge = (itemId: string, rawText: string) => {
        setDraftQuote(prev => {
            const updatedIgnored = [
                ...prev.ignored_items,
                {
                    id: itemId,
                    raw_text: rawText,
                    ignored_reason: "Operator marked unknown charge text block as non-commercial text",
                    evidence: prev.unclassified_items.find(i => i.id === itemId)?.evidence || null
                }
            ];
            return {
                ...prev,
                ignored_items: updatedIgnored,
                unclassified_items: prev.unclassified_items.filter(i => i.id !== itemId)
            };
        });
        setSelectedActionType(null);
    };

    const handleAddUnknownAsCharge = (itemId: string) => {
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
            evidence: draftQuote.unclassified_items.find(i => i.id === itemId)?.evidence || null,
            similarity_group_id: null,
            correction_actions: []
        };

        setDraftQuote(prev => {
            const updatedSuggested = [...prev.suggested_charges, newCharge];
            const updatedQueue = [...prev.review_queue];
            if (!addProductCode) {
                updatedQueue.push({
                    id: newChargeId,
                    type: "charge_needs_review",
                    message: "Newly added charge line requires a valid ProductCode mapping."
                });
            }
            return {
                ...prev,
                suggested_charges: updatedSuggested,
                review_queue: updatedQueue,
                unclassified_items: prev.unclassified_items.filter(i => i.id !== itemId)
            };
        });

        setSelectedActionType(null);
        alert(`Successfully added unknown charge block as "${addName}".`);
    };

    const toggleIncludeInTotals = (chargeId: string) => {
        setDraftQuote(prev => {
            const updated = prev.suggested_charges.map(c => 
                c.id === chargeId ? { ...c, include_in_totals: !c.include_in_totals } : c
            );
            return {
                ...prev,
                suggested_charges: updated
            };
        });
    };

    // Calculate totals dynamically split by currency
    const activeCharges = draftQuote.suggested_charges.filter(c => c.include_in_totals && c.status !== "ignored");
    const uniqueCurrencies = Array.from(new Set(activeCharges.map(c => c.currency)));
    const subtotals = uniqueCurrencies.reduce((acc, curr) => {
        acc[curr] = activeCharges.filter(c => c.currency === curr).reduce((sum, c) => sum + c.amount, 0);
        return acc;
    }, {} as Record<string, number>);

    // Checklist statuses
    const checklistIssuesResolved = combinedUnresolved.length === 0;
    const checklistNoUnknown = draftQuote.unclassified_items.length === 0;
    const checklistProductCodesVerified = draftQuote.suggested_charges
        .filter(c => c.include_in_totals && c.status !== "ignored")
        .every(c => c.suggested_product_code !== null && c.status !== ("pending_product_code" as DraftChargeStatus));
    
    const canFinishReview = checklistIssuesResolved && checklistNoUnknown && checklistProductCodesVerified;

    return (
        <div className="min-h-screen bg-slate-955 text-slate-100 p-6 font-sans">
            <div className="max-w-4xl mx-auto flex flex-col gap-6">
                
                {/* Header Summary */}
                <div className="bg-slate-905 border border-slate-800 rounded-2xl p-6 shadow-xl flex justify-between items-center">
                    <div>
                        <h1 className="text-xl font-bold text-slate-50">Review Workspace</h1>
                        <p className="text-sm text-slate-400 mt-1">Guided exception workflow for operators</p>
                    </div>
                    <div className="text-right">
                        <span className="text-xs text-slate-500 block">Remaining Items</span>
                        <span className="text-lg font-bold text-amber-400">{combinedUnresolved.length} issues left</span>
                    </div>
                </div>

                {/* 1. Resolve Mode Card */}
                {currentIssue ? (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
                        <div className="flex justify-between items-center mb-4 pb-3 border-b border-slate-800">
                            <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
                                Issue {activeIssueIndex + 1} of {combinedUnresolved.length}
                            </span>
                            <div className="flex gap-1.5">
                                <button
                                    disabled={activeIssueIndex === 0}
                                    onClick={() => { setActiveIssueIndex(prev => prev - 1); setSelectedActionType(null); }}
                                    className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded text-xs text-slate-400 disabled:opacity-40"
                                >
                                    Previous
                                </button>
                                <button
                                    disabled={activeIssueIndex >= combinedUnresolved.length - 1}
                                    onClick={() => { setActiveIssueIndex(prev => prev + 1); setSelectedActionType(null); }}
                                    className="px-2.5 py-1 bg-slate-950 border border-slate-800 rounded text-xs text-slate-400 disabled:opacity-40"
                                >
                                    Next
                                </button>
                            </div>
                        </div>

                        <h2 className="text-lg font-bold text-slate-50 mb-1">{currentIssue.title}</h2>
                        <p className="text-xs text-slate-400 mb-4">{currentIssue.problem}</p>

                        {/* Evidence Display (Contextual) */}
                        {currentIssue.type === "review_item" && currentIssue.charge && (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl mb-6">
                                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">Source Quote Evidence</div>
                                <p className="text-sm font-mono text-slate-200 italic mb-2">
                                    &quot;{currentIssue.charge.evidence?.source_text || currentIssue.charge.raw_label}&quot;
                                </p>
                                <span className="text-xs text-slate-400">
                                    Detected amount: {currentIssue.charge.currency} {currentIssue.charge.amount}
                                </span>
                            </div>
                        )}

                        {currentIssue.type === "unknown_charge" && currentIssue.itemDetails && (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl mb-6">
                                <div className="text-[10px] text-slate-500 uppercase tracking-wider font-bold mb-1">Extracted Text block</div>
                                <p className="text-sm font-mono text-slate-200 italic">
                                    &quot;{currentIssue.itemDetails.raw_text}&quot;
                                </p>
                            </div>
                        )}

                        {/* Guided Actions */}
                        {selectedActionType === null ? (
                            <div className="flex flex-wrap gap-2">
                                {currentIssue.type === "review_item" && currentIssue.charge ? (
                                    <>
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
                                        <button
                                            onClick={() => handleIgnoreCharge(currentIssue.id, currentIssue.charge!)}
                                            className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-red-400 rounded-lg text-xs font-semibold transition"
                                        >
                                            Ignore Charge
                                        </button>
                                    </>
                                ) : currentIssue.itemDetails ? (
                                    <>
                                        <button
                                            onClick={() => setSelectedActionType("add_charge")}
                                            className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold transition"
                                        >
                                            Add as Charge
                                        </button>
                                        <button
                                            onClick={() => setSelectedActionType("map_existing")}
                                            className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-slate-200 rounded-lg text-xs font-semibold transition"
                                        >
                                            Map to Existing ProductCode
                                        </button>
                                        <button
                                            onClick={() => handleIgnoreUnknownCharge(currentIssue.id, currentIssue.itemDetails!.raw_text)}
                                            className="px-4 py-2 bg-slate-950 hover:bg-slate-900 border border-slate-800 text-red-400 rounded-lg text-xs font-semibold transition"
                                        >
                                            Ignore as Non-Commercial
                                        </button>
                                    </>
                                ) : null}
                            </div>
                        ) : selectedActionType === "map_existing" ? (
                            <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
                                <h3 className="text-xs uppercase font-bold text-indigo-400">Select Existing Billing Code</h3>
                                <div className="flex gap-2">
                                    <select
                                        onChange={e => {
                                            if (e.target.value) {
                                                handleMapProductCode(currentIssue.id, e.target.value);
                                            }
                                        }}
                                        className="text-xs bg-slate-900 border border-slate-800 rounded p-2 text-slate-200 grow"
                                    >
                                        <option value="">-- Choose Approved Billing Code --</option>
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
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                    <div>
                                        <label className="text-slate-500 block mb-1">Charge Label</label>
                                        <input type="text" value={reqLabel} onChange={e => setReqLabel(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Source Text</label>
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
                                <h3 className="text-xs uppercase font-bold text-indigo-400">Add Unknown Block as Charge Line</h3>
                                <div className="grid grid-cols-2 gap-3 text-xs">
                                    <div>
                                        <label className="text-slate-500 block mb-1">Charge Name</label>
                                        <input type="text" value={addName} onChange={e => setAddName(e.target.value)} placeholder="e.g. Handling Fee" className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Bucket</label>
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
                                        <label className="text-slate-500 block mb-1">Unit</label>
                                        <input type="text" value={addUnit} onChange={e => setAddUnit(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                                    </div>
                                    <div>
                                        <label className="text-slate-500 block mb-1">Product Code (Optional)</label>
                                        <input type="text" value={addProductCode} onChange={e => setAddProductCode(e.target.value)} placeholder="Map directly to code if known" className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
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
                            <p className="text-xs text-slate-400 mt-1">Review validation checks below and complete the final checklist.</p>
                        </div>
                    </div>
                )}

                {/* 2. Suggested Charges Accordion */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                    <button
                        onClick={() => setShowSuggested(!showSuggested)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
                    >
                        <div className="flex items-center gap-2">
                            <CheckCircle className="h-5 w-5 text-indigo-400" />
                            <span>Suggested Charges ({draftQuote.suggested_charges.length})</span>
                        </div>
                        {showSuggested ? <ChevronUp className="h-5 w-5 text-slate-400" /> : <ChevronDown className="h-5 w-5 text-slate-400" />}
                    </button>
                    
                    {showSuggested && (
                        <div className="border-t border-slate-800 p-5 bg-slate-900/40">
                            <div className="divide-y divide-slate-800/60 text-sm">
                                {draftQuote.suggested_charges.map(charge => (
                                    <div key={charge.id} className="py-3 flex items-center justify-between gap-4">
                                        <div className="flex items-center gap-3">
                                            <input
                                                type="checkbox"
                                                checked={charge.include_in_totals}
                                                onChange={() => toggleIncludeInTotals(charge.id)}
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
                                                charge.status === "suggested" ? "bg-slate-800 text-slate-300 border border-slate-700" :
                                                charge.status === "ignored" ? "bg-red-950/40 text-red-400 border border-red-900/40" :
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

                {/* 3. Commercial Terms Accordion */}
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

                {/* 4. Totals & Currencies Accordion */}
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
                                <div className="bg-amber-950/20 border border-amber-900/60 rounded-xl p-4 flex flex-col gap-2">
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

                {/* 5. Ignored Items section */}
                {draftQuote.ignored_items.length > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-base font-bold text-slate-400 mb-3">Ignored Items</h2>
                        <div className="flex flex-col gap-3">
                            {draftQuote.ignored_items.map(item => (
                                <div key={item.id} className="bg-slate-950 border border-slate-850 rounded-xl p-3 text-xs flex flex-col gap-1.5">
                                    <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Reason: {item.ignored_reason}</span>
                                    <p className="text-slate-400 italic font-mono bg-slate-950 p-2 rounded">
                                        &quot;{item.raw_text}&quot;
                                    </p>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* 6. Finish Review & CTA Bar */}
                <div className="mt-4 flex flex-col items-center gap-4 border-t border-slate-800 pt-6">
                    
                    {/* Resolution Checklist */}
                    <div className="w-full bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs flex flex-col gap-2">
                        <h3 className="font-bold text-slate-300 uppercase tracking-wider mb-2">Final Review Checklist</h3>
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400">All review items resolved:</span>
                            <span className={checklistIssuesResolved ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistIssuesResolved ? "Verified" : "Pending"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400">No unknown commercial charges remain:</span>
                            <span className={checklistNoUnknown ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistNoUnknown ? "Verified" : "Pending"}
                            </span>
                        </div>
                        <div className="flex items-center justify-between">
                            <span className="text-slate-400">No included charge is missing a ProductCode mapping:</span>
                            <span className={checklistProductCodesVerified ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                                {checklistProductCodesVerified ? "Verified" : "Pending"}
                            </span>
                        </div>
                    </div>

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
                            disabled={!canFinishReview && !prototypeOverride}
                            onClick={() => alert("Review Complete! Suggestions accepted and finalized locally.")}
                            className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-xl font-bold text-sm shadow-xl shadow-indigo-900/40 w-full sm:w-auto text-center transition"
                        >
                            Finish Review
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
