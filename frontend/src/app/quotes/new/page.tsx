'use client';

import { Fragment, useState, useEffect } from 'react';
import { QuoteStatus, ComputeQuoteResponse, Money, QuoteDetail, QuoteLine } from '@/lib/types';
import { extractErrorMessage, extractErrorFromResponse } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Checkbox } from '@/components/ui/checkbox';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

// Define types for our data
interface Organization {
  id: number;
  name: string;
}

interface Piece {
  weight_kg: string;
  length_cm?: string;
  width_cm?: string;
  height_cm?: string;
}

const commodityTypes = [
  { value: 'GCR', label: 'General Cargo (GCR)' },
  { value: 'DGR', label: 'Dangerous Goods (DGR)' },
  { value: 'PER', label: 'Perishables (PER)' },
  { value: 'LAR', label: 'Live Animals (LAR)' },
];

const serviceScopeOptions = [
  { value: 'AIRPORT_AIRPORT', label: 'Airport to Airport' },
  { value: 'AIRPORT_DOOR', label: 'Airport to Door' },
  { value: 'DOOR_AIRPORT', label: 'Door to Airport' },
  { value: 'DOOR_DOOR', label: 'Door to Door' },
];

const incotermOptions = [
  { value: 'DAP', label: 'DAP (Delivered at Place)' },
  { value: 'EXW', label: 'EXW (Ex Works)' },
  { value: 'FOB', label: 'FOB (Free on Board)' },
  { value: 'DDP', label: 'DDP (Delivered Duty Paid)' },
  { value: 'CIF', label: 'CIF (Cost, Insurance & Freight)' },
  { value: 'CFR', label: 'CFR (Cost & Freight)' },
];

const incotermServiceScopeDefaults: Record<string, string> = {
  EXW: 'DOOR_AIRPORT',
  FOB: 'DOOR_AIRPORT',
  DAP: 'AIRPORT_DOOR',
  DDP: 'AIRPORT_DOOR',
  CIF: 'AIRPORT_AIRPORT',
  CFR: 'AIRPORT_AIRPORT',
};

const stationCountries: Record<string, string> = {
  BNE: 'AU',
  SYD: 'AU',
  CNS: 'AU',
  LAE: 'PG',
  POM: 'PG',
  HGU: 'PG',
};

const detectShipmentType = (originCode: string, destCode: string): string => {
  const originCountry = stationCountries[originCode] ?? '';
  const destCountry = stationCountries[destCode] ?? '';

  if (originCountry && destCountry && originCountry === destCountry) {
    return 'DOMESTIC';
  }
  if (originCountry === 'PG' && destCountry !== 'PG') {
    return 'EXPORT';
  }
  if (originCountry !== 'PG' && destCountry === 'PG') {
    return 'IMPORT';
  }
  if (originCountry && destCountry && originCountry !== destCountry) {
    return 'EXPORT';
  }
  return '';
};

