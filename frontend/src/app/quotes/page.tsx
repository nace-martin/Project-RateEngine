import Link from 'next/link';
import { Quote } from '@/lib/types';

// This is a Server Component, so we can fetch data directly
async function getQuotes(): Promise<{ quotes: Quote[]; error?: string }> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  if (!apiBase) {
    console.error('NEXT_PUBLIC_API_BASE environment variable is not set');
    return { quotes: [], error: 'API configuration error' }; // Return empty array with error info
  }
  
  try {
    const res = await fetch(`${apiBase}/quotes/`, {
      cache: 'no-store',
      // Add timeout to prevent hanging
      signal: AbortSignal.timeout(10000) // 10 second timeout
    });

    if (!res.ok) {
      console.error(`Failed to fetch quotes: ${res.status} ${res.statusText}`);
      console.error(`API Base URL: ${apiBase}`);
      return { quotes: [], error: `Failed to fetch quotes (${res.status})` }; // Return empty array with error info
    }

    const data = await res.json();
    if (!Array.isArray(data)) {
      console.error('Invalid response format: expected an array');
      return { quotes: [], error: 'Invalid response format from server' }; // Return empty array with error info
    }
    const quotes = data as Quote[];
    // We'll sort so the newest quotes appear first
    quotes.sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
    return { quotes, error: undefined }; // Success case
  } catch (error) {
    console.error('Error fetching quotes:', error);
    // Check if it's a timeout error
    if (error instanceof Error && error.name === 'TimeoutError') {
      console.error('Request timed out while fetching quotes');
      return { quotes: [], error: 'Request timed out' };
    }
    // Return empty array with error info instead of throwing
    return { quotes: [], error: 'Failed to connect to server' };
  }
}

export default async function QuotesListPage() {
  const { quotes, error } = await getQuotes();

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
          {error ? (
            <li className="p-6 text-center">
              <p className="text-red-500 font-medium">Unable to load quotes: {error}</p>
              <p className="text-gray-500 mt-2">Please check your connection and ensure the API server is running.</p>
            </li>
          ) : quotes.length > 0 ? (
            quotes.map((quote) => (
              <li key={quote.id} className="p-4 sm:p-6 flex justify-between items-center hover:bg-gray-50 transition-colors">
                <div>
                  {/* This line will now work correctly after updating types.ts */}
                  <p className="font-semibold text-lg text-gray-800">{quote.client.name}</p>
                  <p className="text-sm text-gray-500 mt-1">
                    {quote.origin} → {quote.destination} - <span className="font-medium text-gray-700">{
                      Intl.NumberFormat('en-US', {
                        style: 'currency',
                        currency: 'PGK',
                        maximumFractionDigits: 2,
                      }).format(Number(quote.total_sell ?? 0))
                    }</span>
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