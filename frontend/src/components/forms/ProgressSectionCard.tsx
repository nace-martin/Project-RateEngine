"use client";

import type { ReactNode } from "react";
import { CheckCircle2, CircleDot, PencilLine } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type ProgressSectionStatus = "active" | "completed";

type ProgressSectionCardProps = {
  step: number;
  title: string;
  status: ProgressSectionStatus;
  summary: ReactNode;
  children?: ReactNode;
  actionLabel?: string;
  onAction?: () => void;
  className?: string;
};

const statusMeta: Record<
  ProgressSectionStatus,
  {
    badgeLabel: string;
    badgeClassName: string;
    icon: typeof CircleDot;
    iconClassName: string;
    cardClassName: string;
  }
> = {
  active: {
    badgeLabel: "Current step",
    badgeClassName: "border-primary/20 bg-primary/10 text-primary",
    icon: CircleDot,
    iconClassName: "text-primary",
    cardClassName: "border-primary/30 shadow-md",
  },
  completed: {
    badgeLabel: "Done",
    badgeClassName: "border-emerald-200 bg-emerald-50 text-emerald-700",
    icon: CheckCircle2,
    iconClassName: "text-emerald-600",
    cardClassName: "border-emerald-200",
  },
};

export default function ProgressSectionCard({
  step,
  title,
  status,
  summary,
  children,
  actionLabel,
  onAction,
  className,
}: ProgressSectionCardProps) {
  const meta = statusMeta[status];
  const Icon = meta.icon;
  const isExpanded = status === "active";

  return (
    <Card className={cn("transition-all duration-200", meta.cardClassName, className)}>
      <CardHeader className={cn("gap-4", isExpanded ? "pb-5" : "pb-4")}>
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white text-sm font-semibold text-slate-700">
              {step}
            </div>
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2 text-lg">
                <Icon className={cn("h-5 w-5", meta.iconClassName)} />
                {title}
              </CardTitle>
              <div>{summary}</div>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Badge variant="outline" className={meta.badgeClassName}>
              {meta.badgeLabel}
            </Badge>
            {onAction ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="shrink-0"
                onClick={onAction}
              >
                {status === "completed" ? <PencilLine className="h-4 w-4" /> : null}
                {actionLabel}
              </Button>
            ) : null}
          </div>
        </div>
      </CardHeader>

      {isExpanded ? <CardContent>{children}</CardContent> : null}
    </Card>
  );
}
