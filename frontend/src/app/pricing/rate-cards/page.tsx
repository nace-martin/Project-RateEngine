'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { getLogicalRateCards, type LogicalRateCard } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { formatServiceScope } from '@/lib/display';

export default function RateCardsPage() {
  const [rateCards, setRateCards] = useState<LogicalRateCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadRateCards() {
      try {
        setLoading(true);
        setError(null);
        const cards = await getLogicalRateCards();
        setRateCards(cards);
      } catch (loadError) {
        console.error('Failed to load V4 logical rate cards:', loadError);
        setError(loadError instanceof Error ? loadError.message : 'Failed to load rate cards.');
      } finally {
        setLoading(false);
      }
    }

    loadRateCards();
  }, []);

  return (
    <div className="container mx-auto py-10">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">V4 Pricing Cards</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Read-only logical views of the live V4 pricing architecture.
          </p>
        </div>
        <Link
          href="/pricing/rate-cards/upload"
          className="inline-flex items-center rounded-md border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-medium text-blue-800 hover:bg-blue-100"
        >
          Upload V4 CSV
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Logical Cards</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-8 text-center text-muted-foreground">Loading...</div>
          ) : error ? (
            <div className="py-8 text-center text-sm text-red-600">{error}</div>
          ) : rateCards.length === 0 ? (
            <div className="py-8 text-center text-muted-foreground">No logical cards found.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Card</TableHead>
                  <TableHead>Domain</TableHead>
                  <TableHead>Scope</TableHead>
                  <TableHead>Pricing Model</TableHead>
                  <TableHead>Source Tables</TableHead>
                  <TableHead className="text-right">Lines</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rateCards.map((card) => (
                  <TableRow key={card.id}>
                    <TableCell>
                      <div className="font-medium">{card.name}</div>
                      <div className="text-xs text-muted-foreground">{card.description}</div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{card.domain}</Badge>
                    </TableCell>
                    <TableCell>{formatServiceScope(card.service_scope, 'Mixed')}</TableCell>
                    <TableCell>{card.pricing_model}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-1">
                        {card.source_tables.map((tableName) => (
                          <Badge key={tableName} variant="secondary">
                            {tableName}
                          </Badge>
                        ))}
                      </div>
                    </TableCell>
                    <TableCell className="text-right">{card.line_count}</TableCell>
                    <TableCell>
                      <Button variant="outline" size="sm" asChild>
                        <Link href={`/pricing/rate-cards/${card.id}`}>View</Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
