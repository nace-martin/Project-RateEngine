// frontend/src/app/quotes/new/page.tsx

"use client";

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { createQuoteV2 } from '@/lib/api'; // Import our new function

export default function NewQuotePage() {
  const [chargeableKg, setChargeableKg] = useState('120');
  const [audAmount, setAudAmount] = useState('1000');
  const [isLoading, setIsLoading] = useState(false);
  const [quoteResult, setQuoteResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsLoading(true);
    setError(null);
    setQuoteResult(null);

    // --- This is a HARDCODED request for demonstration ---
    // In a real app, these IDs would come from dropdowns or search boxes.
    const quoteRequest = {
      scenario: 'IMPORT_D2D_COLLECT',
      chargeable_kg: chargeableKg,
      bill_to_id: '38d20932-7dc6-4812-82a0-2285ecec3177', // Replace with a real ID from your DB
      shipper_id: '2ba53f43-6733-4997-880d-9373c4bae881', // Replace with a real ID from your DB
      consignee_id: '38d20932-7dc6-4812-82a0-2285ecec3177', // Replace with a real ID from your DB
      buy_lines: [
        {
          currency: 'AUD',
          amount: audAmount,
          description: 'Air Freight Charges',
        },
      ],
      // Fields needed for export scenario
      origin_code: 'BNE',
      destination_code: 'POM',
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
    <div className="container mx-auto p-4">
      <Card>
        <CardHeader>
          <CardTitle>Create New Quote (V2 Engine)</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="chargeableKg">Chargeable Weight (kg)</Label>
              <Input
                id="chargeableKg"
                value={chargeableKg}
                onChange={(e) => setChargeableKg(e.target.value)}
                required
              />
            </div>
            <div>
              <Label htmlFor="audAmount">Buy Amount (AUD)</Label>
              <Input
                id="audAmount"
                value={audAmount}
                onChange={(e) => setAudAmount(e.target.value)}
                required
              />
            </div>
            <Button type="submit" disabled={isLoading}>
              {isLoading ? 'Calculating...' : 'Calculate Quote'}
            </Button>
          </form>

          {error && (
            <div className="mt-4 text-red-500">
              <p><strong>Error:</strong> {error}</p>
            </div>
          )}

          {quoteResult && (
            <div className="mt-6">
              <h3 className="text-lg font-semibold">Quote Calculation Successful!</h3>
              <p><strong>Quote Number:</strong> {quoteResult.quote_number}</p>
              <p><strong>Grand Total:</strong> {quoteResult.totals?.grand_total_pgk} PGK</p>
              <pre className="mt-2 p-2 bg-gray-100 rounded-md">
                {JSON.stringify(quoteResult, null, 2)}
              </pre>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}