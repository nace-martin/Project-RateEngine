import { Decision } from "./spotResolutionState";

interface ReviewDecisionsPanelProps {
  decisions: Decision[];
  onUndoDecision: (decisionId: string) => void;
}

export function ReviewDecisionsPanel({
  decisions,
  onUndoDecision,
}: ReviewDecisionsPanelProps) {
  if (decisions.length === 0) {
    return null;
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">
        Review Decisions
      </h2>
      <div className="flex flex-col gap-2 text-xs">
        {decisions.map((d) => (
          <div
            key={d.id}
            className="bg-slate-950 border border-slate-850 p-2.5 rounded-lg flex justify-between items-center"
          >
            <span className="text-slate-300">✓ {d.description}</span>
            <div className="flex gap-2">
              <button
                onClick={() => onUndoDecision(d.id)}
                className="text-xs text-indigo-400 font-semibold hover:underline"
              >
                {d.type === "map"
                  ? "Edit Mapping"
                  : d.type === "request"
                    ? "Edit Request"
                    : "Reopen"}
              </button>
              <button
                onClick={() => onUndoDecision(d.id)}
                className="text-xs text-slate-500 font-semibold hover:underline"
              >
                Undo
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
