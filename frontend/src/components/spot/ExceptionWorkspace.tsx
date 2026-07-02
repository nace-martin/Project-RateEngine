"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle, ChevronDown, ChevronUp, Info, ShieldAlert, FileText } from "lucide-react";
import { hardCaseAirImportData } from "../../data/hardCaseAirImport";
import { Evidence, DraftChargeStatus } from "../../lib/draft-quote-types";

// Helper to humanize backend status codes to operator-friendly text
function humanizeStatus(status: string): string {
    switch (status) {
        case "accepted_by_user":
            return "Accepted";
        case "needs_review":
            return "Needs Review";
        case "unclassified":
            return "Unknown Charge";
        case "ignored":
            return "Ignored";
        case "suggested":
            return "Suggested";
        default:
            return status;
    }
}

export function ExceptionWorkspace() {
    const [draftQuote, setDraftQuote] = useState(hardCaseAirImportData);
    
    // Accordion visibility states (collapsed by default)
    const [showSuggested, setShowSuggested] = useState(false);
    const [showTerms, setShowTerms] = useState(false);
    const [showTotalsPanel, setShowTotalsPanel] = useState(false);
    
    // Detail explainers
    const [explainTotals, setExplainTotals] = useState(false);
    
    // Focused issue context to show contextual evidence inline
    const [focusedIssueId, setFocusedIssueId] = useState<string | null>("chg-002");
    
    // Bulk group action checkboxes
    const [bulkUpdateGroups, setBulkUpdateGroups] = useState<Record<string, boolean>>({});
    
    // User local overrides for code/currency
    const [productCodeOverrides, setProductCodeOverrides] = useState<Record<string, string>>({});
    const [currencyOverrides, setCurrencyOverrides] = useState<Record<string, string>>({});

    const updateChargeStatus = (chargeId: string, newStatus: string) => {
        setDraftQuote(prev => {
            const updatedCharges = prev.suggested_charges.map(c => {
                if (c.id === chargeId) {
                    const updated = { ...c, status: newStatus as DraftChargeStatus };
                    return updated;
                }
                const target = prev.suggested_charges.find(x => x.id === chargeId);
                if (target?.similarity_group_id && c.similarity_group_id === target.similarity_group_id && bulkUpdateGroups[target.similarity_group_id]) {
                    return { ...c, status: newStatus as DraftChargeStatus };
                }
                return c;
            });
            
            const calculated = updatedCharges
                .filter(c => c.status !== "ignored" && c.include_in_totals)
                .reduce((sum, c) => sum + Number(c.amount), 0);
            
            const diff = Math.abs((prev.totals_validation.extracted_total || 0) - calculated);
            
            return {
                ...prev,
                suggested_charges: updatedCharges,
                totals_validation: {
                    ...prev.totals_validation,
                    calculated_total: calculated,
                    difference: diff,
                    math_balances: diff === 0
                }
            };
        });
    };

    const toggleIncludeInTotals = (chargeId: string) => {
        setDraftQuote(prev => {
            const updated = prev.suggested_charges.map(c => 
                c.id === chargeId ? { ...c, include_in_totals: !c.include_in_totals } : c
            );
            const calculated = updated
                .filter(c => c.status !== "ignored" && c.include_in_totals)
                .reduce((sum, c) => sum + Number(c.amount), 0);
            const diff = Math.abs((prev.totals_validation.extracted_total || 0) - calculated);
            return {
                ...prev,
                suggested_charges: updated,
                totals_validation: {
                    ...prev.totals_validation,
                    calculated_total: calculated,
                    difference: diff,
                    math_balances: diff === 0
                }
            };
        });
    };

    const handleProductCodeChange = (chargeId: string, code: string) => {
        setProductCodeOverrides(prev => ({ ...prev, [chargeId]: code }));
        setDraftQuote(prev => {
            const target = prev.suggested_charges.find(c => c.id === chargeId);
            return {
                ...prev,
                suggested_charges: prev.suggested_charges.map(c => {
                    if (c.id === chargeId) {
                        return { ...c, suggested_product_code: code, product_code_conflict: false };
                    }
                    if (target?.similarity_group_id && c.similarity_group_id === target.similarity_group_id && bulkUpdateGroups[target.similarity_group_id]) {
                        return { ...c, suggested_product_code: code, product_code_conflict: false };
                    }
                    return c;
                })
            };
        });
    };

    const handleCurrencyChange = (chargeId: string, cur: string) => {
        setCurrencyOverrides(prev => ({ ...prev, [chargeId]: cur }));
        setDraftQuote(prev => {
            const target = prev.suggested_charges.find(c => c.id === chargeId);
            return {
                ...prev,
                suggested_charges: prev.suggested_charges.map(c => {
                    if (c.id === chargeId) {
                        return { ...c, currency: cur };
                    }
                    if (target?.similarity_group_id && c.similarity_group_id === target.similarity_group_id && bulkUpdateGroups[target.similarity_group_id]) {
                        return { ...c, currency: cur };
                    }
                    return c;
                })
            };
        });
    };

    // Humanize queue items
    const humanizedQueue = draftQuote.review_queue.map(q => {
        let title = "Unknown Item";
        let reason = q.message;
        let evidence: Evidence | null = null;
        
        if (q.id === "chg-002") {
            title = "Fuel Surcharge";
            reason = "Product code couldn't be automatically mapped. Select the appropriate billing code to resolve.";
            evidence = draftQuote.suggested_charges.find(c => c.id === "chg-002")?.evidence || null;
        } else if (q.id === "chg-003") {
            title = "Security Charge";
            reason = "Currency was inherited from shipment context. Please confirm the currency is correct.";
            evidence = draftQuote.suggested_charges.find(c => c.id === "chg-003")?.evidence || null;
        } else if (q.id === "unclass-001") {
            title = "Unclassified Item";
            reason = "A charge block was found in the text but could not be mapped to any standard line. Choose its classification.";
            evidence = draftQuote.unclassified_items.find(i => i.id === "unclass-001")?.evidence || null;
        }

        return {
            ...q,
            title,
            reason,
            evidence
        };
    });

    const activeIssue = humanizedQueue.find(q => q.id === focusedIssueId);
    
    // Count status values
    const pendingIssuesCount = humanizedQueue.length;
    const readySuggestionsCount = draftQuote.suggested_charges.filter(c => c.status === "suggested" || c.status === "accepted_by_user").length;

    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 p-6 font-sans">
            
            {/* Top Minimal Banner */}
            <div className="mb-6 bg-indigo-950/30 border border-indigo-900/60 rounded-xl p-3 flex justify-between items-center text-xs text-indigo-300">
                <div className="flex items-center gap-2">
                    <Info className="h-4 w-4 shrink-0" />
                    <span><strong>Prototype Mode</strong> — Mock data, no live database persistence active.</span>
                </div>
            </div>

            {/* Operator Workspace Grid */}
            <div className="max-w-4xl mx-auto flex flex-col gap-6">
                
                {/* 1. Review Summary Card */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                    <div>
                        <h1 className="text-xl font-bold text-slate-50 mb-1">Draft Quote Ready</h1>
                        <p className="text-sm text-slate-400">Review status for {draftQuote.shipment_context.origin} → {draftQuote.shipment_context.destination} ({draftQuote.shipment_context.commodity})</p>
                        
                        <div className="flex flex-wrap gap-4 mt-4 text-sm font-medium">
                            <span className="text-emerald-400 flex items-center gap-1.5">
                                <CheckCircle className="h-4 w-4" /> {readySuggestionsCount} suggestions ready
                            </span>
                            {pendingIssuesCount > 0 ? (
                                <span className="text-amber-400 flex items-center gap-1.5">
                                    <AlertCircle className="h-4 w-4" /> {pendingIssuesCount} items need review
                                </span>
                            ) : (
                                <span className="text-emerald-400 flex items-center gap-1.5">
                                    <CheckCircle className="h-4 w-4" /> All issues resolved
                                </span>
                            )}
                            <span className="text-indigo-400 flex items-center gap-1.5">
                                <FileText className="h-4 w-4" /> 1 commercial term requires confirmation
                            </span>
                        </div>
                    </div>
                    
                    <div className="flex flex-col items-stretch md:items-end gap-2 shrink-0 w-full md:w-auto">
                        <div className="text-xs text-slate-400 text-left md:text-right">
                            Estimated review time: <strong className="text-indigo-300">45 seconds</strong>
                        </div>
                        <button 
                            onClick={() => {
                                if (pendingIssuesCount > 0) {
                                    setFocusedIssueId(humanizedQueue[0].id);
                                }
                            }}
                            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition font-semibold text-sm text-center shadow-lg shadow-indigo-900/30"
                        >
                            Start Review
                        </button>
                    </div>
                </div>

                {/* 2. Needs Attention Queue (Primary Focus Workspace) */}
                {pendingIssuesCount > 0 && (
                    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-lg">
                        <h2 className="text-lg font-bold text-slate-50 mb-4 flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-amber-400" /> Needs Attention
                        </h2>
                        
                        <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                            
                            {/* Issues checklist (Left Column - 7cols) */}
                            <div className="md:col-span-7 flex flex-col gap-3">
                                {humanizedQueue.map(item => {
                                    const isActive = item.id === focusedIssueId;
                                    const actionObj = draftQuote.correction_actions.find(
                                        a => a.charge_id === item.id || a.item_id === item.id
                                    );
                                    const hasBulkGroup = draftQuote.suggested_charges.find(c => c.id === item.id)?.similarity_group_id;
                                    
                                    return (
                                        <div
                                            key={item.id}
                                            onClick={() => setFocusedIssueId(item.id)}
                                            className={`cursor-pointer rounded-xl p-4 border transition-all ${
                                                isActive
                                                    ? "bg-slate-800/80 border-indigo-500 shadow-md"
                                                    : "bg-slate-900 border-slate-880 hover:border-slate-700"
                                            }`}
                                        >
                                            <div className="flex justify-between items-start gap-2 mb-2">
                                                <span className="font-semibold text-sm text-slate-100">{item.title}</span>
                                                <span className="text-[10px] text-amber-400 font-semibold uppercase tracking-wider bg-amber-950/40 px-2 py-0.5 rounded border border-amber-900/40">
                                                    Action Required
                                                </span>
                                            </div>
                                            
                                            <p className="text-xs text-slate-300 mb-3">{item.reason}</p>
                                            
                                            {/* Resolution input triggers */}
                                            {isActive && actionObj && (
                                                <div className="mt-3 pt-3 border-t border-slate-800" onClick={e => e.stopPropagation()}>
                                                    {actionObj.action_type === "RESOLVE_PRODUCT_CODE" ? (
                                                        <div className="flex flex-col gap-2">
                                                            <label className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Select Billing Code</label>
                                                            <select
                                                                value={productCodeOverrides[item.id] || ""}
                                                                onChange={e => handleProductCodeChange(item.id, e.target.value)}
                                                                className="text-xs bg-slate-950 border border-slate-800 text-slate-200 rounded-lg p-2 focus:ring-indigo-500 focus:border-indigo-500"
                                                            >
                                                                <option value="">-- Choose Mapping Code --</option>
                                                                {actionObj.options.map(opt => (
                                                                    <option key={opt} value={opt}>{opt}</option>
                                                                ))}
                                                            </select>
                                                        </div>
                                                    ) : actionObj.action_type === "CONFIRM_INHERITED_CURRENCY" ? (
                                                        <div className="flex flex-col gap-2">
                                                            <label className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Confirm Currency</label>
                                                            <select
                                                                value={currencyOverrides[item.id] || "SGD"}
                                                                onChange={e => handleCurrencyChange(item.id, e.target.value)}
                                                                className="text-xs bg-slate-950 border border-slate-800 text-slate-200 rounded-lg p-2 focus:ring-indigo-500 focus:border-indigo-500"
                                                            >
                                                                {actionObj.options.map(opt => (
                                                                    <option key={opt} value={opt}>{opt}</option>
                                                                ))}
                                                            </select>
                                                        </div>
                                                    ) : (
                                                        <div className="flex flex-col gap-2">
                                                            <label className="text-[10px] text-slate-400 uppercase tracking-wider font-semibold">Map Unknown Charge</label>
                                                            <div className="flex gap-2">
                                                                {actionObj.options.map(opt => (
                                                                    <button
                                                                        key={opt}
                                                                        onClick={() => {
                                                                            alert(`Assigned category: ${opt}`);
                                                                            updateChargeStatus(item.id, "accepted_by_user");
                                                                        }}
                                                                        className="text-[10px] font-semibold bg-slate-950 hover:bg-slate-900 text-slate-200 border border-slate-800 px-3 py-1.5 rounded-lg transition"
                                                                    >
                                                                        {opt}
                                                                    </button>
                                                                ))}
                                                            </div>
                                                        </div>
                                                    )}
                                                    
                                                    {/* Similarity groups checkbox */}
                                                    {hasBulkGroup && (
                                                        <div className="mt-3 flex items-center gap-2">
                                                            <input
                                                                type="checkbox"
                                                                id={`bulk-${item.id}`}
                                                                checked={!!bulkUpdateGroups[hasBulkGroup]}
                                                                onChange={() => setBulkUpdateGroups(prev => ({
                                                                    ...prev,
                                                                    [hasBulkGroup]: !prev[hasBulkGroup]
                                                                }))}
                                                                className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-indigo-500 w-4.5 h-4.5"
                                                            />
                                                            <label htmlFor={`bulk-${item.id}`} className="text-xs text-indigo-300 font-medium cursor-pointer select-none">
                                                                Apply this correction to 3 similar charges
                                                            </label>
                                                        </div>
                                                    )}
                                                    
                                                    {/* Resolve Accept Button */}
                                                    <div className="mt-4 flex gap-2 justify-end">
                                                        <button 
                                                            onClick={() => updateChargeStatus(item.id, "accepted_by_user")}
                                                            className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg text-xs font-semibold flex items-center gap-1 transition"
                                                        >
                                                            Resolve & Accept
                                                        </button>
                                                        <button 
                                                            onClick={() => updateChargeStatus(item.id, "ignored")}
                                                            className="px-3.5 py-1.5 bg-slate-950 hover:bg-slate-900 text-slate-400 hover:text-red-400 rounded-lg text-xs font-semibold flex items-center gap-1 transition border border-slate-800"
                                                        >
                                                            Ignore Charge
                                                        </button>
                                                    </div>
                                                </div>
                                            )}
                                        </div>
                                    );
                                })}
                            </div>
                            
                            {/* Contextual evidence side (Right Column - 5cols) */}
                            <div className="md:col-span-5">
                                {activeIssue && activeIssue.evidence ? (
                                    <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 flex flex-col gap-3">
                                        <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-indigo-400">
                                            <FileText className="h-4 w-4" /> Matched Document Evidence
                                        </div>
                                        <p className="text-xs text-slate-400">Source: page {activeIssue.evidence.page || 1} ({activeIssue.evidence.document_reference || "attachment"})</p>
                                        <p className="text-sm font-mono text-slate-200 bg-slate-950 p-3 rounded-lg border border-slate-800 italic leading-relaxed">
                                            &quot;{activeIssue.evidence.source_text}&quot;
                                        </p>
                                        {activeIssue.evidence.extraction_note && (
                                            <p className="text-[10px] text-slate-400 italic">Extraction note: {activeIssue.evidence.extraction_note}</p>
                                        )}
                                    </div>
                                ) : (
                                    <div className="h-full bg-slate-950/20 border border-dashed border-slate-800 rounded-xl p-4 flex items-center justify-center text-center text-xs text-slate-500">
                                        Select an active issue to view matched source document text.
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                )}

                {/* 3. Suggested Charges Accordion */}
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
                                                    Product Code: <strong className="font-mono text-indigo-300">{charge.suggested_product_code || "Unmapped"}</strong>
                                                    {charge.rate && ` | @ ${charge.rate}/${charge.unit}`}
                                                </span>
                                            </div>
                                        </div>
                                        <div className="flex items-center gap-3">
                                            <span className="font-bold text-slate-100">{charge.currency} {Number(charge.amount).toFixed(2)}</span>
                                            <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold ${
                                                charge.status === "accepted_by_user" ? "bg-emerald-950/40 text-emerald-400 border border-emerald-900/60" :
                                                charge.status === "suggested" ? "bg-slate-800 text-slate-300 border border-slate-700" :
                                                "bg-amber-950/40 text-amber-300 border border-amber-900/60"
                                            }`}>
                                                {humanizeStatus(charge.status)}
                                            </span>
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* 4. Commercial Terms Accordion */}
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

                {/* 5. Totals Validation Accordion */}
                <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
                    <button
                        onClick={() => setShowTotalsPanel(!showTotalsPanel)}
                        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
                    >
                        <div className="flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-indigo-400" />
                            <span>Verification Warnings</span>
                        </div>
                        {showTotalsPanel ? <ChevronUp className="h-5 w-5 text-slate-400" /> : <ChevronDown className="h-5 w-5 text-slate-400" />}
                    </button>
                    
                    {showTotalsPanel && (
                        <div className="border-t border-slate-800 p-5 bg-slate-900/40 flex flex-col gap-4">
                            
                            {/* Quick warnings summarize */}
                            <div className="flex flex-col gap-3">
                                <div className="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm">
                                    <span className="text-slate-400">Math balance difference:</span>
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

                                <div className="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm">
                                    <span className="text-slate-400">Mixed currencies:</span>
                                    <div className="flex items-center gap-2">
                                        <span className="text-amber-400 font-semibold">SGD and USD detected</span>
                                        <button 
                                            onClick={() => alert("Explanation: Local cargo fees are in SGD, main linehaul air freight is in USD.")}
                                            className="text-xs text-indigo-400 font-semibold hover:underline"
                                        >
                                            [Explain]
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    )}
                </div>

                {/* 6. Finish Review & CTA Bar */}
                <div className="mt-4 flex flex-col items-center gap-3 border-t border-slate-800 pt-6">
                    <button
                        onClick={() => alert("Review Complete! The quote suggestions have been processed locally in this prototype mockup.")}
                        className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-bold text-sm shadow-xl shadow-indigo-900/40 w-full sm:w-auto text-center"
                    >
                        Finish Review
                    </button>
                    <div className="text-center text-xs text-slate-500">
                        Prototype only — Changes made will not be permanently saved.
                    </div>
                </div>

            </div>
        </div>
    );
}
