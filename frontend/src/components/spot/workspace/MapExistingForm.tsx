"use client";

import React from "react";
import { Combobox } from "@/components/ui/combobox";

interface ProductCodeSelectorOption {
    code: string;
    description: string;
}

interface MapExistingFormProps {
    productCodes: ProductCodeSelectorOption[];
    isLoadingProductCodes: boolean;
    productCodeLoadError: string | null;
    onRetry: () => void;
    onMap: (productCode: string) => void;
    onCancel: () => void;
    collectChargeDetails?: boolean;
    selectedProductCode?: string;
    onProductCodeChange?: (value: string) => void;
    chargeName?: string;
    onChargeNameChange?: (value: string) => void;
    chargeBucket?: string;
    onChargeBucketChange?: (value: string) => void;
    chargeCurrency?: string;
    onChargeCurrencyChange?: (value: string) => void;
    chargeAmount?: string;
    onChargeAmountChange?: (value: string) => void;
    chargeUnit?: string;
    onChargeUnitChange?: (value: string) => void;
}

export function MapExistingForm({
    productCodes,
    isLoadingProductCodes,
    productCodeLoadError,
    onRetry,
    onMap,
    onCancel,
    collectChargeDetails = false,
    selectedProductCode = "",
    onProductCodeChange,
    chargeName = "",
    onChargeNameChange,
    chargeBucket = "",
    onChargeBucketChange,
    chargeCurrency = "",
    onChargeCurrencyChange,
    chargeAmount = "",
    onChargeAmountChange,
    chargeUnit = "flat",
    onChargeUnitChange,
}: MapExistingFormProps) {
    const options = productCodes.map(productCode => ({
        value: productCode.code,
        label: `${productCode.code} (${productCode.description})`
    }));
    return (
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
            <h3 className="text-xs uppercase font-bold text-indigo-400">Map to Existing ProductCode</h3>
            <p className="text-xs text-slate-400">Choose this if the billing code already exists in EFM RateEngine catalog.</p>
            {isLoadingProductCodes ? (
                <p className="text-xs text-slate-500">Loading ProductCodes for this shipment direction...</p>
            ) : null}
            {productCodeLoadError ? (
                <div className="flex items-center justify-between gap-2 rounded-lg border border-red-900/60 bg-red-950/30 px-3 py-2 text-xs text-red-200">
                    <span>{productCodeLoadError}</span>
                    <button
                        type="button"
                        onClick={onRetry}
                        className="rounded border border-red-800 px-2 py-1 font-semibold text-red-100 hover:border-red-600"
                    >
                        Retry
                    </button>
                </div>
            ) : null}
            <div className="flex gap-2">
                <div className="grow">
                    <Combobox
                        options={options}
                        placeholder="Search ProductCodes..."
                        emptyMessage={productCodeLoadError || "No ProductCodes found for this shipment direction."}
                        value={selectedProductCode}
                        onChange={value => {
                            if (collectChargeDetails) {
                                onProductCodeChange?.(value);
                            } else if (value) {
                                onMap(value);
                            }
                        }}
                        disabled={isLoadingProductCodes || Boolean(productCodeLoadError)}
                        buttonClassName="text-xs bg-slate-900 border border-slate-800 rounded p-2 text-slate-200 grow"
                    />
                </div>
                {!collectChargeDetails ? (
                    <button
                        onClick={onCancel}
                        className="px-3 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400"
                    >
                        Cancel
                    </button>
                ) : null}
            </div>
            {collectChargeDetails ? (
                <>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                        <div>
                            <label className="text-slate-500 block mb-1">Charge description</label>
                            <input type="text" value={chargeName} onChange={e => onChargeNameChange?.(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                        </div>
                        <div>
                            <label className="text-slate-500 block mb-1">Section Bucket</label>
                            <select value={chargeBucket} onChange={e => onChargeBucketChange?.(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5">
                                <option value="">Choose bucket...</option>
                                <option value="origin_charges">Origin Charges</option>
                                <option value="destination_charges">Destination Charges</option>
                                <option value="airfreight">Air Freight Linehaul</option>
                            </select>
                        </div>
                        <div>
                            <label className="text-slate-500 block mb-1">Currency</label>
                            <input type="text" value={chargeCurrency} onChange={e => onChargeCurrencyChange?.(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                        </div>
                        <div>
                            <label className="text-slate-500 block mb-1">Amount</label>
                            <input type="text" value={chargeAmount} onChange={e => onChargeAmountChange?.(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                        </div>
                        <div>
                            <label className="text-slate-500 block mb-1">Unit</label>
                            <input type="text" value={chargeUnit} onChange={e => onChargeUnitChange?.(e.target.value)} className="w-full bg-slate-900 border border-slate-800 rounded p-1.5" />
                        </div>
                    </div>
                    <div className="flex gap-2 justify-end mt-2">
                        <button onClick={() => onMap(selectedProductCode)} className="px-4 py-2 bg-indigo-600 text-white rounded text-xs font-semibold">
                            Confirm Mapping
                        </button>
                        <button onClick={onCancel} className="px-4 py-2 bg-slate-900 border border-slate-800 rounded text-xs text-slate-400">
                            Cancel
                        </button>
                    </div>
                </>
            ) : null}
        </div>
    );
}
