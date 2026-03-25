"use client";

import * as React from "react";

import { cn } from "@/lib/utils";

type PageActionBarProps = {
  children: React.ReactNode;
  className?: string;
};

export default function PageActionBar({
  children,
  className,
}: PageActionBarProps) {
  return (
    <div
      className={cn(
        "flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:flex-row sm:items-center",
        "sm:justify-end",
        className,
      )}
    >
      <div className="flex flex-wrap items-center gap-3 sm:justify-end">
        {children}
      </div>
    </div>
  );
}
