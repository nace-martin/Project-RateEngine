"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

type PageBackButtonProps = {
  fallbackHref: string;
  returnTo?: string | null;
  isDirty?: boolean;
  confirmLeave?: () => boolean | Promise<boolean>;
  label?: string;
  disabled?: boolean;
  className?: string;
};

export default function PageBackButton({
  fallbackHref,
  returnTo,
  isDirty = false,
  confirmLeave,
  label = "Back",
  disabled = false,
  className,
}: PageBackButtonProps) {
  const router = useRouter();

  const handleClick = async () => {
    if (disabled) {
      return;
    }
    const canLeave = confirmLeave
      ? await confirmLeave()
      : (!isDirty || window.confirm("You have unsaved changes. Are you sure you want to leave?"));
    if (!canLeave) {
      return;
    }
    router.push(returnTo || fallbackHref);
  };

  return (
    <Button
      type="button"
      variant="ghost"
      className={className ?? "mb-4 -ml-2 gap-2 px-2 text-slate-600 hover:text-slate-900"}
      onClick={handleClick}
      disabled={disabled}
    >
      <ArrowLeft className="h-4 w-4" />
      {label}
    </Button>
  );
}
