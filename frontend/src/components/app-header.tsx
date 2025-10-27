'use client';

import { Button } from '@/components/ui/button';
import Link from 'next/link';
import { useAuth } from '@/context/auth-context';

export default function AppHeader() {
  const { user, logout, isAuthenticated } = useAuth();

  const canSeeSettings = user?.role === 'manager' || user?.role === 'finance';

  return (
    <header className="w-full border-b bg-white">
      <div className="container mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link href="/" className="font-bold text-lg text-gray-800">RateEngine</Link>
          {isAuthenticated && (
            <nav className="flex items-center gap-3 text-sm">
              <Button variant="link" asChild>
                <Link href="/quotes">Quotes</Link>
              </Button>
              <Button variant="link" asChild>
                <Link href="/customers">Customers</Link>
              </Button>
              {canSeeSettings && (
                <Button variant="link" asChild>
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
              <Button variant="secondary" size="sm" onClick={logout}>Logout</Button>
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

