'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { PlusCircle, RefreshCw } from 'lucide-react';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { usePermissions } from '@/hooks/usePermissions';
import { useConfirm } from '@/hooks/useConfirm';
import { useToast } from '@/context/toast-context';
import {
  getProductCodes,
  type LocalCOGSRateRecord,
  type LocalRateRecord,
  type RateChangeLogEntry,
  type RateRevisionOptions,
  type LocalRateUpsertPayload,
  type ProductCodeOption,
  type V4RateListParams,
} from '@/lib/api';
import LocalRateFormModal from './LocalRateFormModal';
import RateHistorySheet from './RateHistorySheet';

type ModalState<T extends LocalRateRecord | LocalCOGSRateRecord> =
  | { mode: 'create'; rate: T | null }
  | { mode: 'edit'; rate: T }
  | { mode: 'revise'; rate: T };

interface LocalRateManagerPageProps<T extends LocalRateRecord | LocalCOGSRateRecord> {
  title: string;
  description: string;
  pathLabel: string;
  productDomains: string[];
  supportsPaymentTerm: boolean;
  supportsCounterparty: boolean;
  listRates: (params?: V4RateListParams) => Promise<T[]>;
  createRate: (payload: LocalRateUpsertPayload) => Promise<T>;
  updateRate: (id: number | string, payload: Partial<LocalRateUpsertPayload>) => Promise<T>;
  reviseRate: (id: number | string, payload: LocalRateUpsertPayload & RateRevisionOptions) => Promise<T>;
  retireRate: (id: number | string) => Promise<{ deleted?: boolean; detail?: string } | T>;
  loadHistory: (id: number | string) => Promise<RateChangeLogEntry[]>;
}

function getStatusLabel(rate: LocalRateRecord | LocalCOGSRateRecord): 'ACTIVE' | 'EXPIRED' | 'SCHEDULED' {
  const today = new Date().toISOString().split('T')[0];
  if (rate.valid_until < today) return 'EXPIRED';
  if (rate.valid_from > today) return 'SCHEDULED';
  return 'ACTIVE';
}

function statusBadge(status: 'ACTIVE' | 'EXPIRED' | 'SCHEDULED') {
  if (status === 'ACTIVE') {
    return <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">Active</Badge>;
  }
  if (status === 'SCHEDULED') {
    return <Badge className="border-blue-200 bg-blue-50 text-blue-700">Scheduled</Badge>;
  }
  return <Badge variant="outline" className="border-slate-300 text-slate-600">Expired</Badge>;
}

