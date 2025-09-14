'use client';

import { useState, useEffect } from 'react';
import { QuoteStatus, ComputeQuoteResponse, Money } from '@/lib/types';
import { extractErrorMessage, extractErrorFromResponse } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"

// Define types for our data
interface Organization {
  id: number;
  name: string;
}

interface Piece {
  weight_kg: string;
  length_cm?: string;
  width_cm?: string;
  height_cm?: string;
}

const commodityTypes = [
    { value: 'GCR', label: 'General Cargo (GCR)' },
    { value: 'DGR', label: 'Dangerous Goods (DGR)' },
    { value: 'PER', label: 'Perishables (PER)' },
    { value: 'LAR', label: 'Live Animals (LAR)' },
];

export default function NewQuotePage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [origin, setOrigin] = useState('BNE');
  const [destination, setDestination] = useState('LAE');
  const [commodityCode, setCommodityCode] = useState('GCR');
  const [isUrgent, setIsUrgent] = useState(false);
  const [pieces, setPieces] = useState<Piece[]>([{ weight_kg: '' }]);
  const [quoteResult, setQuoteResult] = useState<ComputeQuoteResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch organizations when the component mounts
  useEffect(() => {
    async function fetchOrganizations() {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE;
        const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
        if (!apiBase) throw new Error('API configuration error');

        const response = await fetch(`${apiBase}/organizations/`, {
          headers: {
            ...(token ? { 'Authorization': `Token ${token}` } : {}),
          },
        });
        if (!response.ok) {
          const msg = await extractErrorFromResponse(response, 'Failed to fetch organizations');
          setError(msg);
          return;
        }
        const data = await response.json();
        setOrganizations(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      }
    }
    fetchOrganizations();
  }, []);

  const handleAddPiece = () => {
    setPieces([...pieces, { weight_kg: '' }]);
  };

  const handlePieceChange = (index: number, field: keyof Piece, value: string) => {
    const updatedPieces = [...pieces];
    updatedPieces[index][field] = value;
    setPieces(updatedPieces);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setQuoteResult(null);

    const payload = {
      org_id: parseInt(selectedOrg, 10),
      origin_iata: origin,
      dest_iata: destination,
      shipment_type: "IMPORT",
      service_scope: "AIRPORT_AIRPORT",
      commodity_code: commodityCode,
      is_urgent: isUrgent,
      pieces: pieces.map(p => ({
        ...p,
        weight_kg: parseFloat(p.weight_kg) || 0,
        length_cm: parseFloat(p.length_cm || '0') || undefined,
        width_cm: parseFloat(p.width_cm || '0') || undefined,
        height_cm: parseFloat(p.height_cm || '0') || undefined,
      })),
    };

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
      if (!apiBase) throw new Error('API configuration error');

      const response = await fetch(`${apiBase}/quote/compute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Token ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      let data: any = null;
      try { data = await response.json(); } catch {}
      if (!response.ok) {
        const errorMsg = extractErrorMessage(data, 'Failed to compute quote');
        throw new Error(errorMsg);
      }
      setQuoteResult(data as ComputeQuoteResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const renderResult = () => {
    if (isLoading) return <p>Calculating...</p>;
    if (error) return <p className="text-red-500">{error}</p>;
    if (!quoteResult) return <p>Enter shipment details and click "Get Quote".</p>;

    // Status values standardized by backend: see QuoteStatus enum
    if (quoteResult.status === QuoteStatus.PENDING_RATE) {
      return (
        <Alert>
          <AlertTitle>Manual Quote Required</AlertTitle>
          <AlertDescription>
            <p>This shipment cannot be quoted automatically. Our pricing team has been notified and will provide a quote shortly.</p>
            <p className="font-bold mt-2">Reason: {quoteResult.manual_reasons?.[0]}</p>
          </AlertDescription>
        </Alert>
      );
    }

    const sell: Money | undefined = quoteResult.sell_total ?? quoteResult.totals?.sell_total;

    return (
      <div className="space-y-4">
        <h3 className="text-2xl font-bold">
          {sell ? (
            <>Total Sell Price: {sell.amount} {sell.currency}</>
          ) : (
            <>Quote Created: #{quoteResult.quote_id}</>
          )}
        </h3>
        <details>
          <summary>View Full Breakdown</summary>
          <pre className="bg-gray-100 p-2 rounded-md text-sm overflow-auto mt-2">
            {JSON.stringify(quoteResult, null, 2)}
          </pre>
        </details>
      </div>
    );
  }

  return (
    <div className="container mx-auto p-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Card>
          <CardHeader><CardTitle>Create a New Quote</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="organization">Client / Organization</Label>
                <Select onValueChange={setSelectedOrg} value={selectedOrg} required>
                  <SelectTrigger id="organization"><SelectValue placeholder="Select a client" /></SelectTrigger>
                  <SelectContent>
                    {organizations.map((org) => (
                      <SelectItem key={org.id} value={String(org.id)}>{org.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="origin">Origin</Label>
                  <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} maxLength={3} />
                </div>
                <div>
                  <Label htmlFor="destination">Destination</Label>
                  <Input id="destination" value={destination} onChange={(e) => setDestination(e.target.value.toUpperCase())} maxLength={3} />
                </div>
              </div>

              <div>
                <Label htmlFor="commodity">Cargo Type</Label>
                <Select onValueChange={setCommodityCode} value={commodityCode}>
                    <SelectTrigger id="commodity"><SelectValue /></SelectTrigger>
                    <SelectContent>
                        {commodityTypes.map((type) => (
                            <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
              </div>

              <Label>Pieces</Label>
              {pieces.map((piece, index) => (
                <div key={index} className="flex items-center gap-2 p-2 border rounded-md">
                  <Input type="number" placeholder="Weight (kg)" value={piece.weight_kg ?? ''} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} className="w-24" required />
                  <Input type="number" placeholder="L (cm)" value={piece.length_cm ?? ''} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} />
                  <Input type="number" placeholder="W (cm)" value={piece.width_cm ?? ''} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} />
                  <Input type="number" placeholder="H (cm)" value={piece.height_cm ?? ''} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} />
                </div>
              ))}
              <div className="flex justify-between items-center">
                <Button type="button" variant="outline" size="sm" onClick={handleAddPiece}>Add Piece</Button>
                <div className="flex items-center space-x-2">
                    <Checkbox id="isUrgent" checked={isUrgent} onCheckedChange={(checked) => setIsUrgent(checked as boolean)} />
                    <Label htmlFor="isUrgent">Urgent Shipment</Label>
                </div>
              </div>
              
              <Button type="submit" disabled={isLoading || !selectedOrg} className="w-full">
                {isLoading ? 'Calculating...' : 'Get Quote'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Quote Result</CardTitle></CardHeader>
          <CardContent>
            {renderResult()}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
