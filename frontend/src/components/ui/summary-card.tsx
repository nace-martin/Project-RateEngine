import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export type SummaryLine = {
  text: ReactNode;
  emphasis?: "primary" | "secondary" | "tertiary";
};

export function SummaryStack({
  lines,
  className,
}: {
  lines: SummaryLine[];
  className?: string;
}) {
  return (
    <div className={cn("space-y-0.5", className)}>
      {lines.map((line, index) => (
        <div
          key={`${String(line.text)}-${index}`}
          className={cn(
            line.emphasis === "primary" && "text-sm font-medium text-foreground",
            line.emphasis === "secondary" && "text-sm text-muted-foreground",
            line.emphasis === "tertiary" && "text-xs text-slate-500",
          )}
        >
          {line.text}
        </div>
      ))}
    </div>
  );
}

export function SummaryCard({
  label,
  lines,
  className,
}: {
  label: string;
  lines: SummaryLine[];
  className?: string;
}) {
  return (
    <div className={cn("rounded-lg border border-slate-200 bg-slate-50 px-4 py-3", className)}>
      <p className="text-xs font-semibold uppercase tracking-wide text-slate-500">{label}</p>
      <SummaryStack lines={lines} className="mt-2" />
    </div>
  );
}

