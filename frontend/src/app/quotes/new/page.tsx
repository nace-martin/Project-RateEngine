// frontend/src/app/quotes/new/page.tsx

"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { createQuoteV2 } from '@/lib/api';

// Define a type for a single shipment piece for better code quality
type ShipmentPiece = {
  pieces: number;
  length: number;
  width: number;
  height: number;
  weight: number;
};

export default function NewQuotePage() {
  // State for the form inputs
  const [scenario, setScenario] = useState('IMPORT_D2D_COLLECT');
  const [billToId, setBillToId] = useState('c0a8e1e4-6d2c-4b3f-8a9a-0b2c1d3e4f5a'); // Placeholder
  const [shipperId, setShipperId] = useState('d1b9f2e7-7e3d-4c4a-9b8b-1c3d2e5f6a7b'); // Placeholder
  const [consigneeId, setConsigneeId] = useState('c0a8e1e4-6d2c-4b3f-8a9a-0b2c1d3e4f5a'); // Placeholder
  const [origin, setOrigin] = useState('BNE');
  const [destination, setDestination] = useState('POM');

  const [pieces, setPieces] = useState<ShipmentPiece[]>([
    { pieces: 1, length: 100, width: 80, height: 50, weight: 120 },
  ]);

  // State for API interaction
  const [isLoading, setIsLoading] = useState(false);
  const [quoteResult, setQuoteResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  // --- Calculation Logic ---
  const calculateVolume = (piece: ShipmentPiece) => (piece.length * piece.width * piece.height) / 1000000; // in CBM
  const calculateVolumetricWeight = (piece: ShipmentPiece) => calculateVolume(piece) * 167; // IATA standard
  
  const totalGrossWeight = pieces.reduce((total, p) => total + (p.pieces * p.weight), 0);
  const totalVolumetricWeight = pieces.reduce((total, p) => total + (p.pieces * calculateVolumetricWeight(p)), 0);
  const chargeableWeight = Math.max(totalGrossWeight, totalVolumetricWeight).toFixed(2);

  // --- Handlers for dynamic form elements ---
  const handlePieceChange = (index: number, field: keyof ShipmentPiece, value: string) => {
    const newPieces = [...pieces];
    newPieces[index] = { ...newPieces[index], [field]: Number(value) || 0 };
    setPieces(newPieces);
  };

  const addPiece = () => {
    setPieces([...pieces, { pieces: 1, length: 0, width: 0, height: 0, weight: 0 }]);
  };

  const removePiece = (index: number) => {
    setPieces(pieces.filter((_, i) => i !== index));
  };


  // --- API Submission ---
  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setQuoteResult(null);

    const quoteRequest = {
      scenario,
      chargeable_kg: chargeableWeight,
      bill_to_id: billToId,
      shipper_id: shipperId,
      consignee_id: consigneeId,
      origin_code: origin,
      destination_code: destination,
      // Example buy lines. This could also be a dynamic form section.
      buy_lines: [
        { currency: 'AUD', amount: '1250.00', description: 'Air Freight Charges' },
        { currency: 'AUD', amount: '75.00', description: 'Origin Handling' },
      ],
      // Example agent lines for export scenarios
      agent_dest_lines_aud: [
        { "amount": "250.00", "description": "Agent Handling and Delivery" }
      ]
    };

    try {
      const result = await createQuoteV2(quoteRequest);
      setQuoteResult(result);
    } catch (err: any) {
      setError(err.message || 'An unknown error occurred.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-bold">New Quote</h1>
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2 space-y-6">
            
            {/* Shipment Details Card */}
            <Card>
              <CardHeader><CardTitle>Shipment Details</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="origin">Origin</Label>
                    <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} />
                  </div>
                  <div>
                    <Label htmlFor="destination">Destination</Label>
                    <Input id="destination" value={destination} onChange={(e) => setDestination(e.target.value.toUpperCase())} />
                  </div>
                </div>

                <Label>Dimensions & Weight</Label>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Pcs</TableHead>
                      <TableHead>Length (cm)</TableHead>
                      <TableHead>Width (cm)</TableHead>
                      <TableHead>Height (cm)</TableHead>
                      <TableHead>Weight (kg)</TableHead>
                      <TableHead></TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pieces.map((piece, index) => (
                      <TableRow key={index}>
                        <TableCell><Input type="number" value={piece.pieces} onChange={(e) => handlePieceChange(index, 'pieces', e.target.value)} /></TableCell>
                        <TableCell><Input type="number" value={piece.length} onChange={(e) => handlePieceChange(index, 'length', e.target.value)} /></TableCell>
                        <TableCell><Input type="number" value={piece.width} onChange={(e) => handlePieceChange(index, 'width', e.target.value)} /></TableCell>
                        <TableCell><Input type="number" value={piece.height} onChange={(e) => handlePieceChange(index, 'height', e.target.value)} /></TableCell>
                        <TableCell><Input type="number" value={piece.weight} onChange={(e) => handlePieceChange(index, 'weight', e.target.value)} /></TableCell>
                        <TableCell><Button type="button" variant="destructive" size="sm" onClick={() => removePiece(index)}>X</Button></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Button type="button" variant="outline" onClick={addPiece}>Add Piece</Button>
              </CardContent>
            </Card>

            {/* Parties Card */}
            <Card>
              <CardHeader><CardTitle>Parties</CardTitle><CardDescription>Select the companies involved in this shipment.</CardDescription></CardHeader>
              <CardContent className="space-y-4">
                  {/* NOTE: These should be replaced with searchable dropdown components */}
                  <div>
                      <Label htmlFor="billTo">Bill To Account (Enter ID)</Label>
                      <Input id="billTo" value={billToId} onChange={(e) => setBillToId(e.target.value)} />
                  </div>
                   <div>
                      <Label htmlFor="shipper">Shipper (Enter ID)</Label>
                      <Input id="shipper" value={shipperId} onChange={(e) => setShipperId(e.target.value)} />
                  </div>
                   <div>
                      <Label htmlFor="consignee">Consignee (Enter ID)</Label>
                      <Input id="consignee" value={consigneeId} onChange={(e) => setConsigneeId(e.target.value)} />
                  </div>
              </CardContent>
            </Card>
          </div>

          {/* Summary and Actions Card */}
          <div className="space-y-6">
            <Card>
              <CardHeader><CardTitle>Quote Summary</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                 <div>
                    <Label>Quote Type</Label>
                    <Select value={scenario} onValueChange={setScenario}>
                      <SelectTrigger><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="IMPORT_D2D_COLLECT">Import D2D Collect</SelectItem>
                        <SelectItem value="EXPORT_D2D_PREPAID">Export D2D Prepaid</SelectItem>
                        <SelectItem value="IMPORT_A2D_AGENT_AUD">Import A2D Agent (AUD)</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                      <div className="flex justify-between"><span>Gross Weight:</span> <strong>{totalGrossWeight.toFixed(2)} kg</strong></div>
                      <div className="flex justify-between"><span>Volumetric Weight:</span> <strong>{totalVolumetricWeight.toFixed(2)} kg</strong></div>
                      <div className="flex justify-between text-lg font-bold"><span>Chargeable Weight:</span> <strong>{chargeableWeight} kg</strong></div>
                  </div>
                  <Button type="submit" className="w-full" disabled={isLoading}>
                    {isLoading ? 'Calculating...' : 'Calculate Quote'}
                  </Button>
              </CardContent>
            </Card>
            
            {error && (
                <Card className="bg-red-50 border-red-200"><CardContent className="p-4"><p className="text-red-700 font-semibold">Error: {error}</p></CardContent></Card>
            )}

            {quoteResult && (
              <Card>
                <CardHeader><CardTitle>Calculation Result</CardTitle></CardHeader>
                <CardContent>
                    <div className="space-y-2">
                        <div className="flex justify-between"><span>Quote Number:</span> <strong>{quoteResult.quote_number}</strong></div>
                        <div className="flex justify-between text-xl font-bold"><span>Grand Total:</span> <strong>{quoteResult.totals?.grand_total_pgk} PGK</strong></div>
                    </div>
                    <a href={`http://127.0.0.1:8000/api/v2/quotes/${quoteResult.id}/pdf/`} target="_blank" rel="noopener noreferrer">
                        <Button className="w-full mt-4" variant="outline">Download PDF</Button>
                    </a>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </form>
    </div>
  );
}
