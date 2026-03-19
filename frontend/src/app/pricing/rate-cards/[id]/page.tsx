'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { getLogicalRateCards, type LogicalRateCard, type LogicalRateCardLine } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

function formatScope(scope: string | null): string {
  const labels: Record<string, string> = {
    A2A: 'Airport-to-Airport',
    A2D: 'Airport-to-Door',
    D2A: 'Door-to-Airport',
    D2D: 'Door-to-Door',
  };
  if (!scope) return 'Mixed';
  return labels[scope] || scope;
}

function formatRate(line: LogicalRateCardLine): string {
  if (line.amount) {
    return `${line.amount} ${line.currency ?? ''}`.trim();
  }
  if (line.rate_per_kg) {
    return `${line.rate_per_kg} ${line.currency ?? ''}/kg`.trim();
  }
  if (line.rate_per_shipment) {
    return `${line.rate_per_shipment} ${line.currency ?? ''}/shipment`.trim();
  }
  if (line.percent_rate) {
    return `${line.percent_rate}%`;
  }
  return 'Weight break / derived';
}

function formatCoverage(line: LogicalRateCardLine): string {
  if (line.location_code) {
    const extras = [line.direction, line.payment_term].filter(Boolean).join(' / ');
    return extras ? `${line.location_code} (${extras})` : line.location_code;
  }
  if (line.origin_code && line.destination_code) {
    return `${line.origin_code} -> ${line.destination_code}`;
  }
  return line.coverage_label ?? 'N/A';
}

export default function LogicalRateCardDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [card, setCard] = useState<LogicalRateCard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadCard() {
      try {
        setLoading(true);
        setError(null);
        const cards = await getLogicalRateCards();
        const match = cards.find((item) => item.id === id) ?? null;
        if (!match) {
          setError('Logical card not found.');
          return;
        }
        setCard(match);
      } catch (loadError) {
        console.error('Failed to load logical rate card:', loadError);
        setError(loadError instanceof Error ? loadError.message : 'Failed to load logical card.');
      } finally {
        setLoading(false);
      }
    }

    loadCard();
  }, [id]);

  const groupedLines = useMemo(() => {
    if (!card) return [];
    const groups = new Map<string, LogicalRateCardLine[]>();
    for (const line of card.lines) {
      const groupKey = `${line.source_label}::${line.source_table}`;
      if (!groups.has(groupKey)) {
        groups.set(groupKey, []);
      }
      groups.get(groupKey)?.push(line);
    }
    return Array.from(groups.entries());
  }, [card]);

  if (loading) {
    return <div className="container mx-auto py-10 text-muted-foreground">Loading...</div>;
  }

  if (error || !card) {
    return (
      <div className="container mx-auto py-10">
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
          {error || 'Logical card not found.'}
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-6 py-10">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="mb-2 text-sm text-muted-foreground">
            <Link href="/pricing/rate-cards" className="hover:underline">
              V4 Pricing Cards
            </Link>
            {' / '}
            {card.name}
          </div>
          <h1 className="text-3xl font-bold">{card.name}</h1>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{card.description}</p>
        </div>
        <Button variant="outline" asChild>
          <Link href="/pricing/rate-cards">Back</Link>
        </Button>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase text-muted-foreground">Domain</div>
          <div className="mt-1 font-medium">{card.domain}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase text-muted-foreground">Scope</div>
          <div className="mt-1 font-medium">{formatScope(card.service_scope)}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase text-muted-foreground">Pricing Model</div>
          <div className="mt-1 font-medium">{card.pricing_model}</div>
        </div>
        <div className="rounded-lg border p-4">
          <div className="text-xs uppercase text-muted-foreground">Visible Lines</div>
          <div className="mt-1 font-medium">{card.line_count}</div>
        </div>
      </div>

      <div className="rounded-lg border p-4">
        <div className="mb-2 text-xs uppercase text-muted-foreground">Source Tables</div>
        <div className="flex flex-wrap gap-2">
          {card.source_tables.map((tableName) => (
            <Badge key={tableName} variant="secondary">
              {tableName}
            </Badge>
          ))}
        </div>
      </div>

      <div className="rounded-lg border p-4">
        <div className="mb-2 text-xs uppercase text-muted-foreground">Architecture Notes</div>
        <ul className="space-y-1 text-sm text-slate-700">
          {card.notes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </div>

      <div className="rounded-lg border p-4">
        <div className="mb-2 text-xs uppercase text-muted-foreground">Coverage</div>
        <div className="flex flex-wrap gap-2">
          {card.coverage.map((item) => (
            <Badge key={item} variant="outline">
              {item}
            </Badge>
          ))}
        </div>
      </div>

      {groupedLines.map(([groupKey, lines]) => (
        <div key={groupKey} className="rounded-lg border">
          <div className="border-b px-4 py-3">
            <div className="font-medium">{lines[0]?.source_label}</div>
            <div className="text-xs text-muted-foreground">
              {lines[0]?.source_table} / {lines[0]?.pricing_role}
            </div>
          </div>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Product</TableHead>
                <TableHead>Coverage</TableHead>
                <TableHead>Rate Type</TableHead>
                <TableHead>Rate</TableHead>
                <TableHead>Counterparty</TableHead>
                <TableHead>Validity</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => (
                <TableRow key={line.id}>
                  <TableCell>
                    <div className="font-medium">{line.product_code_code}</div>
                    <div className="text-xs text-muted-foreground">
                      {line.product_code_description}
                    </div>
                  </TableCell>
                  <TableCell>{formatCoverage(line)}</TableCell>
                  <TableCell>{line.rate_type ?? 'N/A'}</TableCell>
                  <TableCell>{formatRate(line)}</TableCell>
                  <TableCell>{line.counterparty ?? 'N/A'}</TableCell>
                  <TableCell>
                    <div className="text-sm">{line.valid_from}</div>
                    <div className="text-xs text-muted-foreground">to {line.valid_until}</div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      ))}
    </div>
  );
}
