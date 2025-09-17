'use client';

import { useState, useEffect } from 'react';
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
];


export default function NewQuotePage() {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrg, setSelectedOrg] = useState('');
  const [origin, setOrigin] = useState('BNE');
  const [destination, setDestination] = useState('LAE');
  const [commodityCode, setCommodityCode] = useState('GCR');
  const [serviceScope, setServiceScope] = useState('AIRPORT_AIRPORT');
  const [incoterm, setIncoterm] = useState('DAP');
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
              {filtered.map((line, idx) => (
                <tr key={`${line.code}-${idx}`} className="border-t border-slate-200 dark:border-slate-700">
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

    const payload = {
      org_id: parseInt(selectedOrg, 10),
      origin_iata: origin,
      dest_iata: destination,
      shipment_type: "IMPORT",
      service_scope: serviceScope,
      incoterm: incoterm,
      commodity_code: commodityCode,
      is_urgent: isUrgent,
      pieces: pieces.map(p => ({
        ...p,
        weight_kg: parseFloat(p.weight_kg) || 0,
        length_cm: parseFloat(p.length_cm || '0') || undefined,
        width_cm: parseFloat(p.width_cm || '0') || undefined,
        height_cm: parseFloat(p.height_cm || '0') || undefined,
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
              <>Total Sell Price: {formatMoney(sell)}</>
            ) : (
              <>Quote Created: #{quoteResult.quote_id}</>
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
          <>
            {renderLineTable('Buy Breakdown', quoteDetail.buy_lines)}
            {renderLineTable('Sell Breakdown', quoteDetail.sell_lines)}
          </>
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









