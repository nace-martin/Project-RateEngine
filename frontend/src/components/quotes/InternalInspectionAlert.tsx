import { Alert, AlertDescription } from "@/components/ui/alert";
import Link from "next/link";
import { ArrowRight, ExternalLink } from "lucide-react";
import { getCustomerName } from "@/lib/quote-helpers";
import type { V3QuoteComputeResponse } from "@/lib/types";

export interface InternalInspectionAlertProps {
  quote: V3QuoteComputeResponse;
  isDomesticQuote: boolean;
  resolvedServiceScope: string;
  fxEntries: Array<[string, string]>;
  shipmentMetrics: {
    totalWeightKg: number;
    volumetricWeightKg: number;
    chargeableWeightKg: number;
  };
}

export default function InternalInspectionAlert({
  quote,
  isDomesticQuote,
  resolvedServiceScope,
  fxEntries,
  shipmentMetrics,
}: InternalInspectionAlertProps) {
  return (
    <div className="md:col-span-1">
      <Alert className="bg-slate-50 border-slate-200 shadow-sm relative overflow-hidden">
        {/* "Internal Only" Badge */}
        <div className="absolute top-0 right-0 bg-slate-200 text-slate-600 text-[10px] font-bold px-2 py-0.5 rounded-bl">
          INTERNAL USE ONLY
        </div>

        <AlertDescription className="grid grid-cols-2 lg:grid-cols-5 gap-4 text-sm mt-1">
          {/* Customer */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Customer</p>
            <p className="font-medium text-slate-900 truncate" title={getCustomerName(quote.customer)}>
              {getCustomerName(quote.customer)}
            </p>
          </div>

          {/* Sales Rep */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Sales Rep</p>
            <p className="font-medium text-slate-900">
              {quote.created_by || <span className="text-slate-400 italic">Unassigned</span>}
            </p>
          </div>

          {/* Rate Provider */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Rate Provider</p>
            <p className="font-medium text-slate-900 truncate" title={quote.rate_provider || "Internal"}>
              {quote.rate_provider || <span className="text-slate-400 italic">Internal</span>}
            </p>
          </div>

          {/* Routing */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Routing</p>
            <div className="font-medium text-slate-900 flex items-center gap-1">
              <span>{quote.origin_location?.split('-')[0] || quote.origin_location}</span>
              <ArrowRight className="h-3 w-3" />
              <span>{quote.destination_location?.split('-')[0] || quote.destination_location}</span>
            </div>
          </div>

          {/* Opportunity Link */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Opportunity</p>
            <p className="font-medium text-slate-900">
              {quote.opportunity ? (
                <Link
                  href={`/crm/opportunities/${quote.opportunity}`}
                  className="text-primary hover:underline flex items-center gap-1"
                >
                  View CRM
                  <ExternalLink className="h-3 w-3" />
                </Link>
              ) : (
                <span className="text-slate-400 italic">None</span>
              )}
            </p>
          </div>

          {isDomesticQuote ? (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase">Service Scope</p>
              <p className="font-medium text-slate-900">{resolvedServiceScope}</p>
            </div>
          ) : (
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase">FX Rate</p>
              <div className="font-medium text-slate-900 text-xs">
                {fxEntries.length > 1 ? (
                  <span className="text-slate-600">Multiple FX rates used</span>
                ) : fxEntries.length === 1 ? (
                  <div>{fxEntries[0][0]}: {String(fxEntries[0][1])}</div>
                ) : (
                  <span className="text-slate-400 italic">Base (PGK)</span>
                )}
              </div>
            </div>
          )}

          {/* Total Weight */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Total Weight</p>
            <p className="font-medium text-slate-900">
              {shipmentMetrics.totalWeightKg > 0
                ? `${shipmentMetrics.totalWeightKg.toLocaleString()} kg`
                : "0 kg"}
            </p>
          </div>

          {/* Volumetric Weight */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Volumetric Weight</p>
            <p className="font-medium text-slate-900">
              {shipmentMetrics.volumetricWeightKg > 0
                ? `${shipmentMetrics.volumetricWeightKg.toLocaleString()} kg`
                : "0 kg"}
            </p>
          </div>

          {/* Chargeable Weight (CW) */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Chargeable Weight (CW)</p>
            <p className="font-medium text-slate-900">
              {shipmentMetrics.chargeableWeightKg > 0
                ? `${shipmentMetrics.chargeableWeightKg.toLocaleString()} kg`
                : "0 kg"}
            </p>
          </div>

          {/* Validity */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Validity</p>
            <p className="font-medium text-slate-900">
              7 Days
            </p>
          </div>

          {/* Payment Terms */}
          <div>
            <p className="text-xs font-semibold text-slate-500 uppercase">Payment Terms</p>
            <p className="font-medium text-slate-900">
              {(() => {
                const term = (quote.payment_term || "Collect").toLowerCase();
                return term === 'credit' ? 'Credit (30 Days)' : term.charAt(0).toUpperCase() + term.slice(1);
              })()}
            </p>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
}
