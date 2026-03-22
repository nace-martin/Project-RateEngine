"use client";

import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";

type PageCancelButtonProps = {
  href?: string;
  isDirty?: boolean;
  confirmMessage?: string;
  label?: string;
  className?: string;
};

export default function PageCancelButton({
  href = "/quotes",
  isDirty = false,
  confirmMessage = "Discard this quote?",
  label = "Cancel",
  className,
}: PageCancelButtonProps) {
  const router = useRouter();

  const handleClick = () => {
    if (isDirty && !window.confirm(confirmMessage)) {
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
    >
      {label}
    </Button>
  );
}
