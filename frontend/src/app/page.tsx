// Import the Client type we just defined

import { Client } from '@/lib/types';

// This async function will fetch the list of clients from our Django API
async function getClients(): Promise<Client[]> {
  // process.env.NEXT_PUBLIC_API_BASE comes from your .env.local file
  const apiBase = process.env.NEXT_PUBLIC_API_BASE;
  if (!apiBase) {
    throw new Error('API base URL is not configured.');
  }

  // Fetch the data. We add 'cache: no-store' to ensure we always get the latest data.
  const res = await fetch(`${apiBase}/clients/`, { cache: 'no-store' });

  // If the request fails, throw an error
  if (!res.ok) {
    throw new Error('Failed to fetch clients');
  }

  // Parse the JSON response and return it
  return res.json();
}


// This is our main page component. Notice it's an 'async' function.
// This allows us to use 'await' to fetch data directly inside it.
export default async function HomePage() {
  const clients = await getClients();

  return (
    <main className="container mx-auto p-8">
      <h1 className="text-4xl font-bold">Clients</h1>
      <p className="mt-2 text-lg text-gray-600">A list of clients from the database.</p>

      <div className="mt-8">
        <ul className="divide-y divide-gray-200">
          {/* We map over the clients array to display each one */}
          {clients.map((client) => (
            <li key={client.id} className="py-4">
              <p className="text-xl font-semibold text-gray-800">{client.name}</p>
              <p className="text-sm text-gray-500">{client.email}</p>
            </li>
          ))}
        </ul>
      </div>
    </main>
  );
}