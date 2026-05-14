"use client";

import { Download, Mail } from "lucide-react";

type PublicQuoteActionsProps = {
  quoteNumber: string;
  supportEmail?: string | null;
  brandPrimary: string;
  brandAccent: string;
};

export function PublicQuoteActions({
  quoteNumber,
  supportEmail,
  brandPrimary,
  brandAccent,
}: PublicQuoteActionsProps) {
  const approvalHref = supportEmail
    ? `mailto:${supportEmail}?subject=${encodeURIComponent(`Approval for ${quoteNumber}`)}`
    : undefined;

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={() => window.print()}
        className="inline-flex h-10 w-full items-center justify-center gap-2 whitespace-nowrap rounded-md border border-slate-300 bg-white px-4 text-sm font-semibold text-slate-800 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
      >
        <Download className="h-4 w-4" aria-hidden="true" />
        Print / Save PDF
      </button>
      {approvalHref ? (
        <a
          href={approvalHref}
          className="inline-flex h-10 w-full items-center justify-center gap-2 whitespace-nowrap rounded-md px-4 text-sm font-semibold text-white shadow-sm transition hover:brightness-95"
          style={{ backgroundColor: brandAccent || brandPrimary }}
        >
          <Mail className="h-4 w-4" aria-hidden="true" />
          Approve by Email
        </a>
      ) : null}
    </div>
  );
}
