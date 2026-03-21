"use client";

import { Building2 } from "lucide-react";

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
  const logoUrl = organization?.branding?.logo_url || null;

  return (
    <Card className="mb-6 border-slate-200 bg-slate-50/70 shadow-sm">
      <CardContent className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-6 py-5 sm:flex-row sm:items-center sm:gap-6">
        <div className="flex min-w-0 flex-1 items-center gap-4 sm:gap-5">
          <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
            {logoUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={logoUrl} alt={`${brandName} logo`} className="max-h-8 max-w-8 object-contain" />
            ) : (
              <Building2 className="h-5 w-5 text-slate-600" />
            )}
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-sm font-semibold text-slate-900">{title}</p>
            <p className="text-sm text-slate-600">{description}</p>
            {note && <p className="text-xs text-slate-600">{note}</p>}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm shadow-sm sm:ml-auto sm:min-w-[240px] sm:max-w-[280px]">
          <p className="font-medium text-slate-900">{brandName}</p>
          <p className="text-xs uppercase tracking-[0.18em] text-slate-500">{organizationSlug}</p>
        </div>
      </CardContent>
    </Card>
  );
}
