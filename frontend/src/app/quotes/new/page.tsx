"use client";

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Client, ShipmentPiece } from '@/lib/types';

// The initial state for a single piece
const initialPieceState: ShipmentPiece = {
  quantity: 1,
  length_cm: 0,
  width_cm: 0,
  height_cm: 0,
  weight_kg: 0,
};

export default function CreateQuotePage() {
  const router = useRouter();
  const [clients, setClients] = useState<Client[]>([]);

  // --- NEW STATE MANAGEMENT ---
  // Main form state
  const [clientId, setClientId] = useState('');
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');

  // State to hold the array of shipment pieces
  const [pieces, setPieces] = useState<ShipmentPiece[]>([initialPieceState]);

  // --- FETCH CLIENTS (same as before) ---
  useEffect(() => {
    const fetchClients = async () => {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      try {
        const res = await fetch(`${apiBase}/clients/`);
        if (!res.ok) {
          throw new Error(`Failed to fetch clients: ${res.status}`);
        }
        let data;
        try {
          data = await res.json();
        } catch (jsonErr) {
          throw new Error("Failed to parse clients response as JSON.");
        }
        setClients(Array.isArray(data) ? data : []);
      } catch (err) {
        console.error("Error fetching clients:", err);
        setClients([]);
        // Optionally set an error state here to show a UI message
      }
    };
    fetchClients();
  }, []);

  // --- REAL-TIME CALCULATIONS ---
  const totals = useMemo(() => {
    let totalGrossWeight = 0;
    let totalVolume = 0;

    pieces.forEach(p => {
      const quantity = Number(p.quantity) || 0;
      const weight = Number(p.weight_kg) || 0;
      const length = Number(p.length_cm) || 0;
      const width = Number(p.width_cm) || 0;
      const height = Number(p.height_cm) || 0;

      totalGrossWeight += quantity * weight;
      totalVolume += quantity * length * width * height;
    });

    // Assuming a volumetric weight factor (this may vary based on actual shipping rules)
    const volumetricWeightFactor = 5000;
    const totalVolumetricWeight = totalVolume / volumetricWeightFactor;

    // Chargeable weight is the greater of gross weight or volumetric weight
    const chargeableWeight = Math.max(totalGrossWeight, totalVolumetricWeight);

    return {
      totalGrossWeight: totalGrossWeight.toFixed(2),
      totalVolumetricWeight: totalVolumetricWeight.toFixed(2),
      chargeableWeight: chargeableWeight.toFixed(2),
    };
  }, [pieces]); // This recalculates whenever the 'pieces' array changes

  // --- HANDLERS FOR PIECES ---
  const handlePieceChange = (index: number, field: keyof ShipmentPiece, value: string) => {
    const updatedPieces = [...pieces];
    updatedPieces[index] = { ...updatedPieces[index], [field]: value };
    setPieces(updatedPieces);
  };

  const addPiece = () => {
    setPieces([...pieces, { ...initialPieceState }]);
  };

  const removePiece = (index: number) => {
    const updatedPieces = pieces.filter((_, i) => i !== index);
    setPieces(updatedPieces);
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    const quoteData = {
      client: clientId,
      origin: origin,
      destination: destination,
      mode: 'air',
      pieces: pieces.map(p => ({ // Send the cleaned array of pieces
        quantity: Number(p.quantity),
        length_cm: Number(p.length_cm),
        width_cm: Number(p.width_cm),
        height_cm: Number(p.height_cm),
        weight_kg: Number(p.weight_kg),
      })),
    };

    const apiBase = process.env.NEXT_PUBLIC_API_BASE;
    const res = await fetch(`${apiBase}/quotes/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(quoteData),
    });

    if (res.ok) {
      router.push('/quotes'); 
    } else {
      const errorData = await res.json();
      alert(`Failed to create quote: ${JSON.stringify(errorData)}`);
    }
  };

  return (
    <main className="container mx-auto p-8">
      <h1 className="text-4xl font-bold mb-6">Create New Air Freight Quote</h1>

      <form onSubmit={handleSubmit} className="space-y-8">
        {/* --- Main Quote Details --- */}
        <div className="p-6 bg-white shadow rounded-lg">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            <div>
              <label htmlFor="client" className="block text-sm font-medium text-gray-700">Client</label>
              <select id="client" value={clientId} onChange={(e) => setClientId(e.target.value)} required className="mt-1 block w-full p-2 border border-gray-300 rounded-md">
                <option value="">Select a Client</option>
                {clients.map((client) => <option key={client.id} value={client.id}>{client.name}</option>)}
              </select>
            </div>
            <div>
              <label htmlFor="origin" className="block text-sm font-medium text-gray-700">Origin</label>
              <input type="text" id="origin" value={origin} onChange={(e) => setOrigin(e.target.value)} required className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="e.g., BNE" />
            </div>
            <div>
              <label htmlFor="destination" className="block text-sm font-medium text-gray-700">Destination</label>
              <input type="text" id="destination" value={destination} onChange={(e) => setDestination(e.target.value)} required className="mt-1 block w-full p-2 border border-gray-300 rounded-md" placeholder="e.g., POM" />
            </div>
          </div>
        </div>

        {/* --- Shipment Pieces Details --- */}
        <div className="p-6 bg-white shadow rounded-lg">
          <h2 className="text-2xl font-semibold mb-4">Shipment Pieces</h2>
          <div className="space-y-4">
            {pieces.map((piece, index) => (
              <div key={index} className="grid grid-cols-1 md:grid-cols-6 gap-4 items-center">
                <input type="number" placeholder="Qty" value={piece.quantity} onChange={(e) => handlePieceChange(index, 'quantity', e.target.value)} className="w-full p-2 border border-gray-300 rounded-md" />
                <input type="number" placeholder="Length (cm)" value={piece.length_cm} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} className="w-full p-2 border border-gray-300 rounded-md" />
                <input type="number" placeholder="Width (cm)" value={piece.width_cm} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} className="w-full p-2 border border-gray-300 rounded-md" />
                <input type="number" placeholder="Height (cm)" value={piece.height_cm} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} className="w-full p-2 border border-gray-300 rounded-md" />
                <input type="number" placeholder="Weight (kg)" value={piece.weight_kg} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} className="w-full p-2 border border-gray-300 rounded-md" />
                <button type="button" onClick={() => removePiece(index)} className="text-red-500 font-bold text-2xl disabled:opacity-50" disabled={pieces.length <= 1}>×</button>
              </div>
            ))}
          </div>
          <button type="button" onClick={addPiece} className="mt-4 bg-gray-200 text-gray-800 font-bold py-2 px-4 rounded-md hover:bg-gray-300">+ Add Piece</button>
        </div>

        {/* --- Totals and Submission --- */}
        <div className="p-6 bg-gray-50 shadow rounded-lg grid grid-cols-1 md:grid-cols-4 gap-6 items-center">
            <div className="text-center">
                <p className="text-sm text-gray-500">Total Gross Weight</p>
                <p className="text-xl font-bold">{totals.totalGrossWeight} kg</p>
            </div>
            <div className="text-center">
                <p className="text-sm text-gray-500">Total Volumetric Weight</p>
                <p className="text-xl font-bold">{totals.totalVolumetricWeight} kg</p>
            </div>
            <div className="text-center p-4 bg-blue-100 rounded-lg">
                <p className="text-sm text-blue-800">Chargeable Weight</p>
                <p className="text-2xl font-extrabold text-blue-800">{totals.chargeableWeight} kg</p>
            </div>
            <button type="submit" className="w-full bg-blue-600 text-white font-bold py-3 px-4 rounded-md hover:bg-blue-700 text-lg">
              Calculate & Create Quote
            </button>
        </div>
      </form>
    </main>
  );
}