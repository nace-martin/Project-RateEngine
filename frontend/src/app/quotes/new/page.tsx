'use client';

import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { calculateQuoteV2, getCustomers } from '@/lib/api';
import { Customer, BuyOffer, Piece, QuoteContext } from '@/lib/types';
import { useAuth } from '@/context/auth-context';
import { X, Loader2, Terminal } from 'lucide-react';
import QuoteResultDisplay from '@/components/QuoteResultDisplay'; // Import the new component

const initialPiece: Piece = { weight_kg: 0, length_cm: 0, width_cm: 0, height_cm: 0 };

export default function NewQuotePage() {
  const { token } = useAuth();

  // State for customer selection
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [selectedCustomerId, setSelectedCustomerId] = useState<string>('');
  const [isLoadingCustomers, setIsLoadingCustomers] = useState(true);
  const [customerError, setCustomerError] = useState<string | null>(null);

  // State for calculation
  const [calculationResult, setCalculationResult] = useState<BuyOffer | null>(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [calculationError, setCalculationError] = useState<string | null>(null);

  // State for form inputs
  const [pieces, setPieces] = useState<Piece[]>([initialPiece]);
  const [origin, setOrigin] = useState('SYD');
  const [destination, setDestination] = useState('POM');
  
  useEffect(() => {
    if (!token) return;

    const fetchCustomers = async () => {
      try {
        setIsLoadingCustomers(true);
        const fetchedCustomers = await getCustomers(token);
        setCustomers(fetchedCustomers);
        setCustomerError(null);
      } catch (err) {
        setCustomerError('Failed to fetch customers.');
        console.error(err);
      } finally {
        setIsLoadingCustomers(false);
      }
    };

    fetchCustomers();
  }, [token]);

  const handlePieceChange = (index: number, field: keyof Piece, value: string) => {
    const newPieces = [...pieces];
    newPieces[index] = { ...newPieces[index], [field]: Number(value) || 0 };
    setPieces(newPieces);
  };

  const addPiece = () => {
    setPieces([...pieces, initialPiece]);
  };

  const removePiece = (index: number) => {
    if (pieces.length <= 1) return; // Don't remove the last piece
    const newPieces = pieces.filter((_, i) => i !== index);
    setPieces(newPieces);
  };

  const handleCalculate = async () => {
    if (!token) {
      setCalculationError("Authentication token is missing.");
      return;
    }

    // Reset previous results and set loading state
    setIsCalculating(true);
    setCalculationError(null);
    setCalculationResult(null);

    try {
      // Assemble the request payload
      const quoteDetails: QuoteContext = {
        customer_id: Number(selectedCustomerId),
        origin_iata: origin,
        dest_iata: destination,
        pieces: pieces,
      };

      // Call the API function
      const result = await calculateQuoteV2(quoteDetails, token);
      setCalculationResult(result);

    } catch (err: any) {
      setCalculationError(err.message || "An unknown error occurred.");
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>Create New Quote</CardTitle>
          <CardDescription>Fill in the details below to calculate the shipment cost.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Customer Selection */}
          <div className="grid w-full max-w-sm items-center gap-1.5">
            <Label htmlFor="customer-select">Customer</Label>
            <Select
              value={selectedCustomerId}
              onValueChange={(value) => {
                if (isLoadingCustomers || customers.length === 0) {
                  return;
                }
                setSelectedCustomerId(value);
              }}
            >
              <SelectTrigger
                id="customer-select"
                aria-disabled={isLoadingCustomers || customers.length === 0}
                className={
                  isLoadingCustomers || customers.length === 0
                    ? "pointer-events-none opacity-60"
                    : undefined
                }
              >
                <SelectValue placeholder={isLoadingCustomers ? 'Loading customers...' : 'Select a customer'} />
              </SelectTrigger>
              <SelectContent>
                {customers.map((customer) => (
                  <SelectItem key={customer.id} value={String(customer.id)}>
                    {customer.company_name || customer.name || `Customer ${customer.id}`}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {customerError && <p className="text-sm text-red-500">{customerError}</p>}
          </div>

          {/* Origin / Destination */}
          <div className="grid grid-cols-2 gap-4">
            <div className="space-y-1.5">
              <Label htmlFor="origin">Origin (IATA)</Label>
              <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} maxLength={3} />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="destination">Destination (IATA)</Label>
              <Input id="destination" value={destination} onChange={(e) => setDestination(e.target.value.toUpperCase())} maxLength={3} />
            </div>
          </div>

          {/* Shipment Pieces Section */}
          <div>
            <Label>Shipment Pieces</Label>
            <div className="space-y-4 pt-2">
              {pieces.map((piece, index) => (
                <div key={index} className="flex items-end gap-2 p-2 border rounded-md">
                  <div className="grid flex-1 grid-cols-2 md:grid-cols-4 gap-2">
                    <div className="space-y-1">
                      <Label htmlFor={`weight-${index}`} className="text-xs">Weight (kg)</Label>
                      <Input id={`weight-${index}`} type="number" value={piece.weight_kg} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`length-${index}`} className="text-xs">Length (cm)</Label>
                      <Input id={`length-${index}`} type="number" value={piece.length_cm} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`width-${index}`} className="text-xs">Width (cm)</Label>
                      <Input id={`width-${index}`} type="number" value={piece.width_cm} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} />
                    </div>
                    <div className="space-y-1">
                      <Label htmlFor={`height-${index}`} className="text-xs">Height (cm)</Label>
                      <Input id={`height-${index}`} type="number" value={piece.height_cm} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} />
                    </div>
                  </div>
                  <Button variant="ghost" size="icon" onClick={() => removePiece(index)} disabled={pieces.length <= 1}>
                    <X className="h-4 w-4" />
                  </Button>
                </div>
              ))}
              <Button onClick={addPiece} variant="outline" size="sm">
                Add Piece
              </Button>
            </div>
          </div>
        </CardContent>
        <CardFooter>
          <Button onClick={handleCalculate} disabled={isCalculating || !selectedCustomerId}>
            {isCalculating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Calculate Cost
          </Button>
        </CardFooter>
      </Card>

      {/* --- New Section for Displaying Results --- */}
      <div>
        {isCalculating && (
          <div className="flex items-center justify-center p-8">
            <Loader2 className="mr-2 h-8 w-8 animate-spin" />
            <span className="text-lg">Calculating cost...</span>
          </div>
        )}

        {calculationError && (
          <Alert variant="destructive">
            <Terminal className="h-4 w-4" />
            <AlertTitle>Calculation Failed</AlertTitle>
            <AlertDescription>
              {calculationError}
            </AlertDescription>
          </Alert>
        )}

        {calculationResult && (
          <QuoteResultDisplay result={calculationResult} />
        )}
      </div>
      {/* ------------------------------------------- */}
    </div>
  );
}
