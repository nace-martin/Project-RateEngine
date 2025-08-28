"use client";

import { useState, useEffect, useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { Client, ShipmentPiece, DecimalString } from '@/lib/types';
import { useAuth } from '@/context/auth-context';
import ProtectedRoute from '@/components/protected-route';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Button } from "@/components/ui/button";

// The initial state for a single piece
const initialPieceState: ShipmentPiece = {
  quantity: 1,
  length_cm: 0,
  width_cm: 0,
  height_cm: 0,
  weight_kg: "0" as DecimalString,
};

export default function CreateQuotePage() {
  const router = useRouter();
  const { user } = useAuth();
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
      if (!user) return;
      
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      const token = localStorage.getItem('authToken');
      
      try {
        const res = await fetch(`${apiBase}/clients/`, {
          headers: {
            'Authorization': `Token ${token}`,
            'Content-Type': 'application/json',
          },
        });
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
    
    if (user) {
      fetchClients();
    }
  }, [user]);

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

    // Log the calculations for debugging
    console.log('Total volume (cm³):', totalVolume);
    
    // Assuming a volumetric weight factor (this may vary based on actual shipping rules)
    const volumetricWeightFactor = 6000; // Changed from 5000 to 6000 for air freight
    const totalVolumetricWeight = totalVolume / volumetricWeightFactor;

    // Log the volumetric weight calculation
    console.log('Volumetric weight factor:', volumetricWeightFactor);
    console.log('Total volumetric weight (kg):', totalVolumetricWeight);
    console.log('Total gross weight (kg):', totalGrossWeight);
    
    // Round up gross weight and volumetric weight as per air freight rules
    const roundedGrossWeight = Math.ceil(totalGrossWeight);
    const roundedVolumetricWeight = Math.ceil(totalVolumetricWeight);
    
    // Chargeable weight is the greater of gross weight or volumetric weight (both rounded up)
    const chargeableWeight = Math.max(roundedGrossWeight, roundedVolumetricWeight);
    
    // Log the final chargeable weight
    console.log('Chargeable weight (kg):', chargeableWeight);

    return {
      totalGrossWeight: roundedGrossWeight.toFixed(0), // Show as whole number since we're rounding up
      totalVolumetricWeight: roundedVolumetricWeight.toFixed(0), // Show as whole number since we're rounding up
      chargeableWeight: chargeableWeight.toFixed(0), // Show as whole number since we're rounding up
    };
  }, [pieces]); // This recalculates whenever the 'pieces' array changes

  // --- HANDLERS FOR PIECES ---
  const handlePieceChange = (index: number, field: keyof ShipmentPiece, value: string) => {
    const updatedPieces = [...pieces];
    if (field === 'weight_kg') {
      updatedPieces[index] = { ...updatedPieces[index], [field]: value as DecimalString };
    } else {
      updatedPieces[index] = { ...updatedPieces[index], [field]: value };
    }
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
    const token = localStorage.getItem('authToken');
    
    const res = await fetch(`${apiBase}/quotes/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token ${token}`,
      },
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
    <ProtectedRoute>
      <main className="container mx-auto p-8 space-y-6">
        <h1 className="text-4xl font-bold tracking-tight">Create New Air Freight Quote</h1>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* --- Main Quote Details --- */}
          <Card>
            <CardHeader>
              <CardTitle>Main Details</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <div className="space-y-2">
                  <Label htmlFor="client">Client</Label>
                  <Select id="client" value={clientId} onChange={(e) => setClientId(e.target.value)} required>
                    <option value="">Select a Client</option>
                    {clients.map((client) => (
                      <option key={client.id} value={client.id}>{client.name}</option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="origin">Origin</Label>
                  <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value)} required placeholder="e.g., BNE" />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="destination">Destination</Label>
                  <Input id="destination" value={destination} onChange={(e) => setDestination(e.target.value)} required placeholder="e.g., POM" />
                </div>
              </div>
            </CardContent>
          </Card>

          {/* --- Shipment Pieces Details --- */}
          <Card>
            <CardHeader>
              <CardTitle>Shipment Pieces</CardTitle>
            </CardHeader>
            <CardContent>
            <div className="space-y-4">
              {pieces.map((piece, index) => (
                <div key={index} className="grid grid-cols-1 md:grid-cols-6 gap-4 items-center">
                  <Input type="number" placeholder="Qty" value={piece.quantity} onChange={(e) => handlePieceChange(index, 'quantity', e.target.value)} />
                  <Input type="number" placeholder="Length (cm)" value={piece.length_cm} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} />
                  <Input type="number" placeholder="Width (cm)" value={piece.width_cm} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} />
                  <Input type="number" placeholder="Height (cm)" value={piece.height_cm} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} />
                  <Input type="number" placeholder="Weight (kg)" value={piece.weight_kg} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} />
                  <button type="button" onClick={() => removePiece(index)} className="text-red-500 font-bold text-2xl disabled:opacity-50" disabled={pieces.length <= 1}>×</button>
                </div>
              ))}
            </div>
            <div className="mt-4">
              <Button type="button" onClick={addPiece} variant="secondary">+ Add Piece</Button>
            </div>
            </CardContent>
          </Card>

          {/* --- Totals and Submission --- */}
          <Card>
            <CardContent className="grid grid-cols-1 md:grid-cols-4 gap-6 items-center p-6">
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Total Gross Weight</p>
                <p className="text-xl font-bold">{totals.totalGrossWeight} kg</p>
              </div>
              <div className="text-center">
                <p className="text-sm text-muted-foreground">Total Volumetric Weight</p>
                <p className="text-xl font-bold">{totals.totalVolumetricWeight} kg</p>
              </div>
              <div className="text-center p-4 rounded-lg bg-accent">
                <p className="text-sm">Chargeable Weight</p>
                <p className="text-2xl font-extrabold">{totals.chargeableWeight} kg</p>
              </div>
              <Button type="submit" className="w-full" size="lg">
                Calculate & Create Quote
              </Button>
            </CardContent>
          </Card>
        </form>
      </main>
    </ProtectedRoute>
  );
}
