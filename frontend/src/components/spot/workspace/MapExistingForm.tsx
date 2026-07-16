"use client";

import React from "react";

interface MapExistingFormProps {
    onMap: (productCode: string) => void;
    onCancel: () => void;
}

export function MapExistingForm({ onMap, onCancel }: MapExistingFormProps) {
    return (
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
            <h3 className="text-xs uppercase font-bold text-indigo-400">Map to Existing ProductCode</h3>
            <p className="text-xs text-slate-400">Choose this if the billing code already exists in EFM RateEngine catalog.</p>
            <div className="flex gap-2">
                <select
                    onChange={e => {
                        if (e.target.value) {
                            onMap(e.target.value);
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
                    onClick={onCancel}
                    className="px-3 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}
