'use client';

import { useEffect, useState } from 'react';
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
  type LocalCOGSRateRecord,
  type LocalRateRecord,
  type LocalRateUpsertPayload,
  type PricingAgentOption,
  type PricingCarrierOption,
  type ProductCodeOption,
  type RateRevisionOptions,
  type RateWeightBreak,
} from '@/lib/api';

type FormMode = 'create' | 'edit' | 'revise';
type CounterpartyType = 'agent' | 'carrier';

type WeightBreakDraft = {
  min_kg: string;
  rate: string;
};

interface LocalRateFormModalProps<T extends LocalRateRecord | LocalCOGSRateRecord> {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  mode: FormMode;
  initialRate?: T | null;
  title: string;
  description: string;
  productDomains: string[];
  supportsPaymentTerm: boolean;
  supportsCounterparty: boolean;
  createRate: (payload: LocalRateUpsertPayload) => Promise<T>;
  updateRate: (id: number | string, payload: Partial<LocalRateUpsertPayload>) => Promise<T>;
  reviseRate: (id: number | string, payload: LocalRateUpsertPayload & RateRevisionOptions) => Promise<T>;
  onSuccess: () => void | Promise<void>;
}

function isoDateWithOffset(offsetDays = 0): string {
  const base = new Date();
  base.setDate(base.getDate() + offsetDays);
  return base.toISOString().split('T')[0];
}

function initialWeightBreaks(rate: LocalRateRecord | null | undefined): WeightBreakDraft[] {
  if (!rate?.weight_breaks?.length) return [{ min_kg: '0', rate: '' }];
  return rate.weight_breaks.map((row) => ({
    min_kg: String(row.min_kg ?? ''),
    rate: String(row.rate ?? ''),
  }));
}

