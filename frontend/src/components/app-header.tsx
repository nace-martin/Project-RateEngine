'use client';

import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { useAuth } from '@/context/auth-context';

const navButtonClasses =
  'text-sm font-medium text-primary hover:text-primary hover:bg-primary/10 focus-visible:ring-primary/40';

export default function AppHeader() {
  const { user, logout, isAuthenticated } = useAuth();

  const canSeeSettings = user?.role === 'manager' || user?.role === 'finance';

  return (
    <header className="w-full border-b bg-white">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="font-bold text-lg text-primary">RateEngine</Link>
          {isAuthenticated && (
            <nav className="flex items-center gap-3 text-sm">
              <Button variant="ghost" className={navButtonClasses} asChild>
                <Link href="/quotes">Quotes</Link>
              </Button>
              <Button variant="ghost" className={navButtonClasses} asChild>
                <Link href="/customers">Customers</Link>
              </Button>
              {canSeeSettings && (
                <Button variant="ghost" className={navButtonClasses} asChild>
                  <Link href="/settings">System Settings</Link>
                </Button>
              )}
            </nav>
          )}
        </div>
        <div className="text-sm text-gray-700 flex items-center gap-3">
          {isAuthenticated ? (
            <>
              <span>{user?.username} ({user?.role})</span>
              <Button variant="outline" size="sm" onClick={logout}>Logout</Button>
            </>
          ) : (
            <Button asChild size="sm">
              <Link href="/login">Login</Link>
            </Button>
          )}
        </div>
      </div>
    </header>
  );
}

