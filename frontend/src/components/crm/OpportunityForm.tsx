'use client';

import { FormEvent, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import CompanySearchCombobox from '@/components/CompanySearchCombobox';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useToast } from '@/context/toast-context';
import { createOpportunity, updateOpportunity } from '@/lib/api/crm';
import type { CompanySearchResult, Opportunity, OpportunityPayload } from '@/lib/types';

type OpportunityFormProps = {
  mode: 'create' | 'edit';
  opportunity?: Opportunity | null;
};

const serviceTypeOptions = [
  { value: 'AIR', label: 'Air' },
  { value: 'SEA', label: 'Sea' },
  { value: 'CUSTOMS', label: 'Customs' },
  { value: 'TRANSPORT', label: 'Transport' },
];
const legacyServiceTypeLabels: Record<string, string> = {
  DOMESTIC: 'Domestic',
  MULTIMODAL: 'Multimodal',
};
const statusOptions = ['NEW', 'QUALIFIED', 'QUOTED'];
const priorityOptions = ['LOW', 'MEDIUM', 'HIGH'];
const currencyOptions = ['PGK', 'AUD', 'USD', 'NZD'];

const statusHelp: Record<string, string> = {
  NEW: 'Lead identified, not yet confirmed.',
  QUALIFIED: 'Customer has a real requirement worth pursuing.',
  QUOTED: 'Quote has been issued or is being prepared.',
};

const serviceTypeHelp: Record<string, string> = {
  AIR: 'Use this for air freight opportunities. Quote scope is selected during quote creation; this form does not assume airport-to-airport.',
  SEA: 'Use this for sea freight opportunities. Capture the route, volume or FCL count, and expected frequency.',
  CUSTOMS: 'Use this for customs clearance work. Use the location fields for arrival, port, airport, or clearance location context.',
  TRANSPORT: 'Use this for pickup, delivery, and local transport work. Use origin and destination as pickup and delivery points.',
};

function stringValue(value?: string | number | null): string {
  if (value === null || value === undefined) return '';
  return String(value);
}

