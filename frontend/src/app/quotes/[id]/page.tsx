// frontend/src/app/quotes/[id]/page.tsx

"use client";

import { useEffect, useState } from 'react';
import { getQuoteV2 } from '@/lib/api'; // Import our new V2 function
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import type { QuoteV2Line, QuoteV2Response } from '@/lib/types';

export default function QuoteDetailPage({ params }: { params: { id: string } }) {
  const [quote, setQuote] = useState<QuoteV2Response | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchQuote = async () => {
      setIsLoading(true);
      try {
        const data = await getQuoteV2(params.id); // Use the new function
        setQuote(data);
      } catch (err: unknown) {
        if (err instanceof Error) {
          setError(err.message || 'Failed to fetch quote details.');
        } else {
          setError('Failed to fetch quote details.');
        }
      } finally {
        setIsLoading(false);
      }
    };

    fetchQuote();
  }, [params.id]);

  if (isLoading) {
    return <div className="p-4">Loading quote details...</div>;
  }

  if (error) {
    return <div className="p-4 text-red-500">Error: {error}</div>;
  }

  if (!quote) {
    return <div className="p-4">Quote not found.</div>;
  }

  return (
    <div className="container mx-auto p-4 space-y-6">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold">Quote: {quote.quote_number ?? params.id}</h1>
        <Badge>{quote.status ?? 'UNKNOWN'}</Badge>
      </div>

      <Card>
        <CardHeader><CardTitle>Summary</CardTitle></CardHeader>
        <CardContent>
          <p><strong>Scenario:</strong> {quote.scenario}</p>
          <p><strong>Grand Total:</strong> {quote.totals?.grand_total_pgk} PGK</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle>Charge Breakdown</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Section</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Amount (PGK)</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {quote.lines?.map((line: QuoteV2Line, index: number) => (
                <TableRow key={index}>
                  <TableCell>
                    <Badge variant="outline">{line.section ?? 'N/A'}</Badge>
                  </TableCell>
                  <TableCell>{line.description ?? 'N/A'}</TableCell>
                  <TableCell className="text-right">
                    {line.sell_amount_pgk ?? '—'}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
