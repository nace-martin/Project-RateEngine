'use client';

import Link from 'next/link';
import { PlusCircle, RefreshCw } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

export type RateStatus = 'ACTIVE' | 'EXPIRED' | 'SCHEDULED';

export function RateStatusBadge({ status }: { status: RateStatus }) {
  if (status === 'ACTIVE') {
    return <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Active</Badge>;
  }
  if (status === 'SCHEDULED') {
    return <Badge className="border-blue-200 bg-blue-50 text-blue-700">Scheduled</Badge>;
  }
  return <Badge variant="outline" className="border-slate-300 text-slate-600">Expired</Badge>;
}

export function RateManagerToolbar({
  pathLabel,
  loading,
  onAdd,
  onRefresh,
}: {
  pathLabel: string;
  loading: boolean;
  onAdd: () => void;
  onRefresh: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-3">
      <Button onClick={onAdd}>
        <PlusCircle className="mr-2 h-4 w-4" />
        Add {pathLabel}
      </Button>
      <Button variant="outline" onClick={onRefresh} disabled={loading}>
        <RefreshCw className="mr-2 h-4 w-4" />
        Refresh
      </Button>
      <Button variant="outline" asChild>
        <Link href="/pricing/manage">All Rate Managers</Link>
      </Button>
      <Button variant="outline" asChild>
        <Link href="/pricing/rate-cards">Back To Rate Overview</Link>
      </Button>
    </div>
  );
}

export function RateManagerLifecycleNotice() {
  return (
    <Alert>
      <AlertDescription>
        Use <span className="font-medium">New Effective Rate</span> for active rows whenever possible. Direct edits are available for corrections, but the preferred workflow is to create a new effective-dated row.
      </AlertDescription>
    </Alert>
  );
}

export function RateRowActions<T>({
  rate,
  isRetiring,
  onHistory,
  onRevise,
  onEdit,
  onRetire,
}: {
  rate: T;
  isRetiring: boolean;
  onHistory: (rate: T) => void;
  onRevise: (rate: T) => void;
  onEdit: (rate: T) => void;
  onRetire: (rate: T) => void;
}) {
  return (
    <div className="flex justify-end gap-2">
      <Button variant="outline" size="sm" onClick={() => onHistory(rate)}>
        History
      </Button>
      <Button variant="outline" size="sm" onClick={() => onRevise(rate)}>
        New Effective Rate
      </Button>
      <Button variant="outline" size="sm" onClick={() => onEdit(rate)}>
        Edit
      </Button>
      <Button variant="outline" size="sm" onClick={() => onRetire(rate)} disabled={isRetiring}>
        {isRetiring ? 'Retiring...' : 'Retire'}
      </Button>
    </div>
  );
}
