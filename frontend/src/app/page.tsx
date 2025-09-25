"use client";

import { useEffect, useState } from 'react';
import { Client } from '@/lib/types';
import { extractErrorFromResponse } from '@/lib/utils';
import ProtectedRoute from '@/components/protected-route';
import { useAuth } from '@/context/auth-context';

export default function HomePage() {
  const { user } = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Static list of clients
    const staticClients: Client[] = [
      { id: 1, name: 'Test Client 1', email: 'client1@example.com', phone: '123-456-7890', org_type: 'B2B', created_at: new Date().toISOString() },
      { id: 2, name: 'Test Client 2', email: 'client2@example.com', phone: '098-765-4321', org_type: 'B2C', created_at: new Date().toISOString() },
    ];
    setClients(staticClients);
    setLoading(false);
  }, [user]);

  return (
    <ProtectedRoute>
      <main className="container mx-auto p-8">
        <h1 className="text-4xl font-bold">Clients</h1>
        <p className="mt-2 text-lg text-gray-600">A list of clients from the database.</p>

        {loading && <div className="mt-6">Loading clients…</div>}
        {error && !loading && (
          <div className="mt-6 text-red-600">{error}</div>
        )}

        {!loading && !error && (
          <div className="mt-8">
            <ul className="divide-y divide-gray-200">
              {clients.map((client) => (
                <li key={client.id} className="py-4">
                  <p className="text-xl font-semibold text-gray-800">{client.name}</p>
                  <p className="text-sm text-gray-500">{client.email}</p>
                </li>
              ))}
            </ul>
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}
