'use client';

import { usePathname } from 'next/navigation';

export default function AppHeader() {
  const pathname = usePathname();

  // Simple breadcrumb-like title based on path
  const getTitle = () => {
    if (pathname === '/') return 'Dashboard';
    const parts = pathname.split('/').filter(Boolean);
    return parts.map(p => p.charAt(0).toUpperCase() + p.slice(1)).join(' / ');
  };

  return (
    <header className="w-full h-16 border-b bg-white/50 backdrop-blur-sm flex items-center px-6 sticky top-0 z-10">
      <h2 className="text-lg font-semibold text-foreground capitalize">
        {getTitle()}
      </h2>
    </header>
  );
}
