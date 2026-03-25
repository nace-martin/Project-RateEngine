"use client";

import { useRouter } from "next/navigation";
import { X } from "lucide-react";
import { Button } from "@/components/ui/button";

type PageCancelButtonProps = {
  href?: string;
  isDirty?: boolean;
  confirmMessage?: string;
  label?: string;
  className?: string;
  disabled?: boolean;
  confirmLeave?: () => boolean | Promise<boolean>;
};

export default function PageCancelButton({
  href = "/quotes",
  isDirty = false,
  confirmMessage = "Discard this quote?",
  label = "Cancel",
  className,
  disabled = false,
  confirmLeave,
}: PageCancelButtonProps) {
  const router = useRouter();

  const handleClick = async () => {
    if (disabled) {
      return;
    }
    const canLeave = confirmLeave
      ? await confirmLeave()
      : (!isDirty || window.confirm(confirmMessage));
    if (!canLeave) {
      return;
    }

    if (href) {
      router.push(href);
      return;
    }

    router.back();
  };

  return (
    <Button
      type="button"
      variant="outline"
      className={className}
      onClick={handleClick}
      disabled={disabled}
    >
      <X className="h-4 w-4" />
      {label}
    </Button>
  );
}
