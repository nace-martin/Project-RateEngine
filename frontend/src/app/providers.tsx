import { AuthProvider } from '@/context/auth-context';
import { ConfirmDialogProvider } from '@/context/confirm-dialog-context';
import { ToastProvider } from '@/context/toast-context';
import { Toaster } from '@/components/toaster';
import { ReactNode } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ConfirmDialogProvider>
        <ToastProvider>
          {children}
          <Toaster />
        </ToastProvider>
      </ConfirmDialogProvider>
    </AuthProvider>
  );
}
