'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
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
  type LaneCOGSRateRecord,
  type LaneRateRecord,
  type RateChangeLogEntry,
  type RateRevisionOptions,
  type LaneRateUpsertPayload,
  type ProductCodeOption,
  type V4RateListParams,
} from '@/lib/api';
import LaneRateFormModal from './LaneRateFormModal';
import RateHistorySheet from './RateHistorySheet';
import { getRateStatus } from '@/lib/pricing/rate-utils';
import { RateManagerLifecycleNotice, RateManagerToolbar, RateRowActions, RateStatusBadge } from './shared-page-components';

type ModalState<T extends LaneRateRecord | LaneCOGSRateRecord> =
  | { mode: 'create'; rate: T | null }
  | { mode: 'edit'; rate: T }
  | { mode: 'revise'; rate: T };

interface LaneRateManagerPageProps<T extends LaneRateRecord | LaneCOGSRateRecord> {
  title: string;
  description: string;
  pathLabel: string;
  productDomain: string;
  routeFieldNames: {
    origin: 'origin_airport' | 'origin_zone';
    destination: 'destination_airport' | 'destination_zone';
    originLabel: string;
    destinationLabel: string;
  };
  supportsCounterparty: boolean;
  supportsPercent: boolean;
  listRates: (params?: V4RateListParams) => Promise<T[]>;
  createRate: (payload: LaneRateUpsertPayload) => Promise<T>;
  updateRate: (id: number | string, payload: Partial<LaneRateUpsertPayload>) => Promise<T>;
  reviseRate: (id: number | string, payload: LaneRateUpsertPayload & RateRevisionOptions) => Promise<T>;
  retireRate: (id: number | string) => Promise<{ deleted?: boolean; detail?: string } | T>;
  loadHistory: (id: number | string) => Promise<RateChangeLogEntry[]>;
}

export default function LaneRateManagerPage<T extends LaneRateRecord | LaneCOGSRateRecord>({
  title,
  description,
  pathLabel,
  productDomain,
  routeFieldNames,
  supportsCounterparty,
  supportsPercent,
  listRates,
  createRate,
  updateRate,
  reviseRate,
  retireRate,
  loadHistory,
}: LaneRateManagerPageProps<T>) {
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
  const [currencyFilter, setCurrencyFilter] = useState('all');
  const [modalState, setModalState] = useState<ModalState<T> | null>(null);
  const [historyRate, setHistoryRate] = useState<T | null>(null);
  const [activeActionId, setActiveActionId] = useState<number | string | null>(null);

  const loadRates = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [rateData, productData] = await Promise.all([
        listRates(search ? { search } : undefined),
        getProductCodes({ domain: productDomain }),
      ]);
      setRates(rateData);
      setProducts(productData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load rates.');
    } finally {
      setLoading(false);
    }
  }, [listRates, productDomain, search]);

  useEffect(() => {
    if (!canEditRateCards) return;
    void loadRates();
  }, [canEditRateCards, loadRates]);

  const filteredRates = useMemo(
    () =>
      rates.filter((rate) => {
        const status = getRateStatus(rate);
        if (statusFilter !== 'all' && status !== statusFilter) return false;
        if (productFilter !== 'all' && String(rate.product_code) !== productFilter) return false;
        if (currencyFilter !== 'all' && rate.currency !== currencyFilter) return false;
        return true;
      }),
    [currencyFilter, productFilter, rates, statusFilter],
  );

  const currencies = useMemo(
    () => Array.from(new Set(rates.map((rate) => rate.currency))).sort(),
    [rates],
  );

  const handleRetire = async (rate: T) => {
    const approved = await confirm({
      title: `Retire ${pathLabel}?`,
      description: `Retire ${rate.product_code_code} for ${String(rate[routeFieldNames.origin])} -> ${String(rate[routeFieldNames.destination])}? Active rows will be closed out instead of deleted.`,
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

      <RateManagerToolbar
        pathLabel={pathLabel}
        loading={loading}
        onAdd={() => setModalState({ mode: 'create', rate: null })}
        onRefresh={() => void loadRates()}
      />

      <RateManagerLifecycleNotice />

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="gap-4">
          <CardTitle>Filters</CardTitle>
          <div className="grid gap-3 md:grid-cols-4">
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search product, route, or counterparty"
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
            <Select value={currencyFilter} onValueChange={setCurrencyFilter}>
              <SelectTrigger>
                <SelectValue placeholder="Currency" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All currencies</SelectItem>
                {currencies.map((currency) => (
                  <SelectItem key={currency} value={currency}>
                    {currency}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
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
                  <TableHead>Route</TableHead>
                  {supportsCounterparty ? <TableHead>Counterparty</TableHead> : null}
                  <TableHead>Basis</TableHead>
                  <TableHead>Validity</TableHead>
                  <TableHead>Updated</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRates.map((rate) => {
                  const status = getRateStatus(rate);
                  const basis = rate.weight_breaks?.length
                    ? 'Weight breaks'
                    : rate.percent_rate
                      ? `${rate.percent_rate}%`
                      : rate.is_additive
                        ? `${rate.rate_per_kg || '0'}/kg + ${rate.rate_per_shipment || '0'}`
                        : rate.rate_per_kg
                          ? `${rate.rate_per_kg}/kg`
                          : `${rate.rate_per_shipment || '0'}/shipment`;

                  return (
                    <TableRow key={rate.id}>
                      <TableCell><RateStatusBadge status={status} /></TableCell>
                      <TableCell>
                        <div className="font-medium">{rate.product_code_code}</div>
                        <div className="text-xs text-muted-foreground">{rate.product_code_description}</div>
                      </TableCell>
                      <TableCell>
                        {String(rate[routeFieldNames.origin])} - {String(rate[routeFieldNames.destination])}
                      </TableCell>
                      {supportsCounterparty ? (
                        <TableCell>{(rate as LaneCOGSRateRecord).agent_name || (rate as LaneCOGSRateRecord).carrier_name || 'N/A'}</TableCell>
                      ) : null}
                      <TableCell>{basis}</TableCell>
                      <TableCell>
                        <div>{rate.valid_from}</div>
                        <div className="text-xs text-muted-foreground">to {rate.valid_until}</div>
                      </TableCell>
                      <TableCell>
                        <div>{new Date(rate.updated_at).toLocaleDateString()}</div>
                        <div className="text-xs text-muted-foreground">
                          {(rate as LaneCOGSRateRecord).updated_by_username || 'System'}
                        </div>
                      </TableCell>
                      <TableCell className="text-right">
                        <RateRowActions
                          rate={rate}
                          isRetiring={activeActionId === rate.id}
                          onHistory={setHistoryRate}
                          onRevise={(selectedRate) => setModalState({ mode: 'revise', rate: selectedRate })}
                          onEdit={(selectedRate) => setModalState({ mode: 'edit', rate: selectedRate })}
                          onRetire={(selectedRate) => void handleRetire(selectedRate)}
                        />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <LaneRateFormModal<T>
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
              : 'Create a new V4 rate row.'
        }
        productDomain={productDomain}
        createRate={createRate}
        updateRate={updateRate}
        reviseRate={reviseRate}
        routeFieldNames={routeFieldNames}
        supportsCounterparty={supportsCounterparty}
        supportsPercent={supportsPercent}
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
