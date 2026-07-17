interface FinalReviewPanelProps {
  checklistIssuesResolved: boolean;
  checklistNoUnknown: boolean;
  checklistProductCodesVerified: boolean;
  unresolvedCount: number;
  canFinishReview: boolean;
  canUsePrototypeOverride: boolean;
  isLive: boolean;
  isReviewLocked: boolean;
  prototypeOverride: boolean;
  onTogglePrototypeOverride: () => void;
  onFinalizeReview: () => void;
}

export function FinalReviewPanel({
  checklistIssuesResolved,
  checklistNoUnknown,
  checklistProductCodesVerified,
  unresolvedCount,
  canFinishReview,
  canUsePrototypeOverride,
  isLive,
  isReviewLocked,
  prototypeOverride,
  onTogglePrototypeOverride,
  onFinalizeReview,
}: FinalReviewPanelProps) {
  return (
    <div className="mt-4 flex flex-col items-center gap-4 border-t border-slate-800 pt-6">
      <div className="w-full bg-slate-900 border border-slate-800 rounded-xl p-4 text-xs flex flex-col gap-2.5">
        <h3 className="font-bold text-slate-300 uppercase tracking-wider mb-1">
          Final Review Checklist
        </h3>

        <div className="flex items-center justify-between border-b border-slate-850 pb-2">
          <div>
            <span className="text-slate-200 block font-semibold">
              All review items resolved
            </span>
            <span className="text-slate-400 text-[10px]">
              {checklistIssuesResolved
                ? "Complete"
                : `${unresolvedCount} charges still need action.`}
            </span>
          </div>
          <span
            className={
              checklistIssuesResolved
                ? "text-emerald-400 font-semibold"
                : "text-amber-400"
            }
          >
            {checklistIssuesResolved ? "Complete" : "Pending"}
          </span>
        </div>

        <div className="flex items-center justify-between border-b border-slate-850 pb-2">
          <div>
            <span className="text-slate-200 block font-semibold">
              No unknown commercial charges remain
            </span>
            <span className="text-slate-400 text-[10px]">
              {checklistNoUnknown
                ? "Complete"
                : "Unmapped extracted charge block exists."}
            </span>
          </div>
          <span
            className={
              checklistNoUnknown
                ? "text-emerald-400 font-semibold"
                : "text-amber-400"
            }
          >
            {checklistNoUnknown ? "Complete" : "Pending"}
          </span>
        </div>

        <div className="flex items-center justify-between pb-2">
          <div>
            <span className="text-slate-200 block font-semibold">
              No included charge is missing a ProductCode mapping
            </span>
            <span className="text-slate-400 text-[10px]">
              {checklistProductCodesVerified
                ? "Complete"
                : "Include charge has no mapped billing code."}
            </span>
          </div>
          <span
            className={
              checklistProductCodesVerified
                ? "text-emerald-400 font-semibold"
                : "text-amber-400"
            }
          >
            {checklistProductCodesVerified ? "Complete" : "Pending"}
          </span>
        </div>
      </div>

      {!canFinishReview && !canUsePrototypeOverride && (
        <div className="w-full bg-red-950/20 border border-red-900/60 rounded-xl p-4 text-xs text-red-200">
          <span className="font-bold block mb-1">
            Finish Review unavailable
          </span>
          <span>
            Resolve all pending issues and verify ProductCode mappings to
            complete review.
          </span>
        </div>
      )}

      <div className="w-full flex flex-col sm:flex-row justify-between items-center gap-4">
        {!isLive && (
          <div className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              id="proto-override"
              checked={prototypeOverride}
              onChange={onTogglePrototypeOverride}
              className="rounded bg-slate-950 border-slate-800 text-indigo-600 focus:ring-indigo-500 w-4.5 h-4.5"
            />
            <label
              htmlFor="proto-override"
              className="text-slate-400 cursor-pointer font-medium select-none"
            >
              Prototype override only — not available for production.
            </label>
          </div>
        )}
        {isLive && <div />} {/* spacer to maintain justify-between layout alignment when checkbox is hidden */}
        <button
          disabled={
            isReviewLocked || (!canFinishReview && !canUsePrototypeOverride)
          }
          onClick={onFinalizeReview}
          className="px-8 py-3 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white rounded-xl font-bold text-sm shadow-xl shadow-indigo-900/40 w-full sm:w-auto text-center transition"
        >
          {isReviewLocked ? "Review Finalized" : "Finalize Review"}
        </button>
      </div>

      {!isLive && (
        <div className="text-center text-xs text-slate-500 mt-2">
          Prototype only — Changes made will not be permanently saved.
        </div>
      )}
    </div>
  );
}