export default function NewQuotePage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [origin, setOrigin] = useState('BNE');
  const [destination, setDestination] = useState('LAE');
  const [commodityCode, setCommodityCode] = useState('GCR');
  const [serviceScope, setServiceScope] = useState('AIRPORT_AIRPORT');
  const [incoterm, setIncoterm] = useState('DAP');
  const [paymentTerm, setPaymentTerm] = useState("PREPAID");
  const [shipmentType, setShipmentType] = useState('');
  const [isUrgent, setIsUrgent] = useState(false);
  const [pieces, setPieces] = useState<Piece[]>([{ weight_kg: '' }]);
  const [quoteResult, setQuoteResult] = useState<ComputeQuoteResponse | null>(null);
  const [quoteDetail, setQuoteDetail] = useState<QuoteDetail | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch organizations when the component mounts
  useEffect(() => {
    async function fetchOrganizations() {
      try {
        const apiBase = process.env.NEXT_PUBLIC_API_BASE;
        const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
        if (!apiBase) throw new Error('API configuration error');

        const response = await fetch(`${apiBase}/organizations/`, {
          headers: {
            ...(token ? { 'Authorization': `Token ${token}` } : {}),
          },
        });
        if (!response.ok) {
          const msg = await extractErrorFromResponse(response, 'Failed to fetch organizations');
          setError(msg);
          return;
        }
        const data = await response.json();
        setOrganizations(data);
        if (!selectedOrg && data.length) {
          setSelectedOrg(String(data[0].id));
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'An unknown error occurred');
      }
    }
    fetchOrganizations();
  }, []);

  useEffect(() => {
    const originCode = origin.trim().toUpperCase();
    const destCode = destination.trim().toUpperCase();
    setShipmentType(detectShipmentType(originCode, destCode));
  }, [origin, destination]);
  useEffect(() => {
    const normalized = (incoterm || "").toUpperCase();
    const suggestedScope = incotermServiceScopeDefaults[normalized];
    if (suggestedScope) {
      setServiceScope((current) => (current === suggestedScope ? current : suggestedScope));
    }
  }, [incoterm]);


  const fetchQuoteDetail = async (quoteId: number, token: string | null) => {
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      if (!apiBase) throw new Error('API configuration error');

      const response = await fetch(`${apiBase}/quotes/${quoteId}/`, {
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Token ${token}` } : {}),
        },
      });

      if (!response.ok) {
        const message = await extractErrorFromResponse(response, 'Failed to load quote detail');
        setError(message);
        setQuoteDetail(null);
        return;
      }

      const detail: QuoteDetail = await response.json();
      setQuoteDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load quote detail');
      setQuoteDetail(null);
    }
  };

  const formatMoney = (money?: Money) => {
    if (!money) return '-';
    return `${money.amount} ${money.currency}`;
  };


  const renderLineTable = (title: string, lines?: QuoteLine[]) => {
  if (!lines || lines.length === 0) return null;

  const filtered = lines.filter((line) => Number(line.amount.amount) !== 0);
  if (filtered.length === 0) return null;

  type SegmentKey = 'origin' | 'primary' | 'other';

  const segmentTitleMap: Record<SegmentKey, string> = {
    origin: 'Origin Charges',
    primary: 'Destination Charges',
    other: title,
  };

  const normaliseSegment = (segment: unknown, description: string): SegmentKey => {
    if (segment === 'origin') return 'origin';
    if (segment === 'primary') return 'primary';
    return description.toLowerCase().startsWith('origin -') ? 'origin' : 'primary';
  };

  const getCategory = (segment: SegmentKey, metaCategory?: unknown) => {
    if (typeof metaCategory === 'string' && metaCategory.trim().length > 0) return metaCategory;
    return segment === 'origin' ? 'Origin Charges' : 'Destination Charges';
  };

  type EnrichedLine = {
    line: QuoteLine;
    segment: SegmentKey;
    category: string;
  };

  const enriched: EnrichedLine[] = filtered.map((line) => {
    const meta = (line.meta ?? {}) as Record<string, unknown>;
    const segment = normaliseSegment(meta.segment, line.desc ?? line.code ?? '');
    const category = getCategory(segment, meta.category);
    return { line, segment, category };
  });

  const segments = new Map<
    SegmentKey,
    { title: string; categories: Map<string, EnrichedLine[]>; currency: string }
  >();

  enriched.forEach((item) => {
    const { line, segment, category } = item;
    if (!segments.has(segment)) {
      segments.set(segment, {
        title: segmentTitleMap[segment] ?? title,
        categories: new Map<string, EnrichedLine[]>(),
        currency: line.amount.currency,
      });
    }
    const segmentInfo = segments.get(segment)!;
    if (!segmentInfo.categories.has(category)) {
      segmentInfo.categories.set(category, []);
    }
    segmentInfo.categories.get(category)!.push(item);
  });

  const orderedSegments = (['origin', 'primary', 'other'] as SegmentKey[])
    .filter((key) => segments.has(key))
    .concat(Array.from(segments.keys()).filter((key) => !['origin', 'primary', 'other'].includes(key)));

  const approxZero = (value: number) => Math.abs(value) < 0.005;

  const parseAmount = (raw: unknown): number => {
    if (typeof raw === 'number') {
      return Number.isFinite(raw) ? raw : 0;
    }
    if (typeof raw === 'string') {
      const normalised = raw.replace(/,/g, '');
      const parsed = Number.parseFloat(normalised);
      return Number.isFinite(parsed) ? parsed : 0;
    }
    return 0;
  };

  const formatAmount = (value: number, currency: string) => {
    const safeValue = Number.isFinite(value) ? value : 0;
    const rounded = Math.round(safeValue * 100) / 100;
    const formatted = rounded.toLocaleString(undefined, {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
    return formatted + ' ' + currency;
  };

  const formatDisplay = (value: number, currency: string, dashIfZero = false) => {
    if (dashIfZero && approxZero(value)) {
      return '-';
    }
    return formatAmount(value, currency);
  };

  if (title === 'Sell Breakdown' && orderedSegments.length > 0) {
    return (
      <div className="mt-4">
        <h4 className="text-sm font-semibold mb-2">{title}</h4>
        <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="w-full text-sm">
            <thead className="bg-slate-100 dark:bg-slate-800">
              <tr className="text-left">
                <th className="px-3 py-2">Charge</th>
                <th className="px-3 py-2 text-right">Subtotal</th>
                <th className="px-3 py-2 text-right">GST</th>
                <th className="px-3 py-2 text-right">Total</th>
              </tr>
            </thead>
            <tbody>
              {orderedSegments.map((segmentKey) => {
                const info = segments.get(segmentKey)!;
                const categories = Array.from(info.categories.entries());
                let segmentSubtotal = 0;
                let segmentGST = 0;
                let segmentTotal = 0;

                return (
                  <Fragment key={segmentKey}>
                    <tr className="bg-slate-100/80 dark:bg-slate-800/80 font-semibold">
                      <td className="px-3 py-2" colSpan={4}>
                        {info.title}
                      </td>
                    </tr>
                    {categories.map(([categoryName, rows]) => (
                      <Fragment key={[segmentKey, categoryName].join('-')}>
                        <tr className="bg-slate-50 dark:bg-slate-900/40 text-sm font-semibold italic text-slate-700 dark:text-slate-300">
                          <td className="px-3 py-2" colSpan={4}>
                            {categoryName}
                          </td>
                        </tr>
                        {rows.map(({ line }, idx) => {
                          const meta = (line.meta ?? {}) as Record<string, unknown>;
                          const total = parseAmount(line.amount.amount);
                          const gst = segmentKey === 'primary' ? parseAmount(meta.gst_amount) : 0;
                          const subtotal = segmentKey === 'primary' ? Math.max(total - gst, 0) : total;

                          segmentSubtotal += subtotal;
                          segmentGST += gst;
                          segmentTotal += total;

                          return (
                            <tr
                              key={[segmentKey, categoryName, line.code, String(idx)].join('-')}
                              className="border-t border-slate-200 dark:border-slate-700"
                            >
                              <td className="px-3 py-2 align-top">
                                <div className="font-medium text-slate-900 dark:text-slate-100">
                                  {line.desc || line.code}
                                </div>
                                {line.desc && line.code && (
                                  <div className="text-xs text-slate-500 dark:text-slate-400">{line.code}</div>
                                )}
                              </td>
                              <td className="px-3 py-2 text-right">
                                {formatDisplay(subtotal, info.currency)}
                              </td>
                              <td className="px-3 py-2 text-right">
                                {formatDisplay(gst, info.currency, segmentKey !== 'primary')}
                              </td>
                              <td className="px-3 py-2 text-right">{formatDisplay(total, info.currency)}</td>
                            </tr>
                          );
                        })}
                      </Fragment>
                    ))}
                    <tr className="bg-slate-100 dark:bg-slate-800 font-semibold">
                      <td className="px-3 py-2 text-right">Total {info.title}</td>
                      <td className="px-3 py-2 text-right">{formatDisplay(segmentSubtotal, info.currency)}</td>
                      <td className="px-3 py-2 text-right">
                        {formatDisplay(segmentGST, info.currency, segmentKey !== 'primary')}
                      </td>
                      <td className="px-3 py-2 text-right">{formatDisplay(segmentTotal, info.currency)}</td>
                    </tr>
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    );
  }

  const renderSimpleTable = () => (
    <div className="mt-4">
      <h4 className="text-sm font-semibold mb-2">{title}</h4>
      <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 dark:bg-slate-800">
            <tr className="text-left">
              <th className="px-3 py-2">Charge</th>
              <th className="px-3 py-2">Qty</th>
              <th className="px-3 py-2">Unit</th>
              <th className="px-3 py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((line, idx) => (
              <tr key={[line.code, String(idx)].join('-')} className="border-t border-slate-200 dark:border-slate-700">
                <td className="px-3 py-2">
                  <div className="font-medium">{line.code}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{line.desc}</div>
                </td>
                <td className="px-3 py-2">{line.qty}</td>
                <td className="px-3 py-2">{line.unit}</td>
                <td className="px-3 py-2 text-right">{formatMoney(line.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );

  if (orderedSegments.length === 0) {
    return renderSimpleTable();
  }

  return (
    <div className="mt-4">
      <h4 className="text-sm font-semibold mb-2">{title}</h4>
      <div className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-100 dark:bg-slate-800">
            <tr className="text-left">
              <th className="px-3 py-2">Charge</th>
              <th className="px-3 py-2">Qty</th>
              <th className="px-3 py-2">Unit</th>
              <th className="px-3 py-2 text-right">Amount</th>
            </tr>
          </thead>
          <tbody>
            {orderedSegments.map((segmentKey) => {
              const info = segments.get(segmentKey)!;
              const categories = Array.from(info.categories.entries());
              const segmentTotal = categories.reduce(
                (acc, [, rows]) =>
                  acc + rows.reduce((inner, item) => inner + Number(item.line.amount.amount), 0),
                0,
              );
              return (
                <Fragment key={segmentKey}>
                  <tr className="bg-slate-100/80 dark:bg-slate-800/80 font-semibold">
                    <td className="px-3 py-2" colSpan={4}>
                      {info.title}
                    </td>
                  </tr>
                  {categories.map(([categoryName, rows]) => (
                    <Fragment key={[segmentKey, categoryName].join('-')}>
                      <tr className="bg-slate-50 dark:bg-slate-900/40 text-xs uppercase tracking-wide text-slate-500 dark:text-slate-400">
                        <td className="px-3 py-2" colSpan={4}>
                          {categoryName}
                        </td>
                      </tr>
                      {rows.map(({ line }, idx) => (
                        <tr
                          key={[segmentKey, categoryName, line.code, String(idx)].join('-')}
                          className="border-t border-slate-200 dark:border-slate-700"
                        >
                          <td className="px-3 py-2">
                            <div className="font-medium">{line.code}</div>
                            <div className="text-xs text-slate-500 dark:text-slate-400">{line.desc}</div>
                          </td>
                          <td className="px-3 py-2">{line.qty}</td>
                          <td className="px-3 py-2">{line.unit}</td>
                          <td className="px-3 py-2 text-right">{formatMoney(line.amount)}</td>
                        </tr>
                      ))}
                    </Fragment>
                  ))}
                  <tr className="bg-slate-100 dark:bg-slate-800 font-semibold">
                    <td className="px-3 py-2 text-right" colSpan={3}>
                      Total {info.title}
                    </td>
                    <td className="px-3 py-2 text-right">
                      {formatMoney({ amount: segmentTotal.toFixed(2), currency: info.currency } as Money)}
                    </td>
                  </tr>
                </Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};

  const handleAddPiece = () => {
    setPieces([...pieces, { weight_kg: '' }]);
  };

  const handlePieceChange = (index: number, field: keyof Piece, value: string) => {
    const updatedPieces = [...pieces];
    updatedPieces[index][field] = value;
    setPieces(updatedPieces);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoading(true);
    setError(null);
    setQuoteResult(null);

    const originCode = origin.trim().toUpperCase();
    const destCode = destination.trim().toUpperCase();

    const payload = {
      org_id: parseInt(selectedOrg, 10),
      origin_iata: originCode,
      dest_iata: destCode,
      service_scope: serviceScope,
      incoterm: incoterm,
      payment_term: paymentTerm,
      commodity_code: commodityCode,
      is_urgent: isUrgent,
      pieces: pieces.map(p => ({
        weight_kg: (p.weight_kg && p.weight_kg.trim()) || '0',
        length_cm: (p.length_cm && p.length_cm.trim()) || undefined,
        width_cm: (p.width_cm && p.width_cm.trim()) || undefined,
        height_cm: (p.height_cm && p.height_cm.trim()) || undefined,
      })),
    };

    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE;
      const token = typeof window !== 'undefined' ? localStorage.getItem('authToken') : null;
      if (!apiBase) throw new Error('API configuration error');

      const response = await fetch(`${apiBase}/quote/compute`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { 'Authorization': `Token ${token}` } : {}),
        },
        body: JSON.stringify(payload),
      });

      let data: any = null;
      try { data = await response.json(); } catch {}
      if (!response.ok) {
        const errorMsg = extractErrorMessage(data, 'Failed to compute quote');
        throw new Error(errorMsg);
      }
      setQuoteResult(data as ComputeQuoteResponse);
      await fetchQuoteDetail(data.quote_id, token);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    } finally {
      setIsLoading(false);
    }
  };

  const renderResult = () => {
    if (isLoading) return <p>Calculating...</p>;
    if (error) return <p className="text-red-500">{error}</p>;
    if (!quoteResult) return <p>Enter shipment details and click "Get Quote".</p>;

    if (quoteResult.status === QuoteStatus.PENDING_RATE) {
      return (
        <Alert>
          <AlertTitle>Manual Quote Required</AlertTitle>
          <AlertDescription>
            <p>This shipment cannot be quoted automatically. Our pricing team has been notified and will provide a quote shortly.</p>
            {quoteResult.manual_reasons?.length ? (
              <p className="font-bold mt-2">Reason: {quoteResult.manual_reasons.join(', ')}</p>
            ) : null}
          </AlertDescription>
        </Alert>
      );
    }

    const totals = quoteDetail?.totals ?? quoteResult.totals;
    const sell = totals?.sell_total ?? quoteResult.sell_total;
    const buy = totals?.buy_total;
    const tax = totals?.tax_total;
    const marginAbs = totals?.margin_abs;
    const marginPct = totals?.margin_pct;

    return (
      <div className="space-y-6">
        <div>
          <h3 className="text-2xl font-bold">
            {sell ? (
              <Fragment>Total Sell Price: {formatMoney(sell)}</Fragment>
            ) : (
              <Fragment>Quote Created: #{quoteResult.quote_id}</Fragment>
            )}
          </h3>
          {quoteDetail?.manual_reasons?.length ? (
            <p className="text-sm text-slate-500 mt-1">{quoteDetail.manual_reasons.join(', ')}</p>
          ) : null}
        </div>

        {totals && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            {buy && (
              <div className="flex justify-between border rounded-md p-2">
                <span className="text-slate-500">Buy Total (COGS)</span>
                <span className="font-medium">{formatMoney(buy)}</span>
              </div>
            )}
            {tax && (
              <div className="flex justify-between border rounded-md p-2">
                <span className="text-slate-500">Tax Total</span>
                <span className="font-medium">{formatMoney(tax)}</span>
              </div>
            )}
            {marginAbs && (
              <div className="flex justify-between border rounded-md p-2">
                <span className="text-slate-500">Margin Amount</span>
                <span className="font-medium">{formatMoney(marginAbs)}</span>
              </div>
            )}
            {marginPct && (
              <div className="flex justify-between border rounded-md p-2">
                <span className="text-slate-500">Margin %</span>
                <span className="font-medium">{formatMoney(marginPct)}</span>
              </div>
            )}
          </div>
        )}

        {quoteDetail ? (
          <Fragment>
            {renderLineTable('Buy Breakdown', quoteDetail.buy_lines)}
            {renderLineTable('Sell Breakdown', quoteDetail.sell_lines)}
          </Fragment>
        ) : null}

        <details className="border rounded-md p-3 bg-slate-50 dark:bg-slate-800 dark:border-slate-700">
          <summary className="cursor-pointer font-medium">View Raw Response</summary>
          <pre className="mt-2 text-xs overflow-auto">
            {JSON.stringify(quoteDetail ?? quoteResult, null, 2)}
          </pre>
        </details>
      </div>
    );
  };

  return (
    <div className="container mx-auto p-4">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
        <Card>
          <CardHeader><CardTitle>Create a New Quote</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <Label htmlFor="organization">Client / Organization</Label>
                <Select onValueChange={setSelectedOrg} value={selectedOrg} required>
                  <SelectTrigger id="organization" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100"><SelectValue placeholder="Select a client" /></SelectTrigger>
                  <SelectContent>
                    {organizations.map((org) => (
                      <SelectItem key={org.id} value={String(org.id)}>{org.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label htmlFor="origin">Origin</Label>
                  <Input id="origin" value={origin} onChange={(e) => setOrigin(e.target.value.toUpperCase())} maxLength={3} />
                </div>
                <div>
                  <Label htmlFor="destination">Destination</Label>
                  <Input id="destination" value={destination} onChange={(e) => setDestination(e.target.value.toUpperCase())} maxLength={3} />
                </div>
              </div>

              <div>
                <Label>Shipment Type</Label>
                <div className="mt-2 inline-flex">
                  <span className="inline-flex items-center rounded-md border border-slate-300 bg-slate-50 px-3 py-1 text-sm font-medium text-slate-700 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-100">
                    {shipmentType || 'Awaiting selection'}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Automatically detected based on route.</p>
              </div>

              <div>
                <Label>Payment Term</Label>
                <div className="mt-2 flex flex-col gap-2 sm:flex-row sm:items-center sm:gap-6">
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                    <input
                      type="radio"
                      name="paymentTerm"
                      value="PREPAID"
                      checked={paymentTerm === 'PREPAID'}
                      onChange={() => setPaymentTerm('PREPAID')}
                      required
                    />
                    <span>Prepaid (Shipper Pays)</span>
                  </label>
                  <label className="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-200">
                    <input
                      type="radio"
                      name="paymentTerm"
                      value="COLLECT"
                      checked={paymentTerm === 'COLLECT'}
                      onChange={() => setPaymentTerm('COLLECT')}
                    />
                    <span>Freight Collect (Receiver Pays)</span>
                  </label>
                </div>
              </div>
              <div>
                <Label htmlFor="commodity">Cargo Type</Label>
                <Select onValueChange={setCommodityCode} value={commodityCode}>
                    <SelectTrigger id="commodity" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100"><SelectValue placeholder="Select cargo type" /></SelectTrigger>
                    <SelectContent>
                        {commodityTypes.map((type) => (
                            <SelectItem key={type.value} value={type.value}>{type.label}</SelectItem>
                        ))}
                    </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="incoterm">Incoterms</Label>
                <Select value={incoterm} onValueChange={setIncoterm}>
                  <SelectTrigger id="incoterm" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100"><SelectValue placeholder="Select incoterm" /></SelectTrigger>
                  <SelectContent>
                    {incotermOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div>
                <Label htmlFor="serviceScope">Service Scope</Label>
                <Select value={serviceScope} onValueChange={setServiceScope}>
                  <SelectTrigger id="serviceScope" className="bg-white text-slate-900 dark:bg-slate-900 dark:text-slate-100"><SelectValue placeholder="Select service scope" /></SelectTrigger>
                  <SelectContent>
                    {serviceScopeOptions.map((option) => (
                      <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <Label>Pieces</Label>
              {pieces.map((piece, index) => (
                <div key={index} className="flex items-center gap-2 p-2 border rounded-md">
                  <Input type="number" placeholder="Weight (kg)" value={piece.weight_kg ?? ''} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} className="w-24" required />
                  <Input type="number" placeholder="L (cm)" value={piece.length_cm ?? ''} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} />
                  <Input type="number" placeholder="W (cm)" value={piece.width_cm ?? ''} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} />
                  <Input type="number" placeholder="H (cm)" value={piece.height_cm ?? ''} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} />
                </div>
              ))}
              <div className="flex justify-between items-center">
                <Button type="button" variant="outline" size="sm" onClick={handleAddPiece}>Add Piece</Button>
                <div className="flex items-center space-x-2">
                    <Checkbox id="isUrgent" checked={isUrgent} onCheckedChange={(checked) => setIsUrgent(checked as boolean)} />
                    <Label htmlFor="isUrgent">Urgent Shipment</Label>
                </div>
              </div>
              
              <Button type="submit" disabled={isLoading || !selectedOrg} className="w-full">
                {isLoading ? 'Calculating...' : 'Get Quote'}
              </Button>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Quote Result</CardTitle></CardHeader>
          <CardContent>
            {renderResult()}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}