function nullableNumber(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function nullableInteger(value: string): number | null {
  const trimmed = value.trim();
  return trimmed ? Number.parseInt(trimmed, 10) : null;
}

export function OpportunityForm({ mode, opportunity = null }: OpportunityFormProps) {
  const router = useRouter();
  const { toast } = useToast();
  const initialCompany = useMemo<CompanySearchResult | null>(() => {
    if (!opportunity) return null;
    return {
      id: opportunity.company,
      name: opportunity.company_name || 'Selected company',
    };
  }, [opportunity]);

  const [company, setCompany] = useState<CompanySearchResult | null>(initialCompany);
  const [title, setTitle] = useState(opportunity?.title || '');
  const [serviceType, setServiceType] = useState(opportunity?.service_type || 'AIR');
  const [origin, setOrigin] = useState(opportunity?.origin || '');
  const [destination, setDestination] = useState(opportunity?.destination || '');
  const [status, setStatus] = useState(opportunity?.status || 'NEW');
  const [priority, setPriority] = useState(opportunity?.priority || 'MEDIUM');
  const [estimatedWeightKg, setEstimatedWeightKg] = useState(stringValue(opportunity?.estimated_weight_kg));
  const [estimatedVolumeCbm, setEstimatedVolumeCbm] = useState(stringValue(opportunity?.estimated_volume_cbm));
  const [estimatedFclCount, setEstimatedFclCount] = useState(stringValue(opportunity?.estimated_fcl_count));
  const [estimatedFrequency, setEstimatedFrequency] = useState(opportunity?.estimated_frequency || '');
  const [estimatedRevenue, setEstimatedRevenue] = useState(stringValue(opportunity?.estimated_revenue));
  const [estimatedCurrency, setEstimatedCurrency] = useState(opportunity?.estimated_currency || 'PGK');
  const [nextAction, setNextAction] = useState(opportunity?.next_action || '');
  const [nextActionDate, setNextActionDate] = useState(opportunity?.next_action_date || '');
  const [saving, setSaving] = useState(false);
  const normalizedServiceType = serviceType.toUpperCase();
  const isAir = normalizedServiceType === 'AIR';
  const isSea = normalizedServiceType === 'SEA';
  const isCustoms = normalizedServiceType === 'CUSTOMS';
  const isTransport = normalizedServiceType === 'TRANSPORT';
  const isLegacyServiceType = Boolean(legacyServiceTypeLabels[normalizedServiceType]);
  const serviceTypeSelectOptions = useMemo(() => {
    if (!isLegacyServiceType) return serviceTypeOptions;
    return [
      ...serviceTypeOptions,
      {
        value: normalizedServiceType,
        label: `Legacy: ${legacyServiceTypeLabels[normalizedServiceType]}`,
      },
    ];
  }, [isLegacyServiceType, normalizedServiceType]);
  const originLabel = isTransport
    ? 'Pickup / Origin'
    : isCustoms
      ? 'Arrival / Clearance Location'
      : 'Origin';
  const destinationLabel = isTransport
    ? 'Delivery / Destination'
    : isCustoms
      ? 'Delivery / Final Location'
      : 'Destination';
  const originHelper = isTransport
    ? 'Pickup address, town, depot, or origin point.'
    : isCustoms
      ? 'Port, airport, bond store, or arrival location.'
      : 'Airport, port, city, or lane origin.';
  const destinationHelper = isTransport
    ? 'Delivery address, town, depot, or destination point.'
    : isCustoms
      ? 'Delivery point, consignee location, or clearance destination.'
      : 'Airport, port, city, or lane destination.';
  const showEstimatedWeight = isAir;
  const showEstimatedVolume = isAir || isSea;
  const showEstimatedFcl = isSea;
  const nextActionHelper = isCustoms
    ? 'Use this for missing documents, clearance follow-up, or customer confirmation.'
    : isTransport
      ? 'Use this for pickup/delivery confirmation or transport follow-up.'
      : 'Use this for the next sales or quoting follow-up.';

  const validate = () => {
    if (!company) return 'Company is required.';
    if (!title.trim()) return 'Opportunity name is required.';
    if (!serviceType) return 'Service type is required.';
    if (!origin.trim()) return 'Origin is required.';
    if (!destination.trim()) return 'Destination is required.';
    if (!status) return 'Status is required.';
    if (!priority) return 'Priority is required.';
    if (estimatedFclCount.trim() && Number.isNaN(Number.parseInt(estimatedFclCount.trim(), 10))) {
      return 'Estimated FCL count must be a whole number.';
    }
    return null;
  };

  const buildPayload = (): OpportunityPayload => ({
    company: company?.id || '',
    title: title.trim(),
    service_type: serviceType,
    origin: origin.trim(),
    destination: destination.trim(),
    status,
    priority,
    estimated_weight_kg: nullableNumber(estimatedWeightKg),
    estimated_volume_cbm: nullableNumber(estimatedVolumeCbm),
    estimated_fcl_count: nullableInteger(estimatedFclCount),
    estimated_frequency: estimatedFrequency.trim(),
    estimated_revenue: nullableNumber(estimatedRevenue),
    estimated_currency: estimatedCurrency.trim().toUpperCase(),
    next_action: nextAction.trim(),
    next_action_date: nextActionDate || null,
  });

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (saving) return;

    const validationError = validate();
    if (validationError) {
      toast({
        title: 'Check required fields',
        description: validationError,
        variant: 'destructive',
      });
      return;
    }

    setSaving(true);
    try {
      const payload = buildPayload();
      const saved = mode === 'create'
        ? await createOpportunity(payload)
        : await updateOpportunity(opportunity?.id || '', payload);

      toast({
        title: mode === 'create' ? 'Opportunity created' : 'Opportunity updated',
        description: saved.title,
        variant: 'success',
      });
      router.push(`/crm/opportunities/${saved.id}`);
    } catch (error) {
      toast({
        title: mode === 'create' ? 'Could not create opportunity' : 'Could not update opportunity',
        description: error instanceof Error ? error.message : 'The opportunity was not saved.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="pb-2">
        <CardTitle className="text-lg">{mode === 'create' ? 'New Opportunity' : 'Edit Opportunity'}</CardTitle>
      </CardHeader>
      <CardContent className="px-6 pb-6 pt-2">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <CompanySearchCombobox
              label="Company"
              name="opportunity-company"
              value={company}
              onSelect={setCompany}
              placeholder="Search customers"
              disabled={saving}
            />
            <div className="space-y-2">
              <Label htmlFor="opportunity-title">Opportunity Name</Label>
              <Input
                id="opportunity-title"
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                disabled={saving}
                required
              />
              <p className="text-xs text-muted-foreground">
                Short name for this opportunity, e.g. Weekly BNE-POM Air Freight or Customs + Delivery for Medical Supplies.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-service-type">Service Type</Label>
              <select
                id="opportunity-service-type"
                value={serviceType}
                onChange={(event) => setServiceType(event.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {serviceTypeSelectOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                {serviceTypeHelp[normalizedServiceType] ||
                  'Legacy service type retained for this existing record. Change it only if the opportunity should move to a current service type.'}
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-status">Status</Label>
              <select
                id="opportunity-status"
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {statusOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{statusHelp[status]}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-origin">{originLabel}</Label>
              <Input
                id="opportunity-origin"
                value={origin}
                onChange={(event) => setOrigin(event.target.value)}
                disabled={saving}
                required
              />
              <p className="text-xs text-muted-foreground">{originHelper}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-destination">{destinationLabel}</Label>
              <Input
                id="opportunity-destination"
                value={destination}
                onChange={(event) => setDestination(event.target.value)}
                disabled={saving}
                required
              />
              <p className="text-xs text-muted-foreground">{destinationHelper}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-priority">Priority</Label>
              <select
                id="opportunity-priority"
                value={priority}
                onChange={(event) => setPriority(event.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {priorityOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-frequency">Estimated Frequency</Label>
              <Input
                id="opportunity-frequency"
                value={estimatedFrequency}
                onChange={(event) => setEstimatedFrequency(event.target.value)}
                disabled={saving}
                placeholder="Weekly"
              />
            </div>
            {showEstimatedWeight ? (
              <div className="space-y-2">
                <Label htmlFor="opportunity-weight">Estimated Weight KG</Label>
                <Input
                  id="opportunity-weight"
                  type="number"
                  min="0"
                  step="0.001"
                  value={estimatedWeightKg}
                  onChange={(event) => setEstimatedWeightKg(event.target.value)}
                  disabled={saving}
                />
                <p className="text-xs text-muted-foreground">Useful for early air freight sizing. Leave blank if unknown.</p>
              </div>
            ) : null}
            {showEstimatedVolume ? (
              <div className="space-y-2">
                <Label htmlFor="opportunity-volume">Estimated Volume CBM</Label>
                <Input
                  id="opportunity-volume"
                  type="number"
                  min="0"
                  step="0.001"
                  value={estimatedVolumeCbm}
                  onChange={(event) => setEstimatedVolumeCbm(event.target.value)}
                  disabled={saving}
                />
                <p className="text-xs text-muted-foreground">
                  {isSea ? 'Useful for LCL or loose cargo estimates.' : 'Optional estimate for bulky air cargo.'}
                </p>
              </div>
            ) : null}
            {showEstimatedFcl ? (
              <div className="space-y-2">
                <Label htmlFor="opportunity-fcl">Estimated FCL Count</Label>
                <Input
                  id="opportunity-fcl"
                  type="number"
                  min="0"
                  step="1"
                  value={estimatedFclCount}
                  onChange={(event) => setEstimatedFclCount(event.target.value)}
                  disabled={saving}
                />
                <p className="text-xs text-muted-foreground">Optional full-container estimate for sea opportunities.</p>
              </div>
            ) : null}
            <div className="space-y-2">
              <Label htmlFor="opportunity-revenue">Estimated Revenue</Label>
              <Input
                id="opportunity-revenue"
                type="number"
                min="0"
                step="0.01"
                value={estimatedRevenue}
                onChange={(event) => setEstimatedRevenue(event.target.value)}
                disabled={saving}
              />
              <p className="text-xs text-muted-foreground">Optional estimate only. Leave blank if unknown before quoting.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-currency">Estimated Currency</Label>
              <select
                id="opportunity-currency"
                value={estimatedCurrency}
                onChange={(event) => setEstimatedCurrency(event.target.value)}
                disabled={saving}
                className="h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {currencyOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">Optional. Final quote currency will be confirmed during quoting.</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="opportunity-next-action-date">Next Action Date</Label>
              <Input
                id="opportunity-next-action-date"
                type="date"
                value={nextActionDate}
                onChange={(event) => setNextActionDate(event.target.value)}
                disabled={saving}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="opportunity-next-action">Next Action</Label>
            <Textarea
              id="opportunity-next-action"
              value={nextAction}
              onChange={(event) => setNextAction(event.target.value)}
              disabled={saving}
              className="min-h-24"
            />
            <p className="text-xs text-muted-foreground">{nextActionHelper}</p>
          </div>

          <div className="flex flex-wrap justify-end gap-2 border-t pt-4">
            <Button type="button" variant="outline" onClick={() => router.back()} disabled={saving}>
              Cancel
            </Button>
            <Button type="submit" loading={saving} loadingText="Saving" disabled={saving}>
              {mode === 'create' ? 'Create Opportunity' : 'Save Changes'}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
