"use client";

import React, { useState } from "react";
import { AlertCircle, CheckCircle, HelpCircle, Info, ShieldAlert, FileText, Group, Sparkles, XCircle } from "lucide-react";
import { hardCaseAirImportData } from "../../data/hardCaseAirImport";
import { DraftChargeStatus, Evidence } from "../../lib/draft-quote-types";

export function ExceptionWorkspace() {
    const [draftQuote, setDraftQuote] = useState(hardCaseAirImportData);
    const [selectedEvidence, setSelectedEvidence] = useState<Evidence | null>(
        draftQuote.suggested_charges[0]?.evidence || null
    );
    const [selectedItemId, setSelectedItemId] = useState<string>("chg-001");
    const [statusFilter, setStatusFilter] = useState<string>("all");
    const [bulkUpdateGroups, setBulkUpdateGroups] = useState<Record<string, boolean>>({});
    
    // Inline corrections state
    const [productCodeOverrides, setProductCodeOverrides] = useState<Record<string, string>>({});
    const [currencyOverrides, setCurrencyOverrides] = useState<Record<string, string>>({});
    
    // Status update handler
    const updateChargeStatus = (chargeId: string, newStatus: DraftChargeStatus) => {
        setDraftQuote(prev => {
            const updatedCharges = prev.suggested_charges.map(c => {
                if (c.id === chargeId) {
                    const updated = { ...c, status: newStatus };
                    // If similarity group is enabled for this group, update matches as well
                    if (c.similarity_group_id && bulkUpdateGroups[c.similarity_group_id]) {
                        return updated;
                    }
                    return updated;
                }
                // Handle similarity group matches
                const target = prev.suggested_charges.find(x => x.id === chargeId);
                if (target?.similarity_group_id && c.similarity_group_id === target.similarity_group_id && bulkUpdateGroups[target.similarity_group_id]) {
                    return { ...c, status: newStatus };
                }
                return c;
            });
            
            // Re-calculate totals validation dynamically
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

    // Filter charges
    const filteredCharges = draftQuote.suggested_charges.filter(c => {
        if (statusFilter === "all") return true;
        return c.status === statusFilter;
    });

    const selectItem = (id: string, evidence: Evidence | null) => {
        setSelectedItemId(id);
        if (evidence) {
            setSelectedEvidence(evidence);
        }
    };

    return (
        <div className="min-h-screen bg-slate-900 text-slate-100 p-6 font-sans">
            {/* Top Workspace Header */}
            <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-5">
                <div>
                    <div className="flex items-center gap-2 mb-1">
                        <Sparkles className="h-5 w-5 text-indigo-400" />
                        <span className="text-xs uppercase tracking-wider font-semibold text-indigo-400">Intake Assistant</span>
                    </div>
                    <h1 className="text-2xl font-bold text-slate-50">{draftQuote.quote_summary}</h1>
                    <p className="text-sm text-slate-400 mt-1">Contract Version: {draftQuote.contract_version} | Supplier: {draftQuote.supplier_context.supplier_name}</p>
                </div>
                <div className="flex items-center gap-3">
                    <button className="px-4 py-2 bg-slate-800 text-slate-300 rounded-lg hover:bg-slate-700 transition font-medium text-sm">
                        Reset Draft
                    </button>
                    <button className="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-500 transition font-semibold text-sm shadow-lg shadow-indigo-900/30 flex items-center gap-2">
                        <CheckCircle className="h-4 w-4" /> Accept and Sync to V4
                    </button>
                </div>
            </div>

            {/* Top Alerts */}
            {draftQuote.warnings.length > 0 && (
                <div className="mb-6 grid grid-cols-1 md:grid-cols-2 gap-4">
                    {draftQuote.warnings.map((warn, i) => (
                        <div key={i} className="flex items-start gap-3 bg-red-950/40 border border-red-900/60 rounded-xl p-4 text-sm text-red-200">
                            <ShieldAlert className="h-5 w-5 text-red-400 shrink-0 mt-0.5" />
                            <div>
                                <span className="font-semibold block mb-0.5">Validation Alert</span>
                                <span>{warn}</span>
                            </div>
                        </div>
                    ))}
                </div>
            )}

            {/* Dashboard Grid */}
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
                
                {/* Left Side: Summary Cards + Tabular View + Commercial Terms (8 Columns) */}
                <div className="xl:col-span-8 flex flex-col gap-6">
                    
                    {/* Shipment Context Cards */}
                    <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm backdrop-blur-md">
                        <h2 className="text-sm uppercase tracking-wider font-semibold text-slate-400 mb-4 flex items-center gap-2">
                            <Info className="h-4 w-4 text-indigo-400" /> Shipment Metrics & Context
                        </h2>
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
                            <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700/50">
                                <span className="text-xs text-slate-400 block mb-1">Route</span>
                                <span className="text-lg font-bold text-slate-100 flex items-center gap-1.5">
                                    {draftQuote.shipment_context.origin}
                                    <span className="text-slate-500 font-normal">→</span>
                                    {draftQuote.shipment_context.destination}
                                </span>
                            </div>
                            <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700/50">
                                <span className="text-xs text-slate-400 block mb-1">Chargeable Weight</span>
                                <span className="text-lg font-bold text-slate-100">{draftQuote.shipment_context.chargeable_weight_kg} kg</span>
                            </div>
                            <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700/50">
                                <span className="text-xs text-slate-400 block mb-1">Actual Weight</span>
                                <span className="text-lg font-bold text-slate-100">{draftQuote.shipment_context.actual_weight_kg} kg</span>
                            </div>
                            <div className="bg-slate-800/80 rounded-xl p-3 border border-slate-700/50">
                                <span className="text-xs text-slate-400 block mb-1">Volumetric / Pcs</span>
                                <span className="text-lg font-bold text-slate-100">{draftQuote.shipment_context.volumetric_weight_kg} kg ({draftQuote.shipment_context.pieces} pcs)</span>
                            </div>
                        </div>
                    </div>

                    {/* Tabular Charges Section */}
                    <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm flex flex-col">
                        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
                            <h2 className="text-lg font-bold text-slate-50 flex items-center gap-2">
                                <Sparkles className="h-5 w-5 text-indigo-400" /> Suggested Charge Lines
                            </h2>
                            
                            {/* Status Filter Tab Buttons */}
                            <div className="flex bg-slate-800 p-1 rounded-lg border border-slate-700">
                                {["all", "suggested", "needs_review", "ignored"].map(tab => (
                                    <button
                                        key={tab}
                                        onClick={() => setStatusFilter(tab)}
                                        className={`px-3 py-1 text-xs font-semibold rounded-md capitalize transition-all ${
                                            statusFilter === tab
                                                ? "bg-indigo-600 text-white shadow-sm"
                                                : "text-slate-400 hover:text-slate-200"
                                        }`}
                                    >
                                        {tab.replace("_", " ")}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Charges Table */}
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="border-b border-slate-800 text-xs font-bold uppercase tracking-wider text-slate-400">
                                        <th className="py-3 px-2 w-[40px]">Inc</th>
                                        <th className="py-3 px-3">Charge Details</th>
                                        <th className="py-3 px-3">Product Code</th>
                                        <th className="py-3 px-3 text-right">Amount</th>
                                        <th className="py-3 px-3">Status</th>
                                        <th className="py-3 px-3 w-[150px] text-right">Actions</th>
                                    </tr>
                                </thead>
                                <tbody className="text-sm divide-y divide-slate-800/60">
                                    {filteredCharges.map(charge => {
                                        const isSelected = selectedItemId === charge.id;
                                        const actionsObj = draftQuote.correction_actions.find(a => a.charge_id === charge.id);
                                        
                                        return (
                                            <tr
                                                key={charge.id}
                                                onClick={() => selectItem(charge.id, charge.evidence)}
                                                className={`cursor-pointer transition-all ${
                                                    isSelected 
                                                        ? "bg-slate-800/90 border-l-4 border-indigo-500" 
                                                        : "hover:bg-slate-800/30"
                                                }`}
                                            >
                                                {/* Checkbox Include in Totals */}
                                                <td className="py-4 px-2 text-center" onClick={e => e.stopPropagation()}>
                                                    <input
                                                        type="checkbox"
                                                        checked={charge.include_in_totals}
                                                        onChange={() => toggleIncludeInTotals(charge.id)}
                                                        className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-indigo-500 focus:ring-offset-slate-900"
                                                    />
                                                </td>

                                                {/* Label details */}
                                                <td className="py-4 px-3">
                                                    <span className="font-semibold block text-slate-100">{charge.display_label}</span>
                                                    <span className="text-xs text-slate-400 font-mono block max-w-[280px] truncate" title={charge.raw_label}>
                                                        {charge.raw_label}
                                                    </span>
                                                    {charge.similarity_group_id && (
                                                        <span className="inline-flex items-center gap-1 mt-1 px-1.5 py-0.5 rounded text-[10px] bg-indigo-950/40 text-indigo-300 border border-indigo-900/60">
                                                            <Group className="h-3 w-3" /> Similarity Group: {charge.similarity_group_id}
                                                        </span>
                                                    )}
                                                </td>

                                                {/* Product code conflict or mapping */}
                                                <td className="py-4 px-3" onClick={e => e.stopPropagation()}>
                                                    {actionsObj?.action_type === "RESOLVE_PRODUCT_CODE" ? (
                                                        <div className="flex flex-col gap-1">
                                                            <select
                                                                value={productCodeOverrides[charge.id] || ""}
                                                                onChange={e => handleProductCodeChange(charge.id, e.target.value)}
                                                                className="text-xs bg-slate-900 border border-amber-900/60 text-amber-200 rounded p-1 focus:ring-amber-500 focus:border-amber-500"
                                                            >
                                                                <option value="">-- Resolve Conflict --</option>
                                                                {actionsObj.options.map(opt => (
                                                                    <option key={opt} value={opt}>{opt}</option>
                                                                ))}
                                                            </select>
                                                            {charge.product_code_conflict && (
                                                                <span className="text-[10px] text-amber-400 font-medium flex items-center gap-1">
                                                                    <AlertCircle className="h-3 w-3" /> Conflict
                                                                </span>
                                                            )}
                                                        </div>
                                                    ) : (
                                                        <span className="font-mono text-slate-300 bg-slate-900 px-2 py-0.5 rounded border border-slate-700/80">
                                                            {charge.suggested_product_code || "UNMAPPED"}
                                                        </span>
                                                    )}
                                                </td>

                                                {/* Currency & Amount */}
                                                <td className="py-4 px-3 text-right" onClick={e => e.stopPropagation()}>
                                                    <div className="flex items-center justify-end gap-1.5">
                                                        {actionsObj?.action_type === "CONFIRM_INHERITED_CURRENCY" ? (
                                                            <select
                                                                value={currencyOverrides[charge.id] || charge.currency}
                                                                onChange={e => handleCurrencyChange(charge.id, e.target.value)}
                                                                className="text-xs bg-slate-900 border border-slate-700 rounded p-1 text-slate-200"
                                                            >
                                                                {actionsObj.options.map(opt => (
                                                                    <option key={opt} value={opt}>{opt}</option>
                                                                ))}
                                                            </select>
                                                        ) : (
                                                            <span className="text-slate-300 font-medium">{charge.currency}</span>
                                                        )}
                                                        <span className="font-bold text-slate-100">{Number(charge.amount).toFixed(2)}</span>
                                                    </div>
                                                    <span className="text-[10px] text-slate-400 block mt-0.5">
                                                        {charge.rate ? `@ ${charge.rate}/${charge.unit}` : "Flat fee"}
                                                    </span>
                                                </td>

                                                {/* Status badge */}
                                                <td className="py-4 px-3">
                                                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${
                                                        charge.status === "suggested" ? "bg-emerald-950/40 text-emerald-300 border border-emerald-900/60" :
                                                        charge.status === "needs_review" ? "bg-amber-950/40 text-amber-300 border border-amber-900/60" :
                                                        charge.status === "ignored" ? "bg-slate-800 text-slate-400 border border-slate-700" :
                                                        "bg-indigo-950 text-indigo-300 border border-indigo-900"
                                                    }`}>
                                                        {charge.status.replace("_", " ")}
                                                    </span>
                                                </td>

                                                {/* Local Actions Row */}
                                                <td className="py-4 px-3 text-right" onClick={e => e.stopPropagation()}>
                                                    <div className="flex items-center justify-end gap-1.5">
                                                        <button
                                                            onClick={() => updateChargeStatus(charge.id, "accepted_by_user")}
                                                            className="p-1 rounded bg-slate-800 text-slate-400 hover:text-emerald-400 hover:bg-emerald-950/40 border border-slate-700 transition"
                                                            title="Accept suggestion"
                                                        >
                                                            <CheckCircle className="h-4 w-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => updateChargeStatus(charge.id, "ignored")}
                                                            className="p-1 rounded bg-slate-800 text-slate-400 hover:text-red-400 hover:bg-red-950/40 border border-slate-700 transition"
                                                            title="Ignore / Exclude charge"
                                                        >
                                                            <XCircle className="h-4 w-4" />
                                                        </button>
                                                        <button
                                                            onClick={() => updateChargeStatus(charge.id, "needs_review")}
                                                            className="p-1 rounded bg-slate-800 text-slate-400 hover:text-amber-400 hover:bg-amber-950/40 border border-slate-700 transition"
                                                            title="Decline to review queue"
                                                        >
                                                            <HelpCircle className="h-4 w-4" />
                                                        </button>
                                                    </div>
                                                    
                                                    {charge.similarity_group_id && (
                                                        <div className="mt-1 flex items-center justify-end gap-1">
                                                            <input
                                                                type="checkbox"
                                                                id={`bulk-${charge.id}`}
                                                                checked={!!bulkUpdateGroups[charge.similarity_group_id]}
                                                                onChange={() => setBulkUpdateGroups(prev => ({
                                                                    ...prev,
                                                                    [charge.similarity_group_id!]: !prev[charge.similarity_group_id!]
                                                                }))}
                                                                className="rounded bg-slate-900 border-slate-700 text-indigo-600 focus:ring-indigo-500 w-3 h-3"
                                                            />
                                                            <label htmlFor={`bulk-${charge.id}`} className="text-[9px] text-indigo-400 cursor-pointer font-medium select-none">
                                                                Bulk edit group
                                                            </label>
                                                        </div>
                                                    )}
                                                </td>
                                            </tr>
                                        );
                                    })}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    {/* Commercial Terms Section */}
                    <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-50 mb-4 flex items-center gap-2">
                            <FileText className="h-5 w-5 text-indigo-400" /> Extracted Commercial Terms
                        </h2>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {draftQuote.commercial_terms.map((term, i) => (
                                <div
                                    key={i}
                                    onClick={() => selectItem(`term-${i}`, term.evidence)}
                                    className={`cursor-pointer rounded-xl p-4 border transition-all ${
                                        selectedItemId === `term-${i}`
                                            ? "bg-slate-800 border-indigo-500 shadow-md"
                                            : "bg-slate-800/60 border-slate-700/60 hover:bg-slate-800/30"
                                    }`}
                                >
                                    <div className="flex items-center justify-between gap-2 mb-2">
                                        <span className="text-xs uppercase font-bold text-indigo-400 tracking-wider">
                                            {term.type}
                                        </span>
                                        <span className="text-[10px] bg-slate-900 border border-slate-700 px-1.5 rounded text-slate-400">
                                            Value: {term.normalized_value ? String(term.normalized_value) : "Null"}
                                        </span>
                                    </div>
                                    <p className="text-sm text-slate-200 italic">&quot;{term.text}&quot;</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Right Side: Totals Validation Panel + Review Queue + Evidence Panel (4 Columns) */}
                <div className="xl:col-span-4 flex flex-col gap-6">
                    
                    {/* Totals Validation Card */}
                    <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-50 mb-4 flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-indigo-400" /> Totals Verification
                        </h2>
                        
                        <div className="flex flex-col gap-3 bg-slate-900 border border-slate-800 rounded-xl p-4">
                            <div className="flex justify-between items-center text-sm border-b border-slate-800 pb-2">
                                <span className="text-slate-400 font-medium">Calculated Sum</span>
                                <span className="font-bold text-slate-100">
                                    USD {draftQuote.totals_validation.calculated_total?.toFixed(2)}
                                </span>
                            </div>
                            <div className="flex justify-between items-center text-sm border-b border-slate-800 pb-2">
                                <span className="text-slate-400 font-medium">Extracted Total</span>
                                <span className="font-bold text-slate-100">
                                    USD {draftQuote.totals_validation.extracted_total?.toFixed(2)}
                                </span>
                            </div>
                            <div className="flex justify-between items-center text-sm pt-1">
                                <span className="text-slate-400 font-medium">Difference</span>
                                <span className={`font-bold ${
                                    draftQuote.totals_validation.difference && draftQuote.totals_validation.difference > 0
                                        ? "text-red-400"
                                        : "text-emerald-400"
                                }`}>
                                    USD {draftQuote.totals_validation.difference?.toFixed(2)}
                                </span>
                            </div>
                        </div>

                        {draftQuote.totals_validation.warnings.map((warn, i) => (
                            <div key={i} className="mt-4 flex items-start gap-2 text-xs bg-amber-950/20 border border-amber-900/60 rounded-lg p-3 text-amber-200">
                                <AlertCircle className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                                <span>{warn}</span>
                            </div>
                        ))}
                    </div>

                    {/* Review Queue & Unclassified Panel */}
                    <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm">
                        <h2 className="text-lg font-bold text-slate-50 mb-3 flex items-center gap-2">
                            <ShieldAlert className="h-5 w-5 text-indigo-400" /> Review Queue
                        </h2>
                        
                        <div className="flex flex-col gap-3">
                            {draftQuote.review_queue.map(item => {
                                const actionObj = draftQuote.correction_actions.find(
                                    a => a.charge_id === item.id || a.item_id === item.id
                                );
                                
                                return (
                                    <div
                                        key={item.id}
                                        onClick={() => selectItem(item.id, null)}
                                        className="bg-slate-900 border border-slate-800 hover:border-slate-700 cursor-pointer rounded-xl p-3.5 flex flex-col gap-2 transition"
                                    >
                                        <div className="flex items-center justify-between">
                                            <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-900/60">
                                                {item.type.replace("_", " ")}
                                            </span>
                                            <span className="text-slate-500 font-mono text-[10px]">{item.id}</span>
                                        </div>
                                        
                                        <p className="text-xs text-slate-200 font-medium">{item.message}</p>
                                        
                                        {actionObj && (
                                            <div className="mt-2 pt-2 border-t border-slate-800/60 flex flex-col gap-1.5" onClick={e => e.stopPropagation()}>
                                                <span className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">Suggested action</span>
                                                <div className="flex flex-wrap gap-1.5">
                                                    {actionObj.options.map(opt => (
                                                        <button
                                                            key={opt}
                                                            onClick={() => {
                                                                if (item.id === "unclass-001") {
                                                                    // Mock classify action
                                                                    alert(`Classified unclassified item as ${opt}`);
                                                                } else if (actionObj.action_type === "RESOLVE_PRODUCT_CODE") {
                                                                    handleProductCodeChange(item.id, opt);
                                                                } else if (actionObj.action_type === "CONFIRM_INHERITED_CURRENCY") {
                                                                    handleCurrencyChange(item.id, opt);
                                                                }
                                                            }}
                                                            className="text-[10px] font-semibold bg-slate-800 text-slate-300 border border-slate-700 hover:border-slate-500 px-2 py-1 rounded transition"
                                                        >
                                                            {opt.replace("_", " ")}
                                                        </button>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {/* Unclassified & Ignored Section */}
                    {draftQuote.ignored_items.length > 0 && (
                        <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm">
                            <h2 className="text-lg font-bold text-slate-50 mb-3 flex items-center gap-2">
                                <FileText className="h-5 w-5 text-indigo-400" /> Ignored Content
                            </h2>
                            <div className="flex flex-col gap-3">
                                {draftQuote.ignored_items.map(item => (
                                    <div key={item.id} className="bg-slate-900 border border-slate-800 rounded-xl p-3 text-xs flex flex-col gap-1.5">
                                        <span className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">Reason: {item.ignored_reason}</span>
                                        <p className="text-slate-400 italic font-mono bg-slate-950 p-2 rounded">&quot;{item.raw_text}&quot;</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                    )}

                    {/* Right Side: Source Evidence Display */}
                    {selectedEvidence && (
                        <div className="bg-slate-800/50 border border-slate-800 rounded-2xl p-5 shadow-sm">
                            <h2 className="text-lg font-bold text-slate-50 mb-3 flex items-center gap-2">
                                <FileText className="h-5 w-5 text-indigo-400" /> Extraction Evidence
                            </h2>
                            <div className="flex flex-col gap-3 bg-slate-900 border border-slate-800 rounded-xl p-4">
                                <div className="flex justify-between items-center text-xs border-b border-slate-800 pb-2">
                                    <span className="text-slate-400 font-semibold uppercase">Document Source</span>
                                    <span className="font-mono text-slate-200">{selectedEvidence.document_reference || "Unknown"}</span>
                                </div>
                                <div className="flex justify-between items-center text-xs border-b border-slate-800 pb-2">
                                    <span className="text-slate-400 font-semibold uppercase">Location Context</span>
                                    <span className="text-slate-200">Page {selectedEvidence.page || 1} | Section {selectedEvidence.section || "General"}</span>
                                </div>
                                {selectedEvidence.bounding_box && (
                                    <div className="flex justify-between items-center text-xs border-b border-slate-800 pb-2">
                                        <span className="text-slate-400 font-semibold uppercase">BBox Coordinates</span>
                                        <span className="font-mono text-slate-300">[{selectedEvidence.bounding_box.join(", ")}]</span>
                                    </div>
                                )}
                                <div className="flex flex-col gap-1.5 pt-1">
                                    <span className="text-xs text-indigo-400 font-semibold uppercase">Matched Source Text</span>
                                    <p className="text-sm font-mono text-slate-200 bg-slate-950 p-3 rounded-lg border border-slate-800 italic leading-relaxed">
                                        &quot;{selectedEvidence.source_text}&quot;
                                    </p>
                                </div>
                                {selectedEvidence.extraction_note && (
                                    <div className="flex flex-col gap-1.5 pt-2 border-t border-slate-800/60">
                                        <span className="text-[10px] text-slate-400 font-semibold uppercase">Parsing Notes</span>
                                        <span className="text-xs text-slate-300 font-medium">{selectedEvidence.extraction_note}</span>
                                    </div>
                                )}
                            </div>
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}
