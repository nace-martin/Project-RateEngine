'use client';

import { useEffect, useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet';
import { Separator } from '@/components/ui/separator';
import { type EffectiveDatedRateRecord, type RateChangeAction, type RateChangeLogEntry } from '@/lib/api';

interface RateHistorySheetProps<T extends EffectiveDatedRateRecord> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rate: T | null;
  title: string;
  loadHistory: (id: number | string) => Promise<RateChangeLogEntry[]>;
}

const FIELD_LABELS: Record<string, string> = {
  product_code: 'Product',
  origin_airport: 'Origin',
  destination_airport: 'Destination',
  origin_zone: 'Origin',
  destination_zone: 'Destination',
  location: 'Location',
  direction: 'Direction',
  payment_term: 'Payment Term',
  currency: 'Currency',
  rate_per_kg: 'Rate / KG',
  rate_per_shipment: 'Rate / Shipment',
  percent_rate: 'Percent Rate',
  amount: 'Amount',
  rate_type: 'Rate Type',
  additive_flat_amount: 'Additive Flat Amount',
  min_charge: 'Min Charge',
  max_charge: 'Max Charge',
  valid_from: 'Valid From',
  valid_until: 'Valid Until',
  agent: 'Agent',
  carrier: 'Carrier',
  is_additive: 'Is Additive',
  weight_breaks: 'Weight Breaks',
  percent_of_product_code: 'Percent Of Product',
  created_by: 'Created By',
  updated_by: 'Updated By',
  lineage_id: 'Lineage',
  supersedes_rate: 'Supersedes Row',
};

function actionBadge(action: RateChangeAction) {
  if (action === 'CREATE') return <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Create</Badge>;
  if (action === 'UPDATE') return <Badge className="border-amber-200 bg-amber-50 text-amber-700">Update</Badge>;
  if (action === 'RETIRE') return <Badge className="border-rose-200 bg-rose-50 text-rose-700">Retire</Badge>;
  if (action === 'DELETE') return <Badge variant="outline">Delete</Badge>;
  return <Badge className="border-blue-200 bg-blue-50 text-blue-700">Revise</Badge>;
}

function formatSnapshotValue(value: unknown): string {
  if (value == null || value === '') return 'None';
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  if (Array.isArray(value) || typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function summarizeSnapshot(snapshot: Record<string, unknown> | null) {
  if (!snapshot) return [];
  return Object.entries(snapshot)
    .filter(([key]) => !['id', 'created_at', 'updated_at'].includes(key))
    .filter(([, value]) => value !== null && value !== '')
    .slice(0, 12);
}

export default function RateHistorySheet<T extends EffectiveDatedRateRecord>({
  open,
  onOpenChange,
  rate,
  title,
  loadHistory,
}: RateHistorySheetProps<T>) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [entries, setEntries] = useState<RateChangeLogEntry[]>([]);

  useEffect(() => {
    if (!open || !rate) return;
    let cancelled = false;

    const run = async () => {
      setLoading(true);
      setError(null);
      try {
        const history = await loadHistory(rate.id);
        if (!cancelled) setEntries(history);
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : 'Failed to load history.');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [loadHistory, open, rate]);

  const heading = useMemo(() => {
    if (!rate) return title;
    return `${title} history`;
  }, [rate, title]);

  const lineageChain = useMemo(() => {
    const ordered = entries
      .map((entry) => entry.object_pk)
      .filter((value, index, array) => Boolean(value) && array.indexOf(value) === index);
    return ordered.slice().reverse();
  }, [entries]);

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-2xl">
        <SheetHeader>
          <SheetTitle>{heading}</SheetTitle>
          <SheetDescription>
            {rate
              ? `Audit trail for ${rate.product_code_code} (${rate.valid_from} to ${rate.valid_until}).`
              : 'Select a rate row to view audit history.'}
          </SheetDescription>
        </SheetHeader>

        <div className="mt-6 space-y-4">
          {rate?.lineage_id ? (
            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700">
              <div className="font-medium text-slate-900">Lineage</div>
              <div className="mt-1 font-mono text-xs text-slate-600">{rate.lineage_id}</div>
              {lineageChain.length > 1 ? (
                <div className="mt-2 text-xs text-slate-600">
                  Revision chain: {lineageChain.map((rowId) => `#${rowId}`).join(" -> ")}
                </div>
              ) : null}
            </div>
          ) : null}

          {loading ? <div className="text-sm text-muted-foreground">Loading history...</div> : null}

          {!loading && error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : null}

          {!loading && !error && entries.length === 0 ? (
            <Alert>
              <AlertDescription>No audit entries exist for this row yet.</AlertDescription>
            </Alert>
          ) : null}

          {!loading && !error
            ? entries.map((entry) => {
                const beforeRows = summarizeSnapshot(entry.before_snapshot);
                const afterRows = summarizeSnapshot(entry.after_snapshot);

                return (
                  <div key={entry.id} className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          {actionBadge(entry.action)}
                          <div className="text-sm font-medium text-slate-900">
                            {entry.actor_username || 'System'}
                          </div>
                        </div>
                        <div className="text-xs text-slate-500">
                          {new Date(entry.created_at).toLocaleString()}
                        </div>
                      </div>
                      <div className="text-xs text-slate-500">
                        Row ID <span className="font-mono">{entry.object_pk}</span>
                      </div>
                    </div>

                    <Separator className="my-4" />

                    <div className="grid gap-4 md:grid-cols-2">
                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                          Before
                        </div>
                        {beforeRows.length === 0 ? (
                          <div className="text-sm text-slate-500">No prior snapshot.</div>
                        ) : (
                          <div className="space-y-2 text-sm">
                            {beforeRows.map(([key, value]) => (
                              <div key={`${entry.id}-before-${key}`} className="grid grid-cols-[120px_1fr] gap-2">
                                <div className="text-slate-500">{FIELD_LABELS[key] || key}</div>
                                <div className="break-all text-slate-900">{formatSnapshotValue(value)}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>

                      <div className="space-y-2">
                        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500">
                          After
                        </div>
                        {afterRows.length === 0 ? (
                          <div className="text-sm text-slate-500">No post-change snapshot.</div>
                        ) : (
                          <div className="space-y-2 text-sm">
                            {afterRows.map(([key, value]) => (
                              <div key={`${entry.id}-after-${key}`} className="grid grid-cols-[120px_1fr] gap-2">
                                <div className="text-slate-500">{FIELD_LABELS[key] || key}</div>
                                <div className="break-all text-slate-900">{formatSnapshotValue(value)}</div>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })
            : null}
        </div>
      </SheetContent>
    </Sheet>
  );
}
