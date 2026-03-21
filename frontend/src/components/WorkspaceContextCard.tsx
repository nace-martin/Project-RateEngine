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
  const organizationSlug = organization?.slug || "unassigned";

  return (
    <Card className="mb-6 border-slate-200 bg-slate-50/70 shadow-sm">
      <CardContent className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-5 sm:flex-row sm:items-center sm:justify-between sm:gap-6">
        <div className="min-w-0 flex-1 space-y-1">
          <p className="text-sm font-semibold text-slate-900">{title}</p>
          <p className="text-sm text-slate-700">{description}</p>
          {note && <p className="text-xs text-slate-600">{note}</p>}
        </div>

        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm sm:min-w-[240px] sm:max-w-[280px]">
          <p className="font-medium text-slate-900">{brandName}</p>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{organizationSlug}</p>
        </div>
      </CardContent>
    </Card>
  );
}