export default function LocalRateFormModal<T extends LocalRateRecord | LocalCOGSRateRecord>({
  open,
  onOpenChange,
  mode,
  initialRate = null,
  title,
  description,
  productDomains,
  supportsPaymentTerm,
  supportsCounterparty,
  createRate,
  updateRate,
  reviseRate,
  onSuccess,
}: LocalRateFormModalProps<T>) {
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
  const [location, setLocation] = useState('');
  const [direction, setDirection] = useState<'EXPORT' | 'IMPORT'>('EXPORT');
  const [paymentTerm, setPaymentTerm] = useState<'PREPAID' | 'COLLECT' | 'ANY'>('ANY');
  const [currency, setCurrency] = useState('PGK');
  const [rateType, setRateType] = useState<'FIXED' | 'PER_KG' | 'PERCENT'>('FIXED');
  const [amount, setAmount] = useState('');
  const [isAdditive, setIsAdditive] = useState(false);
  const [additiveFlatAmount, setAdditiveFlatAmount] = useState('');
  const [minCharge, setMinCharge] = useState('');
  const [maxCharge, setMaxCharge] = useState('');
  const [weightBreaks, setWeightBreaks] = useState<WeightBreakDraft[]>([{ min_kg: '0', rate: '' }]);
  const [percentOfProductCode, setPercentOfProductCode] = useState('');
  const [counterpartyType, setCounterpartyType] = useState<CounterpartyType>('agent');
  const [counterpartyId, setCounterpartyId] = useState('');
  const [validFrom, setValidFrom] = useState('');
  const [validUntil, setValidUntil] = useState('');
  const [retirePrevious, setRetirePrevious] = useState(true);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;

    const loadOptions = async () => {
      setLoadingOptions(true);
      try {
        const productTasks = productDomains.map((domain) => getProductCodes({ domain }));
        const tasks: Promise<unknown>[] = [Promise.all(productTasks)];
        if (supportsCounterparty) {
          tasks.push(listPricingAgents(), listPricingCarriers());
        }
        const [productData, agentData, carrierData] = await Promise.all(tasks);
        if (cancelled) return;
        setProducts((productData as ProductCodeOption[][]).flat());
        setAgents((agentData as PricingAgentOption[] | undefined) ?? []);
        setCarriers((carrierData as PricingCarrierOption[] | undefined) ?? []);
      } catch (error) {
        if (cancelled) return;
        setFormError(error instanceof Error ? error.message : 'Failed to load form options.');
      } finally {
        if (!cancelled) setLoadingOptions(false);
      }
    };

    void loadOptions();
    return () => {
      cancelled = true;
    };
  }, [open, productDomains, supportsCounterparty]);

  useEffect(() => {
    if (!open) return;
    const source = initialRate;
    setFormError(null);
    setProductCodeId(source ? String(source.product_code) : '');
    setLocation(source?.location ?? '');
    setDirection(source?.direction ?? 'EXPORT');
    setPaymentTerm(source?.payment_term ?? 'ANY');
    setCurrency(source?.currency ?? 'PGK');
    setRateType(source?.rate_type ?? 'FIXED');
    setAmount(source?.amount ?? '');
    setIsAdditive(source?.is_additive ?? false);
    setAdditiveFlatAmount(source?.additive_flat_amount ?? '');
    setMinCharge(source?.min_charge ?? '');
    setMaxCharge(source?.max_charge ?? '');
    setWeightBreaks(initialWeightBreaks(source));
    setPercentOfProductCode(source?.percent_of_product_code ? String(source.percent_of_product_code) : '');
    setCounterpartyType((source as LocalCOGSRateRecord | null)?.carrier ? 'carrier' : 'agent');
    setCounterpartyId(
      (source as LocalCOGSRateRecord | null)?.carrier
        ? String((source as LocalCOGSRateRecord).carrier)
        : (source as LocalCOGSRateRecord | null)?.agent
          ? String((source as LocalCOGSRateRecord).agent)
          : '',
    );
    setRetirePrevious(true);
    if (isRevision) {
      setValidFrom(isoDateWithOffset(1));
      setValidUntil(source?.valid_until ?? isoDateWithOffset(31));
    } else {
      setValidFrom(source?.valid_from ?? isoDateWithOffset(0));
      setValidUntil(source?.valid_until ?? isoDateWithOffset(30));
    }
  }, [open, initialRate, isRevision]);

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

    if (!productCodeId || !location.trim()) {
      setFormError('Product code and location are required.');
      return;
    }
    if (supportsCounterparty && !counterpartyId) {
      setFormError('Counterparty is required.');
      return;
    }
    if (rateType === 'PERCENT' && !percentOfProductCode) {
      setFormError('Select the base product code for percent rates.');
      return;
    }

    const payload: LocalRateUpsertPayload = {
      product_code: Number(productCodeId),
      location: location.trim().toUpperCase(),
      direction,
      payment_term: supportsPaymentTerm ? paymentTerm : undefined,
      agent: supportsCounterparty && counterpartyType === 'agent' ? Number(counterpartyId) : null,
      carrier: supportsCounterparty && counterpartyType === 'carrier' ? Number(counterpartyId) : null,
      currency: currency.trim().toUpperCase(),
      rate_type: rateType,
      amount: amount.trim(),
      is_additive: isAdditive,
      additive_flat_amount: additiveFlatAmount.trim() || null,
      min_charge: minCharge.trim() || null,
      max_charge: maxCharge.trim() || null,
      weight_breaks: weightBreaks
        .filter((row) => row.min_kg.trim() !== '' || row.rate.trim() !== '')
        .map(
          (row): RateWeightBreak => ({
            min_kg: Number(row.min_kg),
            rate: row.rate.trim(),
          }),
        ),
      percent_of_product_code: percentOfProductCode ? Number(percentOfProductCode) : null,
      valid_from: validFrom,
      valid_until: validUntil,
    };

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

  const productOptions = products.filter((product) => product.category !== 'FREIGHT');

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
                  <SelectValue placeholder="Select product code" />
                </SelectTrigger>
                <SelectContent className="max-h-[320px]">
                  {productOptions.map((product) => (
                    <SelectItem key={String(product.id)} value={String(product.id)}>
                      {product.code} - {product.description}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Location</Label>
              <Input value={location} onChange={(event) => setLocation(event.target.value.toUpperCase())} />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label>Direction</Label>
              <Select value={direction} onValueChange={(value) => setDirection(value as 'EXPORT' | 'IMPORT')}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="EXPORT">Export</SelectItem>
                  <SelectItem value="IMPORT">Import</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {supportsPaymentTerm ? (
              <div className="space-y-2">
                <Label>Payment Term</Label>
                <Select value={paymentTerm} onValueChange={(value) => setPaymentTerm(value as 'PREPAID' | 'COLLECT' | 'ANY')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="ANY">Any</SelectItem>
                    <SelectItem value="PREPAID">Prepaid</SelectItem>
                    <SelectItem value="COLLECT">Collect</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            ) : null}

            <div className="space-y-2">
              <Label>Currency</Label>
              <Input value={currency} onChange={(event) => setCurrency(event.target.value.toUpperCase())} maxLength={3} />
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
                    {(counterpartyType === 'agent' ? agents : carriers).map((option) => (
                      <SelectItem key={option.id} value={String(option.id)}>
                        {option.code} - {option.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : null}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label>Rate Type</Label>
              <Select value={rateType} onValueChange={(value) => setRateType(value as 'FIXED' | 'PER_KG' | 'PERCENT')}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="FIXED">Fixed Per Shipment</SelectItem>
                  <SelectItem value="PER_KG">Per KG</SelectItem>
                  <SelectItem value="PERCENT">Percent</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <Label>Amount</Label>
              <Input value={amount} onChange={(event) => setAmount(event.target.value)} placeholder="e.g. 25.0000" />
            </div>
          </div>

          {rateType === 'PER_KG' ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label>Is Additive</Label>
                <Select value={isAdditive ? 'yes' : 'no'} onValueChange={(value) => setIsAdditive(value === 'yes')}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="no">No</SelectItem>
                    <SelectItem value="yes">Yes</SelectItem>
                  </SelectContent>
                </Select>
              </div>

              {isAdditive ? (
                <div className="space-y-2">
                  <Label>Additive Flat Amount</Label>
                  <Input value={additiveFlatAmount} onChange={(event) => setAdditiveFlatAmount(event.target.value)} />
                </div>
              ) : null}
            </div>
          ) : null}

          {rateType === 'PERCENT' ? (
            <div className="space-y-2">
              <Label>Percent Of Product Code</Label>
              <Select value={percentOfProductCode} onValueChange={setPercentOfProductCode} disabled={loadingOptions}>
                <SelectTrigger>
                  <SelectValue placeholder="Select base product code" />
                </SelectTrigger>
                <SelectContent className="max-h-[300px]">
                  {productOptions.map((product) => (
                    <SelectItem key={String(product.id)} value={String(product.id)}>
                      {product.code} - {product.description}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          ) : null}

          {rateType === 'PER_KG' ? (
            <div className="space-y-3 rounded-lg border p-4">
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-medium">Weight Breaks</div>
                  <div className="text-sm text-muted-foreground">Optional. Leave blank if this row is not tiered.</div>
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
                  id="local-retire-previous"
                  checked={retirePrevious}
                  onCheckedChange={(checked) => setRetirePrevious(Boolean(checked))}
                />
                <div className="space-y-1">
                  <Label htmlFor="local-retire-previous">Auto-retire the prior row</Label>
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
