"use client";

import React from "react";

interface RequestProductCodeFormProps {
    reqLabel: string;
    onReqLabelChange: (value: string) => void;
    reqSource: string;
    onReqSourceChange: (value: string) => void;
    reqCurrency: string;
    onReqCurrencyChange: (value: string) => void;
    reqAmount: string;
    onReqAmountChange: (value: string) => void;
    reqBucket: string;
    onReqBucketChange: (value: string) => void;
    reqUnit: string;
    onReqUnitChange: (value: string) => void;
    onSubmit: () => void;
    onCancel: () => void;
}

export function RequestProductCodeForm({
    reqLabel,
    onReqLabelChange,
    reqSource,
    onReqSourceChange,
    reqCurrency,
    onReqCurrencyChange,
    reqAmount,
    onReqAmountChange,
    reqBucket,
    onReqBucketChange,
    reqUnit,
    onReqUnitChange,
    onSubmit,
    onCancel,
}: RequestProductCodeFormProps) {
    return (
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
            <h3 className="text-xs uppercase font-bold text-indigo-400">Request New ProductCode</h3>
            <p className="text-xs text-slate-400">Choose this if the charge is legitimate but the code is missing from the master EFM database.</p>
            <div className="grid grid-cols-2 gap-3 text-xs">
                <div>
                    <label className="text-slate-500 block mb-1">Charge Name</label>
                    <input
                        type="text"
                        value={reqLabel}
                        onChange={e => onReqLabelChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Quote Extracted Text</label>
                    <input
                        type="text"
                        value={reqSource}
                        onChange={e => onReqSourceChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Currency</label>
                    <input
                        type="text"
                        value={reqCurrency}
                        onChange={e => onReqCurrencyChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Amount</label>
                    <input
                        type="text"
                        value={reqAmount}
                        onChange={e => onReqAmountChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    />
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Section Bucket</label>
                    <select
                        value={reqBucket}
                        onChange={e => onReqBucketChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    >
                        <option value="">Choose bucket...</option>
                        <option value="origin_charges">Origin Charges</option>
                        <option value="destination_charges">Destination Charges</option>
                        <option value="airfreight">Air Freight Linehaul</option>
                    </select>
                </div>
                <div>
                    <label className="text-slate-500 block mb-1">Unit</label>
                    <select
                        value={reqUnit}
                        onChange={e => onReqUnitChange(e.target.value)}
                        className="w-full bg-slate-900 border border-slate-800 rounded p-1.5"
                    >
                        <option value="flat">Flat</option>
                        <option value="per_kg">Per KG</option>
                        <option value="per_awb">Per AWB</option>
                        <option value="per_shipment">Per Shipment</option>
                        <option value="per_set">Per Set</option>
                    </select>
                </div>
            </div>
            <div className="flex gap-2 justify-end mt-2">
                <button
                    onClick={onSubmit}
                    className="px-4 py-2 bg-indigo-600 text-white rounded text-xs font-semibold"
                >
                    Submit Request
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
