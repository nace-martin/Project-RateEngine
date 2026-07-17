import { AlertCircle, ChevronDown, ChevronUp, ShieldAlert } from "lucide-react";
import { DraftQuote } from "../../../lib/draft-quote-types";

interface VerificationWarningsPanelProps {
  showTotalsPanel: boolean;
  onToggleTotalsPanel: () => void;
  uniqueCurrencies: string[];
  subtotals: Record<string, number>;
  totalsValidation: DraftQuote["totals_validation"];
  explainTotals: boolean;
  onToggleExplainTotals: () => void;
}

export function VerificationWarningsPanel({
  showTotalsPanel,
  onToggleTotalsPanel,
  uniqueCurrencies,
  subtotals,
  totalsValidation,
  explainTotals,
  onToggleExplainTotals,
}: VerificationWarningsPanelProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-sm">
      <button
        onClick={onToggleTotalsPanel}
        className="w-full px-6 py-4 flex items-center justify-between text-left font-bold text-slate-50 bg-slate-900 hover:bg-slate-800/40 transition"
      >
        <div className="flex items-center gap-2">
          <ShieldAlert className="h-5 w-5 text-indigo-400" />
          <span>Verification Warnings & Totals</span>
        </div>
        {showTotalsPanel ? (
          <ChevronUp className="h-5 w-5 text-slate-400" />
        ) : (
          <ChevronDown className="h-5 w-5 text-slate-400" />
        )}
      </button>

      {showTotalsPanel && (
        <div className="border-t border-slate-800 p-5 bg-slate-900/40 flex flex-col gap-4">
          {uniqueCurrencies.length > 1 ? (
            <div className="bg-amber-955 border border-amber-900/60 rounded-xl p-4 flex flex-col gap-2">
              <div className="flex items-center gap-2 text-amber-400 font-bold text-sm">
                <AlertCircle className="h-4 w-4" />
                <span>Totals Need Review</span>
              </div>
              <p className="text-xs text-slate-300">
                Reason: This quote contains multiple currencies. A single
                calculations total is not safe to display.
              </p>

              <div className="mt-2 divide-y divide-slate-800 text-xs">
                {Object.entries(subtotals).map(([curr, sum]) => (
                  <div
                    key={curr}
                    className="py-1.5 flex justify-between font-mono"
                  >
                    <span className="text-slate-400">{curr} subtotal:</span>
                    <span className="text-slate-200">{sum.toFixed(2)}</span>
                  </div>
                ))}
                <div className="py-2 flex justify-between font-mono text-sm border-t border-slate-700">
                  <span className="text-indigo-300 font-semibold">
                    Supplier extracted total:
                  </span>
                  <span className="text-indigo-200 font-bold">
                    USD {totalsValidation.extracted_total?.toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          ) : (
            <div className="flex flex-col gap-3">
              <div className="flex justify-between items-center bg-slate-950 border border-slate-800 rounded-xl p-3 text-sm">
                <span className="text-slate-400">
                  Calculated sum difference:
                </span>
                <div className="flex items-center gap-2">
                  <span
                    className={`font-semibold ${totalsValidation.difference ? "text-red-400" : "text-emerald-400"}`}
                  >
                    USD {totalsValidation.difference?.toFixed(2) || "0.00"}
                  </span>
                  <button
                    onClick={onToggleExplainTotals}
                    className="text-xs text-indigo-400 font-semibold hover:underline"
                  >
                    [Explain]
                  </button>
                </div>
              </div>

              {explainTotals && (
                <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 flex flex-col gap-2 text-xs">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Calculated Sum:</span>
                    <span>
                      USD {totalsValidation.calculated_total?.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">
                      Extracted Total from document:
                    </span>
                    <span>
                      USD {totalsValidation.extracted_total?.toFixed(2)}
                    </span>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
