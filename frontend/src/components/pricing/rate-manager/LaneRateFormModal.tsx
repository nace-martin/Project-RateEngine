'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
import { useToast } from '@/context/toast-context';
import {
  getProductCodes,
  listPricingAgents,
  listPricingCarriers,
  type LaneCOGSRateRecord,
  type LaneRateRecord,
  type LaneRateUpsertPayload,
  type PricingAgentOption,
  type PricingCarrierOption,
  type ProductCodeOption,
  type RateRevisionOptions,
  type RateWeightBreak,
} from '@/lib/api';

type FormMode = 'create' | 'edit' | 'revise';
type CounterpartyType = 'agent' | 'carrier';
type PricingMode = 'PER_KG' | 'PER_SHIPMENT' | 'ADDITIVE' | 'PERCENT' | 'WEIGHT_BREAKS';

type LaneRecord = LaneRateRecord | LaneCOGSRateRecord;

type WeightBreakDraft = {
  min_kg: string;
  rate: string;
};

interface LaneRateFormModalProps<T extends LaneRecord> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: FormMode;
  initialRate?: T | null;
  title: string;
  description: string;
  productDomain: string;
  createRate: (payload: LaneRateUpsertPayload) => Promise<T>;
  updateRate: (id: number | string, payload: Partial<LaneRateUpsertPayload>) => Promise<T>;
  reviseRate: (id: number | string, payload: LaneRateUpsertPayload & RateRevisionOptions) => Promise<T>;
  routeFieldNames: {
    origin: 'origin_airport' | 'origin_zone';
    destination: 'destination_airport' | 'destination_zone';
    originLabel: string;
    destinationLabel: string;
  };
  supportsCounterparty: boolean;
  supportsPercent: boolean;
  onSuccess: () => void | Promise<void>;
}

function inferPricingMode(rate: LaneRecord | null | undefined): PricingMode {
  if (!rate) return 'PER_KG';
  if (rate.weight_breaks?.length) return 'WEIGHT_BREAKS';
  if (rate.percent_rate) return 'PERCENT';
  if (rate.is_additive && rate.rate_per_kg && rate.rate_per_shipment) return 'ADDITIVE';
  if (rate.rate_per_shipment && !rate.rate_per_kg) return 'PER_SHIPMENT';
  return 'PER_KG';
}

function initialWeightBreaks(rate: LaneRecord | null | undefined): WeightBreakDraft[] {
  if (!rate?.weight_breaks?.length) return [{ min_kg: '0', rate: '' }];
  return rate.weight_breaks.map((row) => ({
    min_kg: String(row.min_kg ?? ''),
    rate: String(row.rate ?? ''),
  }));
}

function isoDateWithOffset(offsetDays = 0): string {
  const base = new Date();
  base.setDate(base.getDate() + offsetDays);
  return base.toISOString().split('T')[0];
}

