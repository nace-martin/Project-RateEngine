"use client";

/**
 * SPOT Quote Verification Panel
 * 
 * Internal screen for sales users to verify calculations and lock quotes.
 * Design matches reference: horizontal layout, 3-column verification grid, sticky actions
 */

import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
    formatPGK,
    formatWeight,
    formatRouteWithCities,
    cleanChargeDescription,
} from "@/lib/format-utils";
import type { SPEComputeResponse, SPEComputeResultLine } from "@/lib/spot-types";

interface QuoteVerificationPanelProps {
    quoteResult: SPEComputeResponse;
    shipmentContext: {
        origin_code: string;
        destination_code: string;
        commodity: string;
        total_weight_kg: number;
        pieces: number;
        volume_cbm?: number;
        service_scope?: string;
    };
    onLockQuote: () => void;
    onSaveDraft: () => void;
    isLoading: boolean;
    quoteId?: string;
}

export function QuoteVerificationPanel({
    quoteResult,
    shipmentContext,
    onLockQuote,
    onSaveDraft,
    isLoading,
    quoteId
}: QuoteVerificationPanelProps) {
    const [lockConfirmed, setLockConfirmed] = useState(false);
    const [draftSaved, setDraftSaved] = useState(false);
    const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({});

    const toggleSection = (key: string) => {
        setExpandedSections(prev => ({ ...prev, [key]: !prev[key] }));
    };

    // Route formatting
    const route = formatRouteWithCities(
        shipmentContext.origin_code,
        shipmentContext.destination_code
    );

    // Calculate totals by bucket
    const lines = quoteResult.lines || [];
    const originLines = lines.filter(l => l.bucket === 'origin_charges' && !l.is_informational);
    const freightLines = lines.filter(l => ['freight_charges', 'airfreight'].includes(l.bucket) && !l.is_informational);
    const destLines = lines.filter(l => l.bucket === 'destination_charges' && !l.is_informational);
    const conditionalLines = lines.filter(l => l.is_informational);

    const originTotal = originLines.reduce((sum, l) => sum + parseFloat(l.sell_pgk_incl_gst || "0"), 0);
    const freightTotal = freightLines.reduce((sum, l) => sum + parseFloat(l.sell_pgk_incl_gst || "0"), 0);
    const destTotal = destLines.reduce((sum, l) => sum + parseFloat(l.sell_pgk_incl_gst || "0"), 0);
    const grandTotal = parseFloat(quoteResult.totals?.total_sell_pgk_incl_gst || "0");

    // Calculate verification values
    const actualWeight = shipmentContext.total_weight_kg || 0;
    const volumeCbm = shipmentContext.volume_cbm || 0;
    const volumetricDivisor = 6000; // Standard air freight divisor
    const volumetricWeight = volumeCbm > 0 ? volumeCbm * 167 : 0; // CBM × 167 for air
    const chargeableWeight = Math.max(actualWeight, volumetricWeight);
    const ratePerKg = freightTotal > 0 && chargeableWeight > 0 ? freightTotal / chargeableWeight : 0;

    // FX info
    const fxInfo = quoteResult.fx_info;
    const baseFxRate = fxInfo ? parseFloat(fxInfo.rate) : 1;
    const cafPercent = 10; // Export CAF is 10%
    const effectiveFxRate = baseFxRate * (1 + cafPercent / 100);
    const spotMarginPercent = 20; // SPOT margin 20%

    return (
        <div className="pb-24">
            <div className="max-w-6xl mx-auto space-y-6">

                {/* Total Hero - Green left border */}
                <div className="bg-white rounded-lg border border-slate-200 border-l-4 border-l-emerald-500 p-6">
                    <div className="flex justify-between items-start">
                        <div>
                            <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Total Estimated Quote</p>
                            <p className="text-4xl font-bold text-slate-900">{formatPGK(grandTotal)}</p>
                            <p className="text-emerald-600 text-sm font-medium mt-1 flex items-center gap-1">
                                <span className="w-2 h-2 bg-emerald-500 rounded-full"></span>
                                Ready to proceed
                            </p>
                        </div>
                        <div className="text-right text-sm text-slate-500 max-w-xs">
                            <p>Includes core origin, air freight, and standard destination charges.</p>
                            <p className="text-xs text-slate-400 mt-1">
                                Assumes standard handling; excludes inspection, storage, and special equipment unless stated.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Verification Data - Horizontal 3-column grid */}
                <div className="bg-white rounded-lg border border-slate-200 p-6">
                    <div className="flex justify-between items-center mb-4">
                        <div>
                            <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Verification Data</h2>
                            <p className="text-xs text-slate-400">Inputs → Rules → Outputs</p>
                        </div>
                        <p className="text-xs text-blue-600">Please verify inputs before locking</p>
                    </div>

                    <div className="grid grid-cols-3 gap-8 pt-4 border-t border-slate-100">
                        {/* Column 1: Chargeable Weight */}
                        <div>
                            <h3 className="text-sm font-semibold text-slate-800 mb-4">1. Chargeable Weight (Air)</h3>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Actual Weight:</span>
                                    <span className="font-medium">{actualWeight.toFixed(2)} kg</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Volumetric (×167):</span>
                                    <span className="font-medium">{volumetricWeight.toFixed(2)} kg</span>
                                </div>
                                <div className="flex justify-between pt-2 border-t border-slate-100">
                                    <span className="text-blue-600">Chargeable:</span>
                                    <span className="font-bold text-slate-900">{chargeableWeight.toFixed(2)} kg</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Applied Rate:</span>
                                    <span className="font-medium">PGK {ratePerKg.toFixed(2)} / kg</span>
                                </div>
                            </div>
                        </div>

                        {/* Column 2: Currency & Adjustment */}
                        {fxInfo && (
                            <div>
                                <h3 className="text-sm font-semibold text-slate-800 mb-4">2. Currency & Adjustment</h3>
                                <div className="space-y-2 text-sm">
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">Base Currency:</span>
                                        <span className="font-medium">{fxInfo.source_currency}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">Base FX Rate:</span>
                                        <span className="font-medium">{baseFxRate.toFixed(4)}</span>
                                    </div>
                                    <div className="flex justify-between">
                                        <span className="text-slate-500">CAF Applied:</span>
                                        <span className="font-medium text-blue-600">{cafPercent}%</span>
                                    </div>
                                    <div className="flex justify-between pt-2 border-t border-slate-100">
                                        <span className="text-blue-600">Effective FX:</span>
                                        <span className="font-bold text-slate-900">{effectiveFxRate.toFixed(4)}</span>
                                    </div>
                                    <p className="text-xs text-slate-400 italic">FX locked at finalization time</p>
                                </div>
                            </div>
                        )}

                        {/* Column 3: Pricing Model */}
                        <div>
                            <h3 className="text-sm font-semibold text-slate-800 mb-4">3. Pricing Model</h3>
                            <div className="space-y-2 text-sm">
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Mode:</span>
                                    <span className="font-medium">{quoteResult.pricing_mode === 'SPOT' ? 'Cost Plus Margin' : 'Standard'}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-500">Rule:</span>
                                    <span className="font-medium">Standard Spot Margin</span>
                                </div>
                                <div className="flex justify-between pt-2 border-t border-slate-100">
                                    <span className="text-slate-500">Markup:</span>
                                    <span className="font-bold text-blue-600">{spotMarginPercent}%</span>
                                </div>
                                <p className="text-xs text-slate-400 italic">Applied to all pass-through costs</p>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Charges Breakdown */}
                <div className="space-y-3">
                    <h2 className="text-sm font-semibold text-slate-700 uppercase tracking-wide">Charges Breakdown</h2>

                    {/* Origin Charges */}
                    <ChargeSection
                        title="Origin Handling & Compliance"
                        subtitle="Included: Documentation, AWB, terminal handling, security screening, pickup, export customs"
                        total={originTotal}
                        lines={originLines}
                        isExpanded={expandedSections['origin']}
                        onToggle={() => toggleSection('origin')}
                        chargeableWeight={chargeableWeight}
                    />

                    {/* Air Freight */}
                    <ChargeSection
                        title={`Air Freight (${shipmentContext.origin_code} → ${shipmentContext.destination_code})`}
                        subtitle={`Chargeable weight: ${chargeableWeight.toFixed(0)} kg @ PGK ${ratePerKg.toFixed(2)}/kg`}
                        total={freightTotal}
                        lines={freightLines}
                        isExpanded={expandedSections['freight']}
                        onToggle={() => toggleSection('freight')}
                        chargeableWeight={chargeableWeight}
                    />

                    {/* Destination Charges */}
                    <ChargeSection
                        title="Estimated Destination Charges"
                        subtitle="Terminal handling, import clearance, Standard Delivery"
                        total={destTotal}
                        lines={destLines}
                        isExpanded={expandedSections['dest']}
                        onToggle={() => toggleSection('dest')}
                        chargeableWeight={chargeableWeight}
                    />
                </div>

                {/* Destination Variability Disclaimer - Red left border */}
                <div className="bg-red-50 border border-red-200 border-l-4 border-l-red-500 rounded-r-lg p-4">
                    <h3 className="text-sm font-semibold text-red-800 mb-1">
                        Important – Destination Variability
                    </h3>
                    <p className="text-sm text-red-700">
                        Destination charges are based on standard handling. Actual costs may vary significantly if
                        Customs inspection, additional terminal handling, storage, or regulatory intervention applies at destination.
                    </p>
                </div>

                {/* Possible Additional Charges */}
                {conditionalLines.length > 0 && (
                    <div className="bg-white border border-slate-200 rounded-lg">
                        <button
                            onClick={() => toggleSection('additional')}
                            className="w-full flex justify-between items-center p-4 text-left hover:bg-slate-50"
                        >
                            <span className="font-medium text-slate-700">
                                Possible Additional Charges (if applicable)
                            </span>
                            <span className="text-slate-400 text-sm">
                                {expandedSections['additional'] ? '[−]' : '[+]'}
                            </span>
                        </button>
                        {expandedSections['additional'] && (
                            <div className="px-4 pb-4 space-y-1 border-t border-slate-100 pt-3">
                                {conditionalLines.map((line, idx) => (
                                    <p key={idx} className="text-sm text-slate-600">
                                        • {cleanChargeDescription(line.description)}
                                    </p>
                                ))}
                            </div>
                        )}
                    </div>
                )}
            </div>

            {/* Sticky Bottom Action Bar */}
            <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 px-6 py-4 shadow-lg">
                <div className="max-w-6xl mx-auto flex items-center justify-between">
                    <div className="flex items-center gap-3">
                        <input
                            type="checkbox"
                            id="confirmCheck"
                            checked={lockConfirmed}
                            onChange={(e) => setLockConfirmed(e.target.checked)}
                            className="h-4 w-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                        />
                        <label htmlFor="confirmCheck" className="text-sm text-slate-600">
                            I've reviewed chargeable weight, FX/CAF, and inclusions.
                        </label>
                        <span className="text-xs text-slate-400 ml-2">
                            Locking freezes rates and FX for the generated PDF and audit trail.
                        </span>
                    </div>
                    <div className="flex items-center gap-4">
                        {draftSaved ? (
                            <span className="text-sm text-emerald-600 font-medium">
                                ✓ Draft saved! Redirecting to Quotes...
                            </span>
                        ) : (
                            <button
                                onClick={() => {
                                    setDraftSaved(true);
                                    setTimeout(() => onSaveDraft(), 1500);
                                }}
                                className="text-sm text-slate-600 hover:text-slate-800"
                            >
                                Save Draft
                            </button>
                        )}
                        <Button
                            onClick={onLockQuote}
                            disabled={isLoading || !lockConfirmed}
                            className="bg-slate-900 hover:bg-slate-800 text-white px-8"
                        >
                            {isLoading ? "Locking..." : "Lock Quote"}
                        </Button>
                    </div>
                </div>
            </div>

            {/* Footer */}
            <div className="text-center text-xs text-slate-400 pb-4 mt-8">
                <p>This quote was generated using <strong className="text-slate-500">RateEngine™</strong></p>
                <p className="mt-0.5">Built on real carrier rates, local handling costs, and current FX assumptions.</p>
            </div>
        </div>
    );
}

