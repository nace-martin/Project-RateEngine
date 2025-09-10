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
import { pngAirports } from "@/data/pngAirports";

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
  const [serviceScope, setServiceScope] = useState<'DOOR_DOOR' | 'DOOR_AIRPORT' | 'AIRPORT_DOOR' | 'AIRPORT_AIRPORT'>('AIRPORT_AIRPORT');

  // State to hold the array of shipment pieces
  const [pieces, setPieces] = useState<ShipmentPiece[]>([initialPieceState]);
  const [calc, setCalc] = useState<any>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [calcError, setCalcError] = useState<string | null>(null);

  // Determine PNG membership and shipment type automatically
  const pngCodes = useMemo(() => new Set(pngAirports.map(a => a.code.toUpperCase())), []);
  const computedShipmentType = useMemo<"IMPORT" | "EXPORT" | "DOMESTIC" | null>(() => {
    if (!origin || !destination) return null;
    const o = origin.toUpperCase();
    const d = destination.toUpperCase();
    const oIsPng = pngCodes.has(o);
    const dIsPng = pngCodes.has(d);
    if (oIsPng && dIsPng) return 'DOMESTIC';
    if (oIsPng && !dIsPng) return 'EXPORT';
    if (!oIsPng && dIsPng) return 'IMPORT';
    return null; // both international or unknown
  }, [origin, destination, pngCodes]);

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

    const quoteData: any = {
      client_id: Number(clientId),
      origin: origin,
      destination: destination,
      shipment_type: (computedShipmentType ?? 'DOMESTIC'),
      service_scope: serviceScope,
      // Retain mode for backward compatibility if backend expects it
      mode: 'air',
      pieces: pieces.map(p => ({
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

  const handleCalculate = async () => {
    setCalcError(null);
    setIsCalculating(true);
    const apiBase = process.env.NEXT_PUBLIC_API_BASE || '';
    const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;

    if (!origin || !destination) {
      setCalcError('Please select both origin and destination.');
      setIsCalculating(false);
      return;
    }
    if (!computedShipmentType) {
      setCalcError('Unable to determine shipment type from selected airports.');
      setIsCalculating(false);
      return;
    }

    const payload = {
      origin_iata: origin,
      dest_iata: destination,
      shipment_type: computedShipmentType,
      service_scope: serviceScope,
      audience: 'PGK_LOCAL',
      sell_currency: 'PGK',
      pieces: pieces.map(p => ({
        weight_kg: String(p.weight_kg ?? '0'),
        length_cm: String(p.length_cm ?? 0),
        width_cm: String(p.width_cm ?? 0),
        height_cm: String(p.height_cm ?? 0),
      })),
    };

    try {
      const base = apiBase.replace(/\/$/, '');
      const res = await fetch(`${base}/quote/compute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Token ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let msg = `Failed to calculate: ${res.status}`;
        try {
          const err = await res.json();
          msg += ` ${JSON.stringify(err)}`;
        } catch {}
        setCalcError(msg);
        return;
      }
      const data = await res.json();
      setCalc(data);
    } catch (e) {
      console.error('Calculate error', e);
      setCalcError('Unable to calculate quote. Check connection and try again.');
    } finally {
      setIsCalculating(false);
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
              <div className="grid grid-cols-1 md:grid-cols-5 gap-6">
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
                  <Select id="origin" value={origin} onChange={(e) => setOrigin(e.target.value)} required>
                    <option value="">Select Airport</option>
                    {pngAirports.map((a) => (
                      <option key={a.code} value={a.code}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="destination">Destination</Label>
                  <Select id="destination" value={destination} onChange={(e) => setDestination(e.target.value)} required>
                    <option value="">Select Airport</option>
                    {pngAirports.map((a) => (
                      <option key={a.code} value={a.code}>
                        {a.code} — {a.name}
                      </option>
                    ))}
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label>Shipment Type</Label>
                  <div className="flex h-9 w-full items-center rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm">
                    {computedShipmentType ?? '--'}
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="serviceScope">Service Scope</Label>
                  <Select id="serviceScope" value={serviceScope} onChange={(e) => setServiceScope(e.target.value as any)} required>
                    <option value="AIRPORT_AIRPORT">Airport to Airport</option>
                    <option value="DOOR_DOOR">Door to Door</option>
                    <option value="DOOR_AIRPORT">Door to Airport</option>
                    <option value="AIRPORT_DOOR">Airport to Door</option>
                  </Select>
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
            <CardContent className="grid grid-cols-1 md:grid-cols-5 gap-6 items-center p-6">
              {calcError && (
                <div className="md:col-span-5 w-full text-sm text-red-700 bg-red-50 border border-red-200 rounded p-2">
                  {calcError}
                </div>
              )}
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
              <div className="space-y-2 text-center">
                <p className="text-sm text-muted-foreground">Estimated Sell</p>
                <p className="text-xl font-bold">
                  {calc?.totals?.sell_total?.amount ? `${calc.totals.sell_total.amount} ${calc.totals.sell_total.currency}` : '--'}
                </p>
              </div>
              <Button type="button" onClick={handleCalculate} className="w-full" variant="secondary" size="lg" disabled={isCalculating}>
                {isCalculating ? 'Calculating…' : 'Calculate'}
              </Button>
              <Button type="submit" className="w-full" size="lg" disabled={isCalculating}>
                Calculate & Create Quote
              </Button>
            </CardContent>
          </Card>

          {calc && (
            <Card>
              <CardHeader>
                <CardTitle>Quote Breakdown</CardTitle>
              </CardHeader>
              <CardContent className="space-y-6">
                <div>
                  <h3 className="text-lg font-semibold mb-2">Sell Breakdown</h3>
                  <div className="grid grid-cols-12 gap-2 text-sm font-medium text-muted-foreground px-2">
                    <div className="col-span-2">Code</div>
                    <div className="col-span-6">Description</div>
                    <div className="col-span-1 text-right">Qty</div>
                    <div className="col-span-1">Unit</div>
                    <div className="col-span-1 text-right">Unit Price</div>
                    <div className="col-span-1 text-right">Amount</div>
                  </div>
                  <div className="divide-y">
                    {calc.sell_lines?.map((l: any, idx: number) => (
                      <div key={`sell-${idx}`} className="grid grid-cols-12 gap-2 py-2 px-2 text-sm">
                        <div className="col-span-2 truncate" title={l.code}>{l.code}</div>
                        <div className="col-span-6 truncate" title={l.desc}>{l.desc}</div>
                        <div className="col-span-1 text-right">{l.qty}</div>
                        <div className="col-span-1">{l.unit}</div>
                        <div className="col-span-1 text-right">{l.unit_price?.amount} {l.unit_price?.currency}</div>
                        <div className="col-span-1 text-right font-medium">{l.amount?.amount} {l.amount?.currency}</div>
                      </div>
                    ))}
                    {(!calc.sell_lines || calc.sell_lines.length === 0) && (
                      <div className="text-sm text-muted-foreground px-2 py-3">No sell lines.</div>
                    )}
                  </div>
                  <div className="flex justify-end mt-2 text-sm">
                    <div className="font-semibold">Total Sell:&nbsp;</div>
                    <div>{calc.totals?.sell_total?.amount} {calc.totals?.sell_total?.currency}</div>
                  </div>
                </div>

                

                <div className="flex justify-end gap-6 text-sm">
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">Margin:</span>
                    <span className="font-semibold">{calc.totals?.margin?.amount} {calc.totals?.margin?.currency}</span>
                  </div>
                </div>
              </CardContent>
            </Card>
          )}
        </form>
      </main>
    </ProtectedRoute>
  );
}
