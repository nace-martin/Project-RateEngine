'use client';

import { usePathname } from 'next/navigation';
import AppHeader from '@/components/app-header';

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const hideInternalChrome = pathname === '/login' || pathname.startsWith('/public');

  if (hideInternalChrome) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AppHeader />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
    </div>
  );
}
