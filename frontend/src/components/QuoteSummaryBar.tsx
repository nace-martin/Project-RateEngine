"use client";

import { V3QuoteComputeResponse } from "@/lib/types";
import { Plane, ArrowRight } from "lucide-react";

interface QuoteSummaryBarProps {
    quote: V3QuoteComputeResponse;
}

const formatCurrency = (amount: string | number | undefined, currency: string) => {
    const value = typeof amount === "number" ? amount : parseFloat(amount || "0");
    return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency,
        minimumFractionDigits: 2,
    }).format(value);
};

// Extract airport code from location string (e.g., "BNE - Brisbane" -> "BNE")
const getAirportCode = (location: string) => {
    const match = location.match(/^([A-Z]{3})/);
    return match ? match[1] : location.substring(0, 3).toUpperCase();
};

export default function QuoteSummaryBar({ quote }: QuoteSummaryBarProps) {
    const customerDetails =
        quote.customer && typeof quote.customer === "object"
            ? quote.customer
            : null;

    const customerName =
        customerDetails?.name ||
        customerDetails?.company_name ||
        (typeof quote.customer === "string" ? quote.customer : "Customer");
    const customerEmail = customerDetails?.email || null;

    // Get totals from latest version
    const totals = quote.latest_version?.totals;
    const currency = totals?.total_sell_fcy_currency || "PGK";
    const totalAmount = totals?.total_sell_fcy || "0";

    // Service and scope info
    const serviceScope = quote.service_scope || "D2D";

    return (
        <div className="bg-white border border-slate-200 rounded-lg overflow-hidden">
            <div className="grid grid-cols-4 divide-x divide-slate-200">
                {/* Customer Section */}
                <div className="p-4">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Customer
                    </div>
                    <div className="font-semibold text-slate-900 text-sm">
                        {customerName}
                    </div>
                    {customerEmail && (
                        <div className="text-xs text-slate-500 mt-0.5 truncate">
                            {customerEmail}
                        </div>
                    )}
                </div>

                {/* Route & Service Section */}
                <div className="p-4">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Route & Service
                    </div>
                    <div className="flex items-center gap-2 mb-2">
                        <span className="font-bold text-slate-900">
                            {getAirportCode(quote.origin_location)}
                        </span>
                        <ArrowRight className="w-4 h-4 text-slate-400" />
                        <span className="font-bold text-slate-900">
                            {getAirportCode(quote.destination_location)}
                        </span>
                    </div>
                    <div className="flex items-center gap-2 text-xs">
                        <span className="inline-flex items-center gap-1 text-slate-600">
                            <Plane className="w-3 h-3" />
                            {quote.mode || "AIR"}
                        </span>
                        <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-medium">
                            {quote.incoterm}
                        </span>
                        <span className="bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded text-[10px] font-medium uppercase">
                            {quote.payment_term}
                        </span>
                    </div>
                </div>

                {/* Service Details Section */}
                <div className="p-4">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-400 mb-2">
                        Service Details
                    </div>
                    <div className="font-semibold text-slate-900 text-sm">
                        {serviceScope === "D2D" ? "Door to Door" :
                            serviceScope === "A2D" ? "Airport to Door" :
                                serviceScope === "D2A" ? "Door to Airport" :
                                    serviceScope === "A2A" ? "Airport to Airport" :
                                        serviceScope}
                    </div>
                    <div className="text-xs text-slate-500 mt-0.5">
                        {quote.shipment_type} • {quote.mode}
                    </div>
                </div>

                {/* Total Estimated Cost Section */}
                <div className="p-4 bg-blue-50">
                    <div className="text-[10px] font-semibold uppercase tracking-wider text-blue-600 mb-2">
                        Total Estimated Cost
                    </div>
                    <div className="flex items-baseline gap-1">
                        <span className="text-xs font-medium text-blue-600">{currency}</span>
                        <span className="font-bold text-xl text-blue-700">
                            {formatCurrency(totalAmount, currency).replace(/^[A-Z]{3}\s*/, "").replace(/^\$/, "")}
                        </span>
                    </div>
                    <div className="text-[10px] text-blue-500 mt-0.5">
                        Excl. GST
                    </div>
                </div>
            </div>
        </div>
    );
}
