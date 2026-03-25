"use client";

import { useConfirmDialog, type ConfirmOptions } from "@/context/confirm-dialog-context";

export function useConfirm() {
  const { confirm } = useConfirmDialog();
  return confirm;
}

export type { ConfirmOptions };
