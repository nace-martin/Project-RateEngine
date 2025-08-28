'use client';

import Link from 'next/link';
import { Quote } from '@/lib/types';
import { useAuth } from '@/context/auth-context';
import ProtectedRoute from '@/components/protected-route';
import { useState, useEffect } from 'react';

export default function QuotesListPage() {
  const { user } = useAuth();
  const [quotes, setQuotes] = useState<Quote[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        
        const res = await fetch(`${apiBase}/quotes/`, {
          headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
          },
        });

        if (!res.ok) {
          throw new Error(`Failed to fetch quotes (${res.status})`);
        }

        const data = await res.json();
        if (!Array.isArray(data)) {
          throw new Error('Invalid response format from server');
        }
        
        const quotesData = data as Quote[];
        // Sort so the newest quotes appear first
        quotesData.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
        setQuotes(quotesData);
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