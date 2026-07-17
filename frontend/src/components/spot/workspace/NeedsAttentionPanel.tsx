import { SpotWorkspaceIssue } from "./spotResolutionState";

interface NeedsAttentionPanelProps {
  items: SpotWorkspaceIssue[];
  onSelectIssue: (issueId: string) => void;
}

export function NeedsAttentionPanel({
  items,
  onSelectIssue,
}: NeedsAttentionPanelProps) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-sm">
      <h2 className="text-sm font-bold uppercase tracking-wider text-slate-400 mb-3">
        Still Needs Attention
      </h2>
      <div className="flex flex-col gap-2.5">
        {items.map((item) => (
          <div
            key={`${item.type}-${item.id}`}
            className="bg-slate-950 border border-slate-850 rounded-xl p-3 flex justify-between items-center text-xs"
          >
            <div>
              <strong className="block text-slate-200">{item.title}</strong>
              <span className="text-slate-400 mt-0.5 block">
                {item.problem}
              </span>
            </div>
            <button
              onClick={() => onSelectIssue(item.id)}
              className="px-2.5 py-1.5 bg-indigo-600/30 hover:bg-indigo-600 border border-indigo-900 text-indigo-300 hover:text-white rounded font-semibold transition"
            >
              Resolve Now
            </button>
          </div>
        ))}
      </div>
    </div>
  );
}
