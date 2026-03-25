"use client";

import type { ReactNode } from "react";

import PageActionBar from "@/components/navigation/PageActionBar";
import { Button } from "@/components/ui/button";

type QuoteWorkflowActionBarProps = {
  secondaryAction?: ReactNode;
  primaryLabel: string;
  onPrimaryClick?: () => void;
  primaryType?: "button" | "submit";
  primaryDisabled?: boolean;
  primaryLoading?: boolean;
  primaryLoadingText?: string;
};

export default function QuoteWorkflowActionBar({
  secondaryAction,
  primaryLabel,
  onPrimaryClick,
  primaryType = "button",
  primaryDisabled = false,
  primaryLoading = false,
  primaryLoadingText,
}: QuoteWorkflowActionBarProps) {
  return (
    <PageActionBar className="border-0 bg-transparent p-0 shadow-none">
      {secondaryAction}
      <Button
        type={primaryType}
        size="lg"
        disabled={primaryDisabled}
        onClick={onPrimaryClick}
        loading={primaryLoading}
        loadingText={primaryLoadingText}
      >
        {primaryLabel}
      </Button>
    </PageActionBar>
  );
}