export default function LocalRateManagerPage<T extends LocalRateRecord | LocalCOGSRateRecord>({
  title,
  description,
  pathLabel,
  productDomains,
  supportsPaymentTerm,
  supportsCounterparty,
  listRates,
  createRate,
  updateRate,
  reviseRate,
  retireRate,
  loadHistory,
}: LocalRateManagerPageProps<T>) {
  const { canEditRateCards } = usePermissions();
  const confirm = useConfirm();
  const { toast } = useToast();

  const [rates, setRates] = useState<T[]>([]);
  const [products, setProducts] = useState<ProductCodeOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | 'ACTIVE' | 'EXPIRED' | 'SCHEDULED'>('all');
  const [productFilter, setProductFilter] = useState('all');
  const [directionFilter, setDirectionFilter] = useState('all');
  const [paymentTermFilter, setPaymentTermFilter] = useState('all');
  const [modalState, setModalState] = useState<ModalState<T> | null>(null);
  const [historyRate, setHistoryRate] = useState<T | null>(null);
  const [activeActionId, setActiveActionId] = useState<number | string | null>(null);

  const loadRates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rateData, productData] = await Promise.all([
        listRates(search ? { search } : undefined),
        Promise.all(productDomains.map((domain) => getProductCodes({ domain }))),
      ]);
      setRates(rateData);
      setProducts(productData.flat());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load rates.');
    } finally {
      setLoading(false);
    }
  }, [listRates, productDomains, search]);

  useEffect(() => {
    if (!canEditRateCards) return;
    void loadRates();
  }, [canEditRateCards, loadRates]);

  const filteredRates = useMemo(
    () =>
      rates.filter((rate) => {
        const status = getStatusLabel(rate);
        if (statusFilter !== 'all' && status !== statusFilter) return false;
        if (productFilter !== 'all' && String(rate.product_code) !== productFilter) return false;
        if (directionFilter !== 'all' && rate.direction !== directionFilter) return false;
        if (supportsPaymentTerm && paymentTermFilter !== 'all' && rate.payment_term !== paymentTermFilter) return false;
        return true;
      }),
    [directionFilter, paymentTermFilter, productFilter, rates, statusFilter, supportsPaymentTerm],
  );

  const handleRetire = async (rate: T) => {
    const approved = await confirm({
      title: `Retire ${pathLabel}?`,
      description: `Retire ${rate.product_code_code} at ${rate.location}? Active rows will be closed out instead of deleted.`,
      confirmLabel: 'Retire row',
      cancelLabel: 'Keep row',
      variant: 'destructive',
    });
    if (!approved) return;

    try {
      setActiveActionId(rate.id);
      const result = await retireRate(rate.id);
      toast({
        title: `${pathLabel} retired`,
        description:
          'deleted' in result && result.deleted
            ? result.detail || 'Future-dated row deleted.'
            : 'The row was retired safely.',
      });
      await loadRates();
    } catch (retireError) {
      toast({
        title: 'Retire failed',
        description: retireError instanceof Error ? retireError.message : `Failed to retire ${pathLabel}.`,
        variant: 'destructive',
      });
    } finally {
      setActiveActionId(null);
    }
  };

  if (!canEditRateCards) {
    return (
      <StandardPageContainer>
        <PageHeader title={title} description={description} />
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="px-6 py-5 text-sm text-muted-foreground">
            You do not have access to this rate manager.
          </CardContent>
        </Card>
      </StandardPageContainer>
    );
  }

  return (
    <StandardPageContainer>
      <PageHeader title={title} description={description} />

      <div className="flex flex-wrap gap-3">
        <Button onClick={() => setModalState({ mode: 'create', rate: null })}>
          <PlusCircle className="mr-2 h-4 w-4" />
          Add {pathLabel}
        </Button>
        <Button variant="outline" onClick={() => void loadRates()} disabled={loading}>
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

      <Alert>
        <AlertDescription>
          Use <span className="font-medium">New Effective Rate</span> for active rows whenever possible. Direct edits are available for corrections, but the preferred workflow is to create a new effective-dated row.
        </AlertDescription>
      </Alert>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="gap-4">
          <CardTitle>Filters</CardTitle>
          <div className="grid gap-3 md:grid-cols-4">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search product, location, or counterparty"
            />
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as typeof statusFilter)}>
              <SelectTrigger>
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                <SelectItem value="ACTIVE">Active</SelectItem>
                <SelectItem value="SCHEDULED">Scheduled</SelectItem>
                <SelectItem value="EXPIRED">Expired</SelectItem>
              </SelectContent>
            </Select>
            <Select value={productFilter} onValueChange={setProductFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Product code" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All products</SelectItem>
                {products.map((product) => (
                  <SelectItem key={String(product.id)} value={String(product.id)}>
                    {product.code}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={directionFilter} onValueChange={setDirectionFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Direction" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All directions</SelectItem>
                <SelectItem value="EXPORT">Export</SelectItem>
                <SelectItem value="IMPORT">Import</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {supportsPaymentTerm ? (
            <div className="max-w-xs">
              <Select value={paymentTermFilter} onValueChange={setPaymentTermFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Payment Term" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All payment terms</SelectItem>
                  <SelectItem value="ANY">Any</SelectItem>
                  <SelectItem value="PREPAID">Prepaid</SelectItem>
                  <SelectItem value="COLLECT">Collect</SelectItem>
                </SelectContent>
              </Select>
            </div>
          ) : null}
        </CardHeader>
      </Card>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="py-8 text-sm text-muted-foreground">Loading rates...</div>
          ) : error ? (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : filteredRates.length === 0 ? (
            <div className="py-8 text-sm text-muted-foreground">No rows matched the current filters.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>Product</TableHead>
                  <TableHead>Location</TableHead>
                  <TableHead>Direction</TableHead>
                  {supportsPaymentTerm ? <TableHead>Payment Term</TableHead> : null}
                  {supportsCounterparty ? <TableHead>Counterparty</TableHead> : null}
                  <TableHead>Basis</TableHead>
                  <TableHead>Validity</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRates.map((rate) => {
                  const status = getStatusLabel(rate);
                  const basis = rate.weight_breaks?.length
                    ? 'Weight breaks'
                    : rate.rate_type === 'PERCENT'
                      ? `${rate.amount}% of ${rate.percent_of_product_code_code || 'base'}`
                      : rate.is_additive
                        ? `${rate.amount}/kg + ${rate.additive_flat_amount || '0'}`
                        : rate.rate_type === 'PER_KG'
                          ? `${rate.amount}/kg`
                          : `${rate.amount}/shipment`;

                  return (
                    <TableRow key={rate.id}>
                      <TableCell>{statusBadge(status)}</TableCell>
                      <TableCell>
                        <div className="font-medium">{rate.product_code_code}</div>
                        <div className="text-xs text-muted-foreground">{rate.product_code_description}</div>
                      </TableCell>
                      <TableCell>{rate.location}</TableCell>
                      <TableCell>{rate.direction}</TableCell>
                      {supportsPaymentTerm ? <TableCell>{rate.payment_term || 'N/A'}</TableCell> : null}
                      {supportsCounterparty ? (
                        <TableCell>
                          {(rate as LocalCOGSRateRecord).agent_name || (rate as LocalCOGSRateRecord).carrier_name || 'N/A'}
                        </TableCell>
                      ) : null}
                      <TableCell>{basis}</TableCell>
                      <TableCell>
                        <div>{rate.valid_from}</div>
                        <div className="text-xs text-muted-foreground">to {rate.valid_until}</div>
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-2">
                          <Button variant="outline" size="sm" onClick={() => setHistoryRate(rate)}>
                            History
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => setModalState({ mode: 'revise', rate })}>
                            New Effective Rate
                          </Button>
                          <Button variant="outline" size="sm" onClick={() => setModalState({ mode: 'edit', rate })}>
                            Edit
                          </Button>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => void handleRetire(rate)}
                            disabled={activeActionId === rate.id}
                          >
                            {activeActionId === rate.id ? 'Retiring...' : 'Retire'}
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <LocalRateFormModal<T>
        open={modalState !== null}
        onOpenChange={(open) => {
          if (!open) setModalState(null);
        }}
        mode={modalState?.mode ?? 'create'}
        initialRate={modalState?.rate ?? null}
        title={
          modalState?.mode === 'edit'
            ? `Edit ${pathLabel}`
            : modalState?.mode === 'revise'
              ? `Revise ${pathLabel}`
              : `Add ${pathLabel}`
        }
        description={
          modalState?.mode === 'edit'
            ? 'Update the selected row directly.'
            : modalState?.mode === 'revise'
              ? 'Create a new effective-dated row and optionally shorten the prior row automatically.'
              : 'Create a new V4 local rate row.'
        }
        productDomains={productDomains}
        supportsPaymentTerm={supportsPaymentTerm}
        supportsCounterparty={supportsCounterparty}
        createRate={createRate}
        updateRate={updateRate}
        reviseRate={reviseRate}
        onSuccess={loadRates}
      />

      <RateHistorySheet
        open={historyRate !== null}
        onOpenChange={(open) => {
          if (!open) setHistoryRate(null);
        }}
        rate={historyRate}
        title={pathLabel}
        loadHistory={loadHistory}
      />
    </StandardPageContainer>
  );
}
