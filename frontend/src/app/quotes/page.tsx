import Link from 'next/link';
import { Quote } from '@/lib/types';

// This is a Server Component, so we can fetch data directly
async function getQuotes(): Promise<Quote[]> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  if (!apiBase) {
    throw new Error('Environment variable NEXT_PUBLIC_API_BASE is not set');
  }
  
  const res = await fetch(`${apiBase}/quotes/`, { cache: 'no-store' });

  if (!res.ok) {
    // This will be caught by the nearest error page
    throw new Error('Failed to fetch quotes');
  }

  const data = await res.json();
  // We'll sort so the newest quotes appear first
  data.sort((a: Quote, b: Quote) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
  return data;
}

export default async function QuotesListPage() {
  const quotes = await getQuotes();

  return (
    <main className="container mx-auto p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-4xl font-bold">All Quotes</h1>
        <Link href="/quotes/new" className="bg-blue-600 text-white font-bold py-2 px-4 rounded-md hover:bg-blue-700 transition-colors">
          Create New Quote
        </Link>
      </div>

      <div className="bg-white shadow-md rounded-lg">
        <ul className="divide-y divide-gray-200">
          {quotes.length > 0 ? (
            quotes.map((quote) => (
              <li key={quote.id} className="p-4 sm:p-6 flex justify-between items-center hover:bg-gray-50 transition-colors">
                <div>
                  {/* This line will now work correctly after updating types.ts */}
                  <p className="font-semibold text-lg text-gray-800">{quote.client.name}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    {quote.origin} → {quote.destination} - <span className="font-medium text-gray-700">${quote.total_sell}</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-2">
                    {new Date(quote.created_at).toLocaleString()}
                  </p>
                </div>
                <Link href={`/quotes/${quote.id}`} className="text-blue-600 hover:underline font-semibold">
                  View Details
                </Link>
              </li>
            ))
          ) : (
            <li className="p-6 text-center text-gray-500">No quotes found.</li>
          )}
        </ul>
      </div>
    </main>
  );
}