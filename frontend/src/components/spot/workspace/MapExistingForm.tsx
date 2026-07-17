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
    onMap: (productCode: string) => void;
    onCancel: () => void;
}

export function MapExistingForm({ productCodes, isLoadingProductCodes, productCodeLoadError, onMap, onCancel }: MapExistingFormProps) {
    const options = productCodes.map(productCode => ({
        value: productCode.code,
        label: `${productCode.code} (${productCode.description})`
    }));
    return (
        <div className="bg-slate-950 border border-slate-850 p-4 rounded-xl flex flex-col gap-3">
            <h3 className="text-xs uppercase font-bold text-indigo-400">Map to Existing ProductCode</h3>
            <p className="text-xs text-slate-400">Choose this if the billing code already exists in EFM RateEngine catalog.</p>
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
