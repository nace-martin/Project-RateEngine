"use client";

import React from "react";

interface AddChargeFormProps {
    addName: string;
    onAddNameChange: (value: string) => void;
    addBucket: string;
    onAddBucketChange: (value: string) => void;
    addCurrency: string;
    onAddCurrencyChange: (value: string) => void;
    addAmount: string;
    onAddAmountChange: (value: string) => void;
    addUnit: string;
    onAddUnitChange: (value: string) => void;
    addProductCode: string;
    onAddProductCodeChange: (value: string) => void;
    onAdd: () => void;
    onCancel: () => void;
}

export function AddChargeForm({
    addName,
    onAddNameChange,
    addBucket,
    onAddBucketChange,
    addCurrency,
    onAddCurrencyChange,
    addAmount,
    onAddAmountChange,
    addUnit,
    onAddUnitChange,
    addProductCode,
    onAddProductCodeChange,
    onAdd,
    onCancel,
}: AddChargeFormProps) {
    return (
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
            <h3 className="text-xs uppercase font-bold text-indigo-400">Add manually as draft charge line</h3>
            <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                    <label className="text-slate-500 block mb-1">Charge Name</label>
                    <input
                        type="text"
                        value={addName}
                        onChange={e => onAddNameChange(e.target.value)}
                        placeholder="e.g. Handling Fee"
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Section Bucket</label>
                    <select
                        value={addBucket}
                        onChange={e => onAddBucketChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    >
                        <option value="origin_charges">Origin Charges</option>
                        <option value="destination_charges">Destination Charges</option>
                        <option value="airfreight">Air Freight Linehaul</option>
                    </select>
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Currency</label>
                    <input
                        type="text"
                        value={addCurrency}
                        onChange={e => onAddCurrencyChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Amount</label>
                    <input
                        type="text"
                        value={addAmount}
                        onChange={e => onAddAmountChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Unit Spec</label>
                    <input
                        type="text"
                        value={addUnit}
                        onChange={e => onAddUnitChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Mapping Code (Optional)</label>
                    <input
                        type="text"
                        value={addProductCode}
                        onChange={e => onAddProductCodeChange(e.target.value)}
                        placeholder="Approved ProductCode"
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
            </div>
            <div className="flex gap-2 justify-end mt-2">
                <button
                    onClick={onAdd}
                    className="px-4 py-2 bg-indigo-600 text-white rounded text-xs font-semibold"
                >
                    Confirm and Add
                </button>
                <button
                    onClick={onCancel}
                    className="px-4 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                >
                    Cancel
                </button>
            </div>
        </div>
    );
}
