'use client';

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
              <Link href="/quotes" className="text-gray-700 hover:text-blue-600 font-medium">Quotes</Link>
              {canSeeSettings && (
                <Link href="/settings" className="text-gray-700 hover:text-blue-600 font-medium">System Settings</Link>
              )}
            </nav>
          )}
        </div>
        <div className="text-sm text-gray-700 flex items-center gap-3">
          {isAuthenticated ? (
            <>
              <span>{user?.username} ({user?.role})</span>
              <button onClick={logout} className="px-3 py-1 rounded bg-gray-100 hover:bg-gray-200">Logout</button>
            </>
          ) : (
            <Link href="/login" className="px-3 py-1 rounded bg-blue-600 text-white hover:bg-blue-700">Login</Link>
          )}
        </div>
      </div>
    </header>
  );
}

