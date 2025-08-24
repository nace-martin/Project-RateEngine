import { Quote } from '@/lib/types';

// This function fetches ONE quote using its ID
async function getQuote(id: string): Promise<Quote> {
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  const res = await fetch(`${apiBase}/quotes/${id}/`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error('Failed to fetch quote');
  }
  return res.json();
}

// The 'params' prop is automatically passed by Next.js for dynamic routes like [id]
export default async function QuoteDetailPage({ params }: { params: { id: string } }) {
  // We get the specific id from the params and pass it to our fetch function
  const quote = await getQuote(params.id);

  return (
    <main className="container mx-auto p-8">
      <h1 className="text-4xl font-bold">Quote #{quote.id}</h1>
      <p className="mt-2 text-lg text-gray-600">
        Details for the selected quote.
      </p>
      
      <div className="mt-8 bg-white shadow rounded-lg p-6 space-y-4">
        <div className="flex justify-between">
          <span className="font-medium text-gray-500">Origin:</span>
          <span className="font-bold text-gray-900">{quote.origin}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-medium text-gray-500">Destination:</span>
          <span className="font-bold text-gray-900">{quote.destination}</span>
        </div>
        <div className="flex justify-between">
          <span className="font-medium text-gray-500">Weight:</span>
          <span className="font-bold text-gray-900">{quote.actual_weight_kg} kg</span>
        </div>
        <div className="flex justify-between border-t pt-4 mt-4">
          <span className="text-xl font-medium text-gray-500">Total Sell Price:</span>
          <span className="text-xl font-bold text-blue-600">${quote.total_sell}</span>
        </div>
      </div>
    </main>
  );
}