export default function LaneRateFormModal<T extends LaneRecord>({
  open,
  onOpenChange,
  mode,
  initialRate = null,
  title,
  description,
  productDomain,
  createRate,
  updateRate,
  reviseRate,
  routeFieldNames,
  supportsCounterparty,
  supportsPercent,
  onSuccess,
}: LaneRateFormModalProps<T>) {
  const { toast } = useToast();
  const isEditing = mode === 'edit' && Boolean(initialRate);
  const isRevision = mode === 'revise' && Boolean(initialRate);

  const [products, setProducts] = useState<ProductCodeOption[]>([]);
  const [agents, setAgents] = useState<PricingAgentOption[]>([]);
  const [carriers, setCarriers] = useState<PricingCarrierOption[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [productCodeId, setProductCodeId] = useState('');
  const [originCode, setOriginCode] = useState('');
  const [destinationCode, setDestinationCode] = useState('');
  const [counterpartyType, setCounterpartyType] = useState<CounterpartyType>('agent');
  const [counterpartyId, setCounterpartyId] = useState('');
  const [currency, setCurrency] = useState('PGK');
  const [pricingMode, setPricingMode] = useState<PricingMode>('PER_KG');
  const [ratePerKg, setRatePerKg] = useState('');
  const [ratePerShipment, setRatePerShipment] = useState('');
  const [percentRate, setPercentRate] = useState('');
  const [minCharge, setMinCharge] = useState('');
  const [maxCharge, setMaxCharge] = useState('');
  const [validFrom, setValidFrom] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [weightBreaks, setWeightBreaks] = useState<WeightBreakDraft[]>([{ min_kg: '0', rate: '' }]);
  const [retirePrevious, setRetirePrevious] = useState(true);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const loadOptions = async () => {
      setLoadingOptions(true);
      try {
        const tasks: Promise<unknown>[] = [getProductCodes({ domain: productDomain })];
        if (supportsCounterparty) {
          tasks.push(listPricingAgents(), listPricingCarriers());
        }
        const [productData, agentData, carrierData] = await Promise.all(tasks);
        if (cancelled) return;
        setProducts(productData as ProductCodeOption[]);
        setAgents((agentData as PricingAgentOption[] | undefined) ?? []);
        setCarriers((carrierData as PricingCarrierOption[] | undefined) ?? []);
      } catch (error) {
        if (cancelled) return;
        setFormError(error instanceof Error ? error.message : 'Failed to load form options.');
      } finally {
        if (!cancelled) {
          setLoadingOptions(false);
        }
      }
    };

    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [open, productDomain, supportsCounterparty]);

  useEffect(() => {
    if (!open) return;
    const source = initialRate;
    setFormError(null);
    setProductCodeId(source ? String(source.product_code) : '');
    setOriginCode(String(source?.[routeFieldNames.origin] ?? ''));
    setDestinationCode(String(source?.[routeFieldNames.destination] ?? ''));
    setCounterpartyType((source as LaneCOGSRateRecord | null)?.carrier ? 'carrier' : 'agent');
    setCounterpartyId(
      (source as LaneCOGSRateRecord | null)?.carrier
        ? String((source as LaneCOGSRateRecord).carrier)
        : (source as LaneCOGSRateRecord | null)?.agent
          ? String((source as LaneCOGSRateRecord).agent)
          : '',
    );
    setCurrency(source?.currency ?? 'PGK');
    setPricingMode(inferPricingMode(source));
    setRatePerKg(source?.rate_per_kg ?? '');
    setRatePerShipment(source?.rate_per_shipment ?? '');
    setPercentRate(source?.percent_rate ?? '');
    setMinCharge(source?.min_charge ?? '');
    setMaxCharge(source?.max_charge ?? '');
    setWeightBreaks(initialWeightBreaks(source));

    setRetirePrevious(true);
    if (isRevision) {
      setValidFrom(isoDateWithOffset(1));
      setValidUntil(source?.valid_until ?? isoDateWithOffset(31));
    } else {
      setValidFrom(source?.valid_from ?? isoDateWithOffset(0));
      setValidUntil(source?.valid_until ?? isoDateWithOffset(30));
    }
  }, [open, initialRate, isRevision, routeFieldNames.destination, routeFieldNames.origin]);

  const counterpartyOptions = useMemo(
    () => (counterpartyType === 'agent' ? agents : carriers),
    [agents, carriers, counterpartyType],
  );

  const addWeightBreak = () => {
    setWeightBreaks((current) => [...current, { min_kg: '', rate: '' }]);
  };

  const removeWeightBreak = (index: number) => {
    setWeightBreaks((current) =>
      current.length === 1 ? current : current.filter((_, itemIndex) => itemIndex !== index),
    );
  };

  const updateWeightBreak = (index: number, field: keyof WeightBreakDraft, value: string) => {
    setWeightBreaks((current) =>
      current.map((row, itemIndex) => (itemIndex === index ? { ...row, [field]: value } : row)),
    );
  };

  const handleSubmit = async () => {
    setFormError(null);

    if (!productCodeId || !originCode.trim() || !destinationCode.trim()) {
      setFormError('Product code and route are required.');
      return;
    }
    if (supportsCounterparty && !counterpartyId) {
      setFormError('Counterparty is required.');
      return;
    }

    const payload: LaneRateUpsertPayload = {
      product_code: Number(productCodeId),
      [routeFieldNames.origin]: originCode.trim().toUpperCase(),
      [routeFieldNames.destination]: destinationCode.trim().toUpperCase(),
      currency: currency.trim().toUpperCase(),
      agent: supportsCounterparty && counterpartyType === 'agent' ? Number(counterpartyId) : null,
      carrier: supportsCounterparty && counterpartyType === 'carrier' ? Number(counterpartyId) : null,
      rate_per_kg: null,
      rate_per_shipment: null,
      min_charge: minCharge.trim() || null,
      max_charge: maxCharge.trim() || null,
      is_additive: false,
      percent_rate: null,
      weight_breaks: null,
      valid_from: validFrom,
      valid_until: validUntil,
    };

    if (pricingMode === 'PER_KG') {
      payload.rate_per_kg = ratePerKg.trim() || null;
    } else if (pricingMode === 'PER_SHIPMENT') {
      payload.rate_per_shipment = ratePerShipment.trim() || null;
    } else if (pricingMode === 'ADDITIVE') {
      payload.rate_per_kg = ratePerKg.trim() || null;
      payload.rate_per_shipment = ratePerShipment.trim() || null;
      payload.is_additive = true;
    } else if (pricingMode === 'PERCENT') {
      payload.percent_rate = percentRate.trim() || null;
    } else if (pricingMode === 'WEIGHT_BREAKS') {
      payload.weight_breaks = weightBreaks
        .filter((row) => row.min_kg.trim() !== '' || row.rate.trim() !== '')
        .map(
          (row): RateWeightBreak => ({
            min_kg: Number(row.min_kg),
            rate: row.rate.trim(),
          }),
        );
    }

    setSaving(true);
    try {
      if (isEditing && initialRate) {
        await updateRate(initialRate.id, payload);
        toast({ title: 'Rate updated', description: 'The selected row was updated.' });
      } else if (isRevision && initialRate) {
        await reviseRate(initialRate.id, {
          ...payload,
          retire_previous: retirePrevious,
        });
        toast({
          title: 'Revision created',
          description: retirePrevious
            ? 'A new effective row was created and the prior row was shortened automatically.'
            : 'A new effective row was created.',
        });
      } else {
        await createRate(payload);
        toast({
          title: 'Rate created',
          description: 'The rate row is ready.',
        });
      }
      await onSuccess();
      onOpenChange(false);
    } catch (error) {
      setFormError(error instanceof Error ? error.message : 'Failed to save rate.');
    } finally {
      setSaving(false);
    }
  };

  const availablePricingModes: PricingMode[] = supportsPercent
    ? ['PER_KG', 'PER_SHIPMENT', 'ADDITIVE', 'PERCENT', 'WEIGHT_BREAKS']
    : ['PER_KG', 'PER_SHIPMENT', 'ADDITIVE', 'WEIGHT_BREAKS'];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {initialRate?.is_active && isRevision ? (
            <Alert>
              <AlertDescription>
                This revision is prefilled from the selected row. Save it as a new effective-dated rate instead of overwriting the current one.
              </AlertDescription>
            </Alert>
          ) : null}

          {formError ? (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Product Code</Label>
              <Select value={productCodeId} onValueChange={setProductCodeId} disabled={loadingOptions}>
                <SelectTrigger>
                  <SelectValue placeholder={loadingOptions ? 'Loading...' : 'Select product code'} />
                </SelectTrigger>
                <SelectContent className="max-h-[320px]">
                  {products.map((product) => (
                    <SelectItem key={String(product.id)} value={String(product.id)}>
                      {product.code} - {product.description}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Currency</Label>
              <Input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>{routeFieldNames.originLabel}</Label>
              <Input value={originCode} onChange={(event) => setOriginCode(event.target.value.toUpperCase())} />
            </div>
            <div className="space-y-2">
              <Label>{routeFieldNames.destinationLabel}</Label>
              <Input value={destinationCode} onChange={(event) => setDestinationCode(event.target.value.toUpperCase())} />
            </div>
          </div>

          {supportsCounterparty ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Counterparty Type</Label>
                <Select
                  value={counterpartyType}
                  onValueChange={(value) => {
                    setCounterpartyType(value as CounterpartyType);
                    setCounterpartyId('');
                  }}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="agent">Agent</SelectItem>
                    <SelectItem value="carrier">Carrier</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>{counterpartyType === 'agent' ? 'Agent' : 'Carrier'}</Label>
                <Select value={counterpartyId} onValueChange={setCounterpartyId} disabled={loadingOptions}>
                  <SelectTrigger>
                    <SelectValue placeholder={`Select ${counterpartyType}`} />
                  </SelectTrigger>
                  <SelectContent className="max-h-[300px]">
                    {counterpartyOptions.map((option) => (
                      <SelectItem key={option.id} value={String(option.id)}>
                        {option.code} - {option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : null}

          <div className="space-y-2">
            <Label>Pricing Basis</Label>
            <Select value={pricingMode} onValueChange={(value) => setPricingMode(value as PricingMode)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {availablePricingModes.map((pricingOption) => (
                  <SelectItem key={pricingOption} value={pricingOption}>
                    {pricingOption === 'PER_KG'
                      ? 'Per KG'
                      : pricingOption === 'PER_SHIPMENT'
                        ? 'Per Shipment'
                        : pricingOption === 'ADDITIVE'
                          ? 'Additive (Per KG + Shipment)'
                          : pricingOption === 'PERCENT'
                            ? 'Percent'
                            : 'Weight Breaks'}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {(pricingMode === 'PER_KG' || pricingMode === 'ADDITIVE') ? (
            <div className="space-y-2">
              <Label>Rate Per KG</Label>
              <Input value={ratePerKg} onChange={(event) => setRatePerKg(event.target.value)} placeholder="e.g. 4.2500" />
            </div>
          ) : null}

          {(pricingMode === 'PER_SHIPMENT' || pricingMode === 'ADDITIVE') ? (
            <div className="space-y-2">
              <Label>{pricingMode === 'ADDITIVE' ? 'Flat Shipment Add-On' : 'Rate Per Shipment'}</Label>
              <Input value={ratePerShipment} onChange={(event) => setRatePerShipment(event.target.value)} placeholder="e.g. 35.00" />
            </div>
          ) : null}

          {pricingMode === 'PERCENT' ? (
            <div className="space-y-2">
              <Label>Percent Rate</Label>
              <Input value={percentRate} onChange={(event) => setPercentRate(event.target.value)} placeholder="e.g. 15.00" />
            </div>
          ) : null}

          {pricingMode === 'WEIGHT_BREAKS' ? (
            <div className="space-y-3 rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Weight Breaks</div>
                  <div className="text-sm text-muted-foreground">Enter ascending `min_kg` tiers with one rate per tier.</div>
                </div>
                <Button type="button" variant="outline" size="sm" onClick={addWeightBreak}>
                  Add Tier
                </Button>
              </div>
              {weightBreaks.map((row, index) => (
                <div key={`${index}-${row.min_kg}-${row.rate}`} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                  <Input
                    value={row.min_kg}
                    onChange={(event) => updateWeightBreak(index, 'min_kg', event.target.value)}
                    placeholder="Min KG"
                  />
                  <Input
                    value={row.rate}
                    onChange={(event) => updateWeightBreak(index, 'rate', event.target.value)}
                    placeholder="Rate"
                  />
                  <Button type="button" variant="ghost" onClick={() => removeWeightBreak(index)}>
                    Remove
                  </Button>
                </div>
              ))}
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Minimum Charge</Label>
              <Input value={minCharge} onChange={(event) => setMinCharge(event.target.value)} placeholder="Optional" />
            </div>
            <div className="space-y-2">
              <Label>Maximum Charge</Label>
              <Input value={maxCharge} onChange={(event) => setMaxCharge(event.target.value)} placeholder="Optional" />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Valid From</Label>
              <Input type="date" value={validFrom} onChange={(event) => setValidFrom(event.target.value)} />
            </div>
            <div className="space-y-2">
              <Label>Valid Until</Label>
              <Input type="date" value={validUntil} onChange={(event) => setValidUntil(event.target.value)} />
            </div>
          </div>

          {isRevision ? (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
              <div className="flex items-start gap-3">
                <Checkbox
                  id="lane-retire-previous"
                  checked={retirePrevious}
                  onCheckedChange={(checked) => setRetirePrevious(Boolean(checked))}
                />
                <div className="space-y-1">
                  <Label htmlFor="lane-retire-previous">Auto-retire the prior row</Label>
                  <div className="text-sm text-muted-foreground">
                    Recommended. When enabled, the current row will end the day before the new revision starts.
                  </div>
                </div>
              </div>
            </div>
          ) : null}
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={saving || loadingOptions}>
            {saving ? 'Saving...' : isEditing ? 'Save Changes' : isRevision ? 'Create Revision' : 'Create Rate'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
