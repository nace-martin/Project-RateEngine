import { Loader2, Pencil, CheckCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { QuoteStatusActions } from "@/components/QuoteStatusBadge";
import type { V3QuoteComputeResponse } from "@/lib/types";

export interface QuoteDetailFooterProps {
  quote: V3QuoteComputeResponse;
  effectiveStatus: string;
  displayCurrency: string;
  displayAmount: number;
  canDownloadPDF: boolean;
  canEditQuote: boolean;
  pdfDownloading: boolean;
  onDownloadPDF: () => Promise<void>;
  onEditQuote: () => void;
  onStatusChange: () => void;
}

export default function QuoteDetailFooter({
  quote,
  effectiveStatus,
  displayCurrency,
  displayAmount,
  canDownloadPDF,
  canEditQuote,
  pdfDownloading,
  onDownloadPDF,
  onEditQuote,
  onStatusChange,
}: QuoteDetailFooterProps) {
  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-slate-200 shadow-[0_-4px_6px_-1px_rgba(0,0,0,0.05)] z-50">
      <div className="container mx-auto max-w-6xl px-4 py-4 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div>
            <p className="text-xs text-slate-500 uppercase font-semibold">Total Quote Amount</p>
            <p className="text-2xl font-bold text-slate-900">
              {displayCurrency} {displayAmount.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </p>
            <p className="text-[10px] text-slate-400">
              Inc. GST
            </p>
          </div>
          {/* Currency Exchange Badge placeholder (future task) */}
          {quote.latest_version?.totals?.currency !== 'PGK' && (
            <div className="hidden md:block px-3 py-1 bg-amber-50 rounded border border-amber-100 text-xs text-amber-700">
              <strong>Note:</strong> Pricing in {quote.latest_version?.totals?.currency}
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {canDownloadPDF && (
            <Button
              variant="outline"
              className="hidden sm:flex"
              disabled={pdfDownloading}
              onClick={onDownloadPDF}
            >
              {pdfDownloading ? (
                <>
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  Generating...
                </>
              ) : (
                "Download PDF"
              )}
            </Button>
          )}
          {/* Only show finalize button for DRAFT quotes, handled by QuoteStatusActions */}
          {effectiveStatus === "FINALIZED" || effectiveStatus === "SENT" || effectiveStatus === "EXPIRED" ? (
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <CheckCircle className="h-4 w-4 text-emerald-600" />
              <span>Quote {effectiveStatus.toLowerCase()}</span>
            </div>
          ) : canEditQuote && effectiveStatus === "DRAFT" ? (
            <>
              <Button
                variant="outline"
                size="sm"
                className="gap-2 mr-2 hidden sm:flex"
                onClick={onEditQuote}
              >
                <Pencil className="h-4 w-4" />
                Edit Quote
              </Button>
              <QuoteStatusActions
                quoteId={quote.id}
                status={quote.status}
                validUntil={quote.valid_until}
                hasMissingRates={quote.latest_version?.totals?.has_missing_rates || false}
                showDelete={false}
                onStatusChange={onStatusChange}
              />
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
