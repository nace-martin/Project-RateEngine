'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useState } from 'react';
import AppHeader from '@/components/app-header';
import { InteractionLogSheet } from '@/components/crm/InteractionLogSheet';

function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tagName = target.tagName.toLowerCase();
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || target.isContentEditable;
}

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() || '';
  const [quickLogOpen, setQuickLogOpen] = useState(false);
  const hideInternalChrome = pathname === '/login' || pathname.startsWith('/public');

  useEffect(() => {
    if (hideInternalChrome) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.shiftKey && !event.ctrlKey && !event.metaKey && !event.altKey && event.key.toLowerCase() === 'l') {
        if (isTypingTarget(event.target)) {
          return;
        }
        event.preventDefault();
        setQuickLogOpen(true);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [hideInternalChrome]);

  if (hideInternalChrome) {
    return <main className="min-h-screen">{children}</main>;
  }

  return (
    <div className="flex flex-col h-screen overflow-hidden">
      <AppHeader onLogActivity={() => setQuickLogOpen(true)} />
      <main className="flex-1 overflow-y-auto p-6">{children}</main>
      <InteractionLogSheet open={quickLogOpen} onOpenChange={setQuickLogOpen} />
    </div>
  );
}
