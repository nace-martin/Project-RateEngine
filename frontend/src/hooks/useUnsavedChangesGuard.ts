"use client";

import { useCallback, useEffect } from "react";

export function useUnsavedChangesGuard(
  isDirty: boolean,
  message = "You have unsaved changes. Are you sure you want to leave?",
) {
  useEffect(() => {
    if (!isDirty) {
      return;
    }

    const handleBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = message;
      return message;
    };

    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [isDirty, message]);

  return useCallback(() => {
    if (!isDirty) {
      return true;
    }
    return window.confirm(message);
  }, [isDirty, message]);
}
