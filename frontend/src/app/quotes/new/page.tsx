"use client"; // This marks the component as a Client Component

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Client } from '@/lib/types'; // Import the Client type

export default function CreateQuotePage() {
  const router = useRouter(); // Initialize the router for navigation
  const [clients, setClients] = useState<Client[]>([]); // State to hold the list of clients
  
  // State for all the form fields
  const [clientId, setClientId] = useState('');
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [actualWeight, setActualWeight] = useState('');
  
  // This effect runs once when the component loads to fetch clients
  useEffect(() => {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE;
    if (!apiBase) {
      console.error('NEXT_PUBLIC_API_BASE is not set');
      return;
    }
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${apiBase}/clients/`, {
          signal: controller.signal,
          credentials: 'include',
        });
        if (!res.ok) {
          console.error('Failed to fetch clients', res.status);
          return;
        }
        const data = await res.json();
        if (Array.isArray(data)) {
          setClients(data);
        } else {
          console.error('Unexpected clients payload', data);
        }
      } catch (err) {
        if ((err as any).name !== 'AbortError') {
          console.error('Error fetching clients', err);
        }
      }
    })();
    return () => controller.abort();
  }, []); // The empty array [] means this effect runs only once
  // This function is called when the form is submitted
  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault(); // Prevent the default form submission behavior

    // The new, simpler data object. We only send what the user enters.
    const quoteData = {
      client: clientId,
      origin: origin,
      destination: destination,
      mode: 'air',
      actual_weight_kg: actualWeight ? Number(actualWeight) : 0,
      // You can add volume and margin fields to your form later
      // volume_cbm: volume ? Number(volume) : undefined,
      // margin_pct: margin ? Number(margin) : undefined,
    };

    const apiBase = process.env.NEXT_PUBLIC_API_BASE;
    try {
      const res = await fetch(`${apiBase}/quotes/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(quoteData),
      });

      if (res.ok) {
        router.push('/quotes');
      } else {
        const errorData = await res.json().catch(() => null);
        let errorMsg = 'Failed to create quote.';
        if (errorData && errorData.error) {
          errorMsg += `\n${errorData.error}`;
        }
        alert(errorMsg);
      }
    } catch (err) {
      alert('Network error: Unable to submit quote.');
      console.error('Submit error:', err);
    }
  };

  return (
    <main className="container mx-auto p-8">
      <h1 className="text-4xl font-bold mb-6">Create New Quote</h1>
      
      <form onSubmit={handleSubmit} className="space-y-6 max-w-lg">
        <div>
          <label htmlFor="client" className="block text-sm font-medium text-gray-700">
            Client
          </label>
          <select
            id="client"
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            required
            className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
          >
            <option value="">Select a Client</option>
            {clients.map((client) => (
              <option key={client.id} value={client.id}>
                {client.name}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label htmlFor="origin" className="block text-sm font-medium text-gray-700">
            Origin
          </label>
          <input
            type="text"
            id="origin"
            value={origin}
            onChange={(e) => setOrigin(e.target.value)}
            required
            className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            placeholder="e.g., BNE"
          />
        </div>

        <div>
          <label htmlFor="destination" className="block text-sm font-medium text-gray-700">
            Destination
          </label>
          <input
            type="text"
            id="destination"
            value={destination}
            onChange={(e) => setDestination(e.target.value)}
            required
            className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            placeholder="e.g., POM"
          />
        </div>

        <div>
          <label htmlFor="actualWeight" className="block text-sm font-medium text-gray-700">
            Actual Weight (kg)
          </label>
          <input
            type="number"
            id="actualWeight"
            value={actualWeight}
            onChange={(e) => setActualWeight(e.target.value)}
            required
            className="mt-1 block w-full p-2 border border-gray-300 rounded-md shadow-sm"
            placeholder="e.g., 150"
          />
        </div>

        <div>
          <button
            type="submit"
            className="w-full bg-blue-600 text-white font-bold py-2 px-4 rounded-md hover:bg-blue-700"
          >
            Create Quote
          </button>
        </div>
      </form>
    </main>
  );
}