'use client';

import Link from 'next/link';
import { Quote, QuoteStatus } from '@/lib/types';
import { useAuth } from '@/context/auth-context';
import ProtectedRoute from '@/components/protected-route';
import { useState, useEffect } from 'react';
import { extractErrorFromResponse } from '@/lib/utils';

export default function QuotesListPage() {
  const { user } = useAuth();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [organizations, setOrganizations] = useState<{ id: number; name: string }[]>([]);
  const [orgId, setOrgId] = useState<string>('');
  const [statusFilter, setStatusFilter] = useState<'' | QuoteStatus>('');

  useEffect(() => {
    const fetchQuotes = async () => {
      if (!user) return;
      
      try {
        setLoading(true);
        const apiBase = process.env.NEXT_PUBLIC_API_BASE;
        const token = localStorage.getItem('authToken');
        
        if (!apiBase) {
          throw new Error('API configuration error');
        }

        const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
        if (orgId) params.set('org_id', orgId);
        if (statusFilter) params.set('status', statusFilter);

        const res = await fetch(`${apiBase}/quotes/?${params.toString()}`, {
          headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
          },
        });

        if (!res.ok) {
          const msg = await extractErrorFromResponse(res, `Failed to fetch quotes (${res.status})`);
          throw new Error(msg);
        }

        const data = await res.json();
        // Expect DRF paginated shape
        const results = Array.isArray(data.results) ? (data.results as Quote[]) : [];
        setQuotes(results);
        setCount(typeof data.count === 'number' ? data.count : results.length);
        setHasNext(Boolean(data.next));
        setHasPrev(Boolean(data.previous));
        setError(null);
      } catch (err) {
        console.error('Error fetching quotes:', err);
        setError(err instanceof Error ? err.message : 'Failed to load quotes');
      } finally {
        setLoading(false);
      }
    };

    if (user) {
      fetchQuotes();
    }
  }, [user, page, pageSize, orgId, statusFilter]);

  // Load organizations for filter dropdown
  useEffect(() => {
    const loadOrgs = async () => {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      const token = localStorage.getItem('authToken');
      if (!apiBase || !user) return;
      try {
        const res = await fetch(`${apiBase}/organizations/`, {
          headers: { ...(token ? { 'Authorization': `Token ${token}` } : {}) },
        });
        if (!res.ok) return; // best-effort
        const data = await res.json();
        if (Array.isArray(data)) setOrganizations(data);
      } catch {}
    };
    loadOrgs();
  }, [user]);

  // Function to determine if user can see COGS data
  const canViewCOGS = () => {
    return user?.role === 'manager' || user?.role === 'finance';
  };

  if (loading) {
    return (
      <ProtectedRoute>
        <main className="container mx-auto p-8">
          <div className="flex justify-between items-center mb-6">
            <h1 className="text-4xl font-bold">All Quotes</h1>
            <Link href="/quotes/new" className="bg-blue-600 text-white font-bold py-2 px-4 rounded-md hover:bg-blue-700 transition-colors">
              Create New Quote
            </Link>
          </div>
          <div className="text-center py-8">Loading quotes...</div>
        </main>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <main className="container mx-auto p-8">
        <div className="flex justify-between items-center mb-6">
          <h1 className="text-4xl font-bold">All Quotes</h1>
          <Link href="/quotes/new" className="bg-blue-600 text-white font-bold py-2 px-4 rounded-md hover:bg-blue-700 transition-colors">
            Create New Quote
          </Link>
        </div>

        <div className="bg-white shadow-sm rounded-md p-4 mb-4 flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-600 mb-1">Organization</label>
            <select
              className="border rounded px-2 py-1 text-sm min-w-[220px]"
              value={orgId}
              onChange={(e) => { setOrgId(e.target.value); setPage(1); }}
            >
              <option value="">All</option>
              {organizations.map((o) => (
                <option key={o.id} value={String(o.id)}>{o.name}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Status</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={statusFilter}
              onChange={(e) => { setStatusFilter(e.target.value as any); setPage(1); }}
            >
              <option value="">All</option>
              <option value={QuoteStatus.PENDING_RATE}>Pending Rate</option>
              <option value={QuoteStatus.COMPLETE}>Complete</option>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Page Size</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={pageSize}
              onChange={(e) => { setPageSize(parseInt(e.target.value, 10)); setPage(1); }}
            >
              <option value={10}>10</option>
              <option value={25}>25</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
          </div>
        </div>

        {error ? (
          <div className="bg-white shadow-md rounded-lg p-6">
            <p className="text-red-500 font-medium">Unable to load quotes: {error}</p>
            <p className="text-gray-500 mt-2">Please check your connection and ensure the API server is running.</p>
          </div>
        ) : quotes.length > 0 ? (
          <div className="bg-white shadow-md rounded-lg overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Client</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Route</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mode</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Weight (kg)</th>
                  {canViewCOGS() && (
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Base Cost</th>
                  )}
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Sell</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {quotes.map((quote) => (
                  <tr key={quote.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{quote.client.name}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.origin} → {quote.destination}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.mode}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {quote.status === QuoteStatus.PENDING_RATE ? 'Pending Rate' : (quote.status || 'Complete')}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.chargeable_weight_kg}</td>
                    {canViewCOGS() && (
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {Intl.NumberFormat('en-US', {
                          style: 'currency',
                          currency: 'PGK',
                          maximumFractionDigits: 2,
                        }).format(Number(quote.base_cost ?? 0))}
                      </td>
                    )}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: 'PGK',
                        maximumFractionDigits: 2,
                      }).format(Number(quote.total_sell ?? 0))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(quote.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <Link href={`/quotes/${quote.id}`} className="text-blue-600 hover:underline font-semibold">
                        View Details
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between p-4 border-t bg-gray-50">
              <div className="text-sm text-gray-600">Total: {count}</div>
              <div className="flex items-center gap-2">
                <button
                  className="px-3 py-1 rounded border text-sm disabled:opacity-50"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={!hasPrev || page <= 1}
                >
                  Previous
                </button>
                <span className="text-sm">Page {page}</span>
                <button
                  className="px-3 py-1 rounded border text-sm disabled:opacity-50"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!hasNext}
                >
                  Next
                </button>
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-white shadow-md rounded-lg p-6 text-center text-gray-500">
            No quotes found.
          </div>
        )}
      </main>
    </ProtectedRoute>
  );
}
