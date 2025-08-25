"use client";

import { useState, useEffect } from 'react';

// We will define a more detailed Quote type here
interface QuoteDetail {
  id: number;
  client: {
    name: string;
  };
  origin: string;
  destination: string;
  mode: string;
  actual_weight_kg: string;
  volume_cbm: string;
  chargeable_weight_kg: string;
  rate_used_per_kg: string;
  base_cost: string;
  margin_pct: string;
  total_sell: string;
  created_at: string;
}

// Helper component for displaying each detail
const DetailRow = ({ label, value }: { label: string; value: string | number }) => (
  <div className="py-3 px-4 flex justify-between items-center border-b border-gray-200">
    <dt className="text-sm font-medium text-gray-600">{label}</dt>
    <dd className="text-sm font-semibold text-gray-900">{value}</dd>
  </div>
);

export default function QuoteDetailPage({ params }: { params: { id: string } }) {
  const [quote, setQuote] = useState<QuoteDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuote = async () => {
      if (!params.id) return;

      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      if (!apiBase) {
        throw new Error('API base URL is not configured');
      }
      try {
        setLoading(true);
        const res = await fetch(`${apiBase}/quotes/${params.id}/`, {
          signal: AbortSignal.timeout(10000) // 10 second timeout
        });        if (!res.ok) {
          throw new Error(`Failed to fetch quote. Status: ${res.status}`);
        }
        const data = await res.json();
        setQuote(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      } finally {
        setLoading(false);
      }
    };

    fetchQuote();
  }, [params.id]);

  if (loading) {
    return <main className="container mx-auto p-8"><p>Loading...</p></main>;
  }

  if (error) {
    return <main className="container mx-auto p-8"><p className="text-red-500">Error: {error}</p></main>;
  }

  if (!quote) {
    return <main className="container mx-auto p-8"><p>Quote not found.</p></main>;
  }

  return (
    <main className="container mx-auto p-8">
      <h1 className="text-4xl font-bold mb-4">Quote Details</h1>
      <p className="text-lg text-gray-500 mb-8">Quote ID: {quote.id}</p>

      <div className="bg-white shadow-md rounded-lg overflow-hidden max-w-2xl">
        <div className="p-6 bg-blue-600 text-white">
          <h2 className="text-2xl font-bold">{quote.client.name}</h2>
          <p className="text-blue-200">{new Date(quote.created_at).toLocaleString()}</p>
        </div>
        
        <dl className="divide-y divide-gray-200">
          <DetailRow label="Route" value={`${quote.origin} → ${quote.destination}`} />
          <DetailRow 
            label="Mode" 
            value={
              typeof quote.mode === 'string' && quote.mode.length > 0
                ? quote.mode.charAt(0).toUpperCase() + quote.mode.slice(1)
                : 'Unknown'
            }
          />
          <DetailRow label="Actual Weight" value={`${quote.actual_weight_kg} kg`} />
          <DetailRow label="Volume" value={`${quote.volume_cbm} CBM`} />
          <DetailRow label="Chargeable Weight" value={`${quote.chargeable_weight_kg} kg`} />
          <DetailRow label="Rate Used" value={`$${quote.rate_used_per_kg} / kg`} />
          <DetailRow label="Base Cost" value={`$${quote.base_cost}`} />
          <DetailRow label="Margin" value={`${quote.margin_pct}%`} />
          <div className="py-4 px-4 bg-gray-50 flex justify-between items-center">
            <dt className="text-lg font-bold text-gray-800">Total Sell Price</dt>
            <dd className="text-xl font-bold text-blue-600">${quote.total_sell}</dd>
          </div>
        </dl>
      </div>
    </main>
  );
}