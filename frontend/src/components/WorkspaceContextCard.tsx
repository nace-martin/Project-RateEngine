"use client";

import { useAuth } from "@/context/auth-context";
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
  const { user } = useAuth();
  const organization = user?.organization;
  const brandName = organization?.branding?.display_name || organization?.name || "RateEngine";

  return (
    <Card className="mb-6 border-slate-200 bg-slate-50/70 shadow-sm">
      <CardContent className="w-full px-6 py-5">
        <div className="min-w-0 space-y-2">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="text-sm text-slate-700">{description}</p>
          {note && <p className="text-xs text-slate-600">{note}</p>}
          <p className="pt-1 text-xs font-medium uppercase tracking-[0.18em] text-slate-500">
            Workspace: {brandName}
          </p>
        </div>
      </CardContent>
    </Card>
  );
}
