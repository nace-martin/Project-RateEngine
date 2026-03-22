"use client";

import { useRouter } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";

type PageBackButtonProps = {
  fallbackHref: string;
  returnTo?: string | null;
  isDirty?: boolean;
  confirmLeave?: () => boolean;
  label?: string;
};

export default function PageBackButton({
  fallbackHref,
  returnTo,
  isDirty = false,
  confirmLeave,
  label = "Back",
}: PageBackButtonProps) {
  const router = useRouter();

  const handleClick = () => {
    const canLeave = confirmLeave ? confirmLeave() : (!isDirty || window.confirm("You have unsaved changes. Are you sure you want to leave?"));
    if (!canLeave) {
      return;
    }
    router.push(returnTo || fallbackHref);
  };

  return (
    <Button type="button" variant="ghost" className="mb-4 -ml-2 gap-2 px-2 text-slate-600 hover:text-slate-900" onClick={handleClick}>
      <ArrowLeft className="h-4 w-4" />
      {label}
    </Button>
  );
}
