'use client';

import Link from 'next/link';
import { V3QuoteComputeResponse } from '@/lib/types';
import { useAuth } from '@/context/auth-context';
import ProtectedRoute from '@/components/protected-route';
import { useState, useEffect, useCallback } from 'react';
import { getQuotesV3 } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { extractErrorFromResponse } from '@/lib/utils';

// Corresponds to backend quotes.models.Quote.Status
const QUOTE_STATUSES = [
  'DRAFT',
  'FINAL',
  'SENT',
  'ACCEPTED',
  'LOST',
  'EXPIRED',
  'INCOMPLETE',
] as const;

export default function QuotesListPage() {
  const { user } = useAuth();
  const [quotes, setQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [count, setCount] = useState(0);
  const [hasNext, setHasNext] = useState(false);
  const [hasPrev, setHasPrev] = useState(false);
  const [statusFilter, setStatusFilter] = useState<string>('');

  const fetchQuotes = useCallback(async () => {
    if (!user) return;

    try {
      setLoading(true);
      const data = await getQuotesV3({ page, pageSize, status: statusFilter });

      const results = Array.isArray(data.results)
        ? (data.results as V3QuoteComputeResponse[])
        : [];

      setQuotes(results);
      setCount(typeof data.count === 'number' ? data.count : results.length);
      setHasNext(Boolean(data.next));
      setHasPrev(Boolean(data.previous));
      setError(null);
    } catch (err) {
      console.error('Error fetching quotes:', err);
      const errorMessage = err instanceof Error ? err.message : 'Failed to load quotes';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  }, [user, page, pageSize, statusFilter]);

  useEffect(() => {
    if (user) {
      fetchQuotes();
    }
  }, [user, fetchQuotes]);

  const canViewCOGS = () => {
    return user?.role === 'manager' || user?.role === 'finance';
  };

  if (loading && quotes.length === 0) {
    return (
      <ProtectedRoute>
        <main className="container mx-auto p-8">
          <div className="flex justify-between items-center mb-6">
            <h1 className="text-4xl font-bold">All Quotes</h1>
            <Button asChild>
              <Link href="/quotes/new">Create New Quote</Link>
            </Button>
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
          <Button asChild>
            <Link href="/quotes/new">Create New Quote</Link>
          </Button>
        </div>

        <div className="bg-white shadow-sm rounded-md p-4 mb-4 flex flex-wrap gap-3 items-end">
          <div>
            <label className="block text-xs text-gray-600 mb-1">Status</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All</option>
              {QUOTE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {status}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">Page Size</label>
            <select
              className="border rounded px-2 py-1 text-sm"
              value={pageSize}
              onChange={(e) => {
                setPageSize(parseInt(e.target.value, 10));
                setPage(1);
              }}
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
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Quote #</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Customer</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Route</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Mode</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Status</th>
                  {canViewCOGS() && (
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Cost (PGK)</th>
                  )}
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Total Sell</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Created</th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Actions</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {quotes.map((quote) => (
                  <tr key={quote.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">{quote.quote_number}</td>
                    {/* Assuming customer name will be added to the serializer. For now, showing ID. */}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.customer}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.origin_code} → {quote.destination_code}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.mode}</td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">{quote.status}</td>
                    {canViewCOGS() && (
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                        {/* Total cost is not in the V3 response yet */}
                        N/A
                      </td>
                    )}
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: quote.latest_version.totals.total_sell_fcy_currency,
                        maximumFractionDigits: 2,
                      }).format(Number(quote.latest_version.totals.total_sell_fcy))}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {new Date(quote.created_at).toLocaleDateString()}
                    </td>
                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      <Button variant="link" asChild>
                        <Link href={`/quotes/${quote.id}`}>View Details</Link>
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="flex items-center justify-between p-4 border-t bg-gray-50">
              <div className="text-sm text-gray-600">Total: {count}</div>
              <div className="flex items-center gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={!hasPrev || page <= 1}
                >
                  Previous
                </Button>
                <span className="text-sm">Page {page}</span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setPage((p) => p + 1)}
                  disabled={!hasNext}
                >
                  Next
                </Button>
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