// =============================================================================
// Charge Section Sub-component - Matches reference design
// =============================================================================

interface ChargeSectionProps {
    title: string;
    subtitle: string;
    total: number;
    lines: SPEComputeResultLine[];
    isExpanded: boolean;
    onToggle: () => void;
    chargeableWeight: number;
}

function ChargeSection({
    title,
    subtitle,
    total,
    lines,
    isExpanded,
    onToggle,
    chargeableWeight
}: ChargeSectionProps) {
    if (lines.length === 0) return null;

    return (
        <div className="bg-white border border-slate-200 rounded-lg">
            <div className="flex justify-between items-center p-4">
                <div>
                    <p className="font-semibold text-slate-900">{title}</p>
                    <p className="text-xs text-slate-500">{subtitle}</p>
                </div>
                <div className="flex items-center gap-4">
                    <span className="font-bold text-slate-900">{formatPGK(total)}</span>
                    <button
                        onClick={onToggle}
                        className="text-sm text-blue-600 hover:text-blue-800"
                    >
                        {isExpanded ? 'Hide Breakdown [−]' : 'View Breakdown [+]'}
                    </button>
                </div>
            </div>
            {isExpanded && (
                <div className="border-t border-slate-100 px-4 pb-4">
                    <table className="w-full text-sm mt-3">
                        <thead>
                            <tr className="text-left text-xs text-slate-500">
                                <th className="pb-2 font-medium">Charge</th>
                                <th className="pb-2 font-medium">Basis</th>
                                <th className="pb-2 text-right font-medium">Amount</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100">
                            {lines.map((line, idx) => (
                                <tr key={idx}>
                                    <td className="py-2 text-slate-700">
                                        {cleanChargeDescription(line.description)}
                                    </td>
                                    <td className="py-2 text-slate-500">
                                        {getBasis(line, chargeableWeight)}
                                    </td>
                                    <td className="py-2 text-right text-slate-900 tabular-nums">
                                        {parseFloat(line.sell_pgk_incl_gst || "0").toFixed(2)}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}

// Helper to determine charge basis for display
function getBasis(line: SPEComputeResultLine, chargeableWeight: number): string {
    const desc = line.description.toLowerCase();

    if (desc.includes('fuel') || desc.includes('surcharge')) {
        return '10% × Pickup';
    }
    if (desc.includes('terminal') || desc.includes('handling')) {
        return `${chargeableWeight.toFixed(0)} kg @ PGK 0.50/kg`;
    }
    if (desc.includes('documentation') || desc.includes('doc')) {
        return 'Per Shipment';
    }
    if (desc.includes('customs') || desc.includes('clearance')) {
        return 'Flat Rate';
    }
    if (desc.includes('freight')) {
        return `${chargeableWeight.toFixed(0)} kg @ rate`;
    }
    return 'Per Shipment';
}
