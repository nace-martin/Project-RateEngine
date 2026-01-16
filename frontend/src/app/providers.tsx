import { AuthProvider } from '@/context/auth-context';
import { ToastProvider } from '@/context/toast-context';
import { Toaster } from '@/components/toaster';
import { ReactNode } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <AuthProvider>
      <ToastProvider>
        {children}
        <Toaster />
      </ToastProvider>
    </AuthProvider>
  );
}
