"use client";

import { Card, CardContent } from "@/components/ui/card";

type WorkspaceContextCardProps = {
  title: string;
  description: string;
  note?: string;
};

export default function WorkspaceContextCard({
  title,
  description,
  note,
}: WorkspaceContextCardProps) {
  return (
    <Card className="mb-6 border-slate-200 bg-slate-50/70 shadow-sm">
      <CardContent className="w-full px-6 py-5">
        <div className="min-w-0 space-y-2">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="text-sm text-slate-700">{description}</p>
          {note && <p className="text-xs text-slate-600">{note}</p>}
        </div>
      </CardContent>
    </Card>
  );
}
