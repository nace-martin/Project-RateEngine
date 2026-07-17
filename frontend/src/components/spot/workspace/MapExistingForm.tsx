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
}

export function MapExistingForm({ productCodes, isLoadingProductCodes, productCodeLoadError, onRetry, onMap, onCancel }: MapExistingFormProps) {
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
                        onChange={value => {
                            if (value) {
                                onMap(value);
                            }
                        }}
                        disabled={isLoadingProductCodes || Boolean(productCodeLoadError)}
                        buttonClassName="text-xs bg-slate-900 border border-slate-800 rounded p-2 text-slate-200 grow"
                    />
                </div>
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
