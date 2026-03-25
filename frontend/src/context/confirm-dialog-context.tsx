"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

type ConfirmOptions = {
  title?: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: "default" | "destructive";
};

type ConfirmDialogContextType = {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
};

const ConfirmDialogContext = React.createContext<ConfirmDialogContextType | undefined>(undefined);

type PendingConfirm = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

export function ConfirmDialogProvider({ children }: { children: React.ReactNode }) {
  const [pendingConfirm, setPendingConfirm] = React.useState<PendingConfirm | null>(null);

  const closeDialog = React.useCallback((confirmed: boolean) => {
    setPendingConfirm((current) => {
      current?.resolve(confirmed);
      return null;
    });
  }, []);

  const confirm = React.useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setPendingConfirm({
        title: options.title ?? "Confirm action",
        description: options.description,
        confirmLabel: options.confirmLabel ?? "Confirm",
        cancelLabel: options.cancelLabel ?? "Cancel",
        variant: options.variant ?? "default",
        resolve,
      });
    });
  }, []);

  return (
    <ConfirmDialogContext.Provider value={{ confirm }}>
      {children}
      <Dialog
        open={Boolean(pendingConfirm)}
        onOpenChange={(open) => {
          if (!open) {
            closeDialog(false);
          }
        }}
      >
        <DialogContent showCloseButton={false}>
          <DialogHeader>
            <DialogTitle>{pendingConfirm?.title}</DialogTitle>
            <DialogDescription>{pendingConfirm?.description}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => closeDialog(false)}>
              {pendingConfirm?.cancelLabel ?? "Cancel"}
            </Button>
            <Button
              type="button"
              variant={pendingConfirm?.variant === "destructive" ? "destructive" : "default"}
              onClick={() => closeDialog(true)}
            >
              {pendingConfirm?.confirmLabel ?? "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </ConfirmDialogContext.Provider>
  );
}

export function useConfirmDialog() {
  const context = React.useContext(ConfirmDialogContext);
  if (!context) {
    throw new Error("useConfirmDialog must be used within a ConfirmDialogProvider");
  }
  return context;
}

export type { ConfirmOptions };
