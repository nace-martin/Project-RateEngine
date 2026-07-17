import { SpotResolutionState } from "./spotResolutionState";

interface IgnoredItemsPanelProps {
  ignoredItems: SpotResolutionState["ignoredItems"];
  onUndoDecision: (decisionId: string) => void;
}

export function IgnoredItemsPanel({
  ignoredItems,
  onUndoDecision,
}: IgnoredItemsPanelProps) {
  if (ignoredItems.length === 0) {
    return null;
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">
        Ignored Items
      </h2>
      <div className="flex flex-col gap-2.5">
        {ignoredItems.map((item) => (
          <div
            key={item.id}
            className="bg-slate-950 border border-slate-855 rounded-xl p-3 text-xs flex justify-between items-center"
          >
            <div>
              <span className="text-[10px] text-slate-500 font-bold block uppercase tracking-wider">
                Reason: {item.ignored_reason}
              </span>
              <p className="text-slate-400 italic font-mono mt-1">
                &quot;{item.raw_text}&quot;
              </p>
            </div>
            <button
              onClick={() => onUndoDecision(item.id)}
              className="text-xs text-indigo-400 font-semibold hover:underline"
            >
              Reopen
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
