'use client';

import ProtectedRoute from '@/components/protected-route';
import { useAuth } from '@/context/auth-context';

export default function SettingsPage() {
  const { user } = useAuth();
  const canSeeSettings = user?.role === 'manager' || user?.role === 'finance';

  return (
    <ProtectedRoute>
      <main className="container mx-auto p-8">
        <h1 className="text-3xl font-bold mb-4">System Settings</h1>
        {!canSeeSettings ? (
          <div className="text-red-600">You do not have access to view this page.</div>
        ) : (
          <div className="space-y-4">
            <p className="text-gray-600">Manage rate cards, CAF/FX and margin rules.</p>
            <div className="p-4 bg-white rounded shadow">
              <p className="text-gray-800">Settings UI coming soon.</p>
            </div>
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}

