'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Home, FileText, Users } from 'lucide-react';
import { useAuth } from '@/context/auth-context';
import { Button } from '@/components/ui/button';

export default function AppHeader() {
  const pathname = usePathname();
  const { user, logout } = useAuth();

  const navItems = [
    { href: '/', label: 'Dashboard', icon: Home },
    { href: '/quotes', label: 'Quotes', icon: FileText },
    { href: '/customers', label: 'Customers', icon: Users },
  ];

  return (
    <header className="w-full h-16 border-b bg-white flex items-center px-6">
      <div className="flex items-center gap-8 flex-1">
        <Link href="/" className="flex items-center gap-2 text-xl font-bold text-primary">
          <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
            <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
            <line x1="12" y1="22.08" x2="12" y2="12" />
          </svg>
          RateEngine
        </Link>

        <nav className="flex items-center gap-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(item.href + '/');

            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2 px-4 py-2 rounded-md transition-colors ${isActive
                    ? 'bg-primary/10 text-primary font-medium'
                    : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                  }`}
              >
                <Icon className="w-4 h-4" />
                {item.label}
              </Link>
            );
          })}
        </nav>
      </div>

      {user && (
        <div className="flex items-center gap-4">
          <span className="text-sm text-muted-foreground">{user.username}</span>
          <Button variant="outline" size="sm" onClick={logout}>
            Logout
          </Button>
        </div>
      )}
    </header>
  );
}
