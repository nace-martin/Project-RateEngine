"use client";

import { useEffect, useState } from 'react';
import { Client } from '@/lib/types';
import ProtectedRoute from '@/components/protected-route';
import { useAuth } from '@/context/auth-context';

export default function HomePage() {
  const { user } = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchClients = async () => {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      if (!apiBase) {
        setError('API base URL is not configured.');
        setLoading(false);
        return;
      }

      try {
        const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
        const res = await fetch(`${apiBase}/clients/`, {
          headers: {
            ...(token ? { Authorization: `Token ${token}` } : {}),
            'Content-Type': 'application/json',
          },
          cache: 'no-store',
        });

        if (!res.ok) {
          setError(`Failed to fetch clients: ${res.status}`);
          setClients([]);
        } else {
          const data = await res.json();
          setClients(Array.isArray(data) ? data : []);
        }
      } catch (e: any) {
        setError(e?.message || 'Unexpected error fetching clients');
        setClients([]);
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchClients();
    }
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
