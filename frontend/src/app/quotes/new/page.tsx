// frontend/src/app/quotes/new/page.tsx

"use client";

import { useState } from 'react';
import { useDebouncedCallback } from 'use-debounce';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Combobox } from '@/components/ui/combobox';
import { createQuoteV2, searchCompanies } from '@/lib/api';
import type { QuoteV2Request, QuoteV2Response } from '@/lib/types';

type ShipmentPiece = {
  pieces: number;
  length: number;
  width: number;
  height: number;
  weight: number;
};

export default function NewQuotePage() {
  const [scenario, setScenario] = useState('IMPORT_D2D_COLLECT');
  const [origin, setOrigin] = useState('BNE');
  const [destination, setDestination] = useState('POM');
  const [pieces, setPieces] = useState<ShipmentPiece[]>([
    { pieces: 1, length: 100, width: 80, height: 50, weight: 120 },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const [quoteResult, setQuoteResult] = useState<QuoteV2Response | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [billTo, setBillTo] = useState('');
  const [shipper, setShipper] = useState('');
  const [consignee, setConsignee] = useState('');

  const [billToOptions, setBillToOptions] = useState<{ value: string; label: string }[]>([]);
  const [shipperOptions, setShipperOptions] = useState<{ value: string; label: string }[]>([]);
  const [consigneeOptions, setConsigneeOptions] = useState<{ value: string; label: string }[]>([]);

  const handleSearch = useDebouncedCallback(
    async (
      query: string,
      setter: React.Dispatch<React.SetStateAction<{ value: string; label: string }[]>>
    ) => {
      if (query.trim().length < 2) {
        setter([]);
        return;
      }

      try {
        const companies = await searchCompanies(query);
        setter(
          companies.map((company) => ({
            value: company.id,
            label: company.name,
          }))
        );
      } catch (searchError) {
        console.error('Company search failed', searchError);
        setter([]);
      }
    },
    300
  );

  const calculateVolume = (piece: ShipmentPiece) =>
    (piece.length * piece.width * piece.height) / 1000000;
  const calculateVolumetricWeight = (piece: ShipmentPiece) => calculateVolume(piece) * 167;
  const totalGrossWeight = pieces.reduce((total, piece) => total + piece.pieces * piece.weight, 0);
  const totalVolumetricWeight = pieces.reduce(
    (total, piece) => total + piece.pieces * calculateVolumetricWeight(piece),
    0
  );
  const chargeableWeight = Math.max(totalGrossWeight, totalVolumetricWeight).toFixed(2);

  const handlePieceChange = (index: number, field: keyof ShipmentPiece, value: string) => {
    const nextPieces = [...pieces];
    nextPieces[index] = { ...nextPieces[index], [field]: Number(value) || 0 };
    setPieces(nextPieces);
  };

  const addPiece = () => {
    setPieces([...pieces, { pieces: 1, length: 0, width: 0, height: 0, weight: 0 }]);
  };

  const removePiece = (index: number) => {
    setPieces(pieces.filter((_, i) => i !== index));
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setQuoteResult(null);

    if (!billTo || !shipper || !consignee) {
      setError('Please select companies for Bill To, Shipper, and Consignee.');
      setIsLoading(false);
      return;
    }

    const quoteRequest: QuoteV2Request = {
      scenario,
      chargeable_kg: chargeableWeight,
      bill_to_id: billTo,
      shipper_id: shipper,
      consignee_id: consignee,
      origin_code: origin,
      destination_code: destination,
      buy_lines: [
        { currency: 'AUD', amount: '1250.00', description: 'Air Freight Charges' },
        { currency: 'AUD', amount: '75.00', description: 'Origin Handling' },
      ],
      agent_dest_lines_aud: [{ amount: '250.00', description: 'Agent Handling and Delivery' }],
    };

    try {
      const result = await createQuoteV2(quoteRequest);
      setQuoteResult(result);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError('An unknown error occurred.');
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-bold">New Quote</h1>
      <form onSubmit={handleSubmit}>
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="space-y-6 lg:col-span-2">
            <Card>
              <CardHeader>
                <CardTitle>Shipment Details</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label htmlFor="origin">Origin</Label>
                    <Input
                      id="origin"
                      value={origin}
                      onChange={(event) => setOrigin(event.target.value.toUpperCase())}
                    />
                  </div>
                  <div>
                    <Label htmlFor="destination">Destination</Label>
                    <Input
                      id="destination"
                      value={destination}
                      onChange={(event) => setDestination(event.target.value.toUpperCase())}
                    />
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
                      <TableHead />
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pieces.map((piece, index) => (
                      <TableRow key={index}>
                        <TableCell>
                          <Input
                            type="number"
                            value={piece.pieces}
                            onChange={(event) =>
                              handlePieceChange(index, 'pieces', event.target.value)
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            value={piece.length}
                            onChange={(event) =>
                              handlePieceChange(index, 'length', event.target.value)
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            value={piece.width}
                            onChange={(event) =>
                              handlePieceChange(index, 'width', event.target.value)
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            value={piece.height}
                            onChange={(event) =>
                              handlePieceChange(index, 'height', event.target.value)
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Input
                            type="number"
                            value={piece.weight}
                            onChange={(event) =>
                              handlePieceChange(index, 'weight', event.target.value)
                            }
                          />
                        </TableCell>
                        <TableCell>
                          <Button
                            type="button"
                            variant="destructive"
                            size="sm"
                            onClick={() => removePiece(index)}
                          >
                            X
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                <Button type="button" variant="outline" onClick={addPiece}>
                  Add Piece
                </Button>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Parties</CardTitle>
                <CardDescription>Select the companies involved in this shipment.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Bill To Account</Label>
                  <Combobox
                    options={billToOptions}
                    value={billTo}
                    onChange={setBillTo}
                    onSearch={(query) => handleSearch(query, setBillToOptions)}
                    placeholder="Select a company..."
                    searchPlaceholder="Search companies..."
                  />
                </div>
                <div>
                  <Label>Shipper</Label>
                  <Combobox
                    options={shipperOptions}
                    value={shipper}
                    onChange={setShipper}
                    onSearch={(query) => handleSearch(query, setShipperOptions)}
                    placeholder="Select a company..."
                    searchPlaceholder="Search companies..."
                  />
                </div>
                <div>
                  <Label>Consignee</Label>
                  <Combobox
                    options={consigneeOptions}
                    value={consignee}
                    onChange={setConsignee}
                    onSearch={(query) => handleSearch(query, setConsigneeOptions)}
                    placeholder="Select a company..."
                    searchPlaceholder="Search companies..."
                  />
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Quote Summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <Label>Quote Type</Label>
                  <Select value={scenario} onValueChange={setScenario}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="IMPORT_D2D_COLLECT">Import D2D Collect</SelectItem>
                      <SelectItem value="EXPORT_D2D_PREPAID">Export D2D Prepaid</SelectItem>
                      <SelectItem value="IMPORT_A2D_AGENT_AUD">Import A2D Agent (AUD)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <span>Gross Weight:</span> <strong>{totalGrossWeight.toFixed(2)} kg</strong>
                  </div>
                  <div className="flex justify-between">
                    <span>Volumetric Weight:</span>{' '}
                    <strong>{totalVolumetricWeight.toFixed(2)} kg</strong>
                  </div>
                  <div className="flex justify-between text-lg font-bold">
                    <span>Chargeable Weight:</span> <strong>{chargeableWeight} kg</strong>
                  </div>
                </div>
                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading ? 'Calculating...' : 'Calculate Quote'}
                </Button>
              </CardContent>
            </Card>

            {error && (
              <Card className="border-red-200 bg-red-50">
                <CardContent className="p-4">
                  <p className="font-semibold text-red-700">Error: {error}</p>
                </CardContent>
              </Card>
            )}

            {quoteResult && (
              <Card>
                <CardHeader>
                  <CardTitle>Calculation Result</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    <div className="flex justify-between">
                      <span>Quote Number:</span> <strong>{quoteResult.quote_number}</strong>
                    </div>
                    <div className="flex justify-between text-xl font-bold">
                      <span>Grand Total:</span>{' '}
                      <strong>{quoteResult.totals?.grand_total_pgk} PGK</strong>
                    </div>
                  </div>
                  <a
                    href={`http://127.0.0.1:8000/api/v2/quotes/${quoteResult.id}/pdf/`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <Button className="mt-4 w-full" variant="outline">
                      Download PDF
                    </Button>
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
