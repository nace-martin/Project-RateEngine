import Link from 'next/link';
import { Quote } from '@/lib/types';

async function getQuotes(): Promise<Quote[]> {
async function getQuotes(): Promise<Quote[]> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  if (!apiBase) {
    throw new Error('Environment variable NEXT_PUBLIC_API_BASE is not set');
  }
  const url = new URL('quotes/', apiBase);
  const res = await fetch(url.toString(), { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`Failed to fetch quotes: ${res.status} ${res.statusText}`);
  }
  const data = (await res.json()) as Quote[];
  return data;
}
export default async function QuotesListPage() {
  const quotes = await getQuotes();

  return (
    <main className="container mx-auto p-8">
      <div className="flex justify-between items-center mb-8">
        <h1 className="text-4xl font-bold">All Quotes</h1>
        <Link href="/quotes/new" className="bg-blue-600 text-white font-bold py-2 px-4 rounded-md hover:bg-blue-700">
          Create New Quote
        </Link>
      </div>

      <div className="bg-white shadow rounded-lg">
        <ul className="divide-y divide-gray-200">
          {quotes.map((quote) => (
            <li key={quote.id}>
              <Link href={`/quotes/${quote.id}`} className="block hover:bg-gray-50 p-4">
                <div className="flex items-center justify-between">
                  <p className="text-lg font-medium text-blue-600">
                    Quote #{quote.id}
                  </p>
                  <p className="text-lg font-bold">${quote.total_sell}</p>
                </div>
                <p className="text-gray-600 mt-1">
                  {quote.origin} to {quote.destination} - {quote.actual_weight_kg} kg
                </p>
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}