'use client';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

type RateWeightBreakDraft = {
  min_kg: string;
  rate: string;
};

export function RateFormRevisionNotice() {
  return (
    <Alert>
      <AlertDescription>
        This revision is prefilled from the selected row. Save it as a new effective-dated rate instead of overwriting the current one.
      </AlertDescription>
    </Alert>
  );
}

export function RateRetirePreviousOption({
  id,
  checked,
  onCheckedChange,
}: {
  id: string;
  checked: boolean;
  onCheckedChange: (checked: boolean | 'indeterminate') => void;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
      <div className="flex items-start gap-3">
        <Checkbox id={id} checked={checked} onCheckedChange={onCheckedChange} />
        <div className="space-y-1">
          <Label htmlFor={id}>Auto-retire the prior row</Label>
          <div className="text-sm text-muted-foreground">
            Recommended. When enabled, the current row will end the day before the new revision starts.
          </div>
        </div>
      </div>
    </div>
  );
}

export function RateValidityFields({
  validFrom,
  validUntil,
  onValidFromChange,
  onValidUntilChange,
}: {
  validFrom: string;
  validUntil: string;
  onValidFromChange: (value: string) => void;
  onValidUntilChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label>Valid From</Label>
        <Input type="date" value={validFrom} onChange={(event) => onValidFromChange(event.target.value)} />
      </div>
      <div className="space-y-2">
        <Label>Valid Until</Label>
        <Input type="date" value={validUntil} onChange={(event) => onValidUntilChange(event.target.value)} />
      </div>
    </div>
  );
}

export function RateChargeBoundsFields({
  minCharge,
  maxCharge,
  onMinChargeChange,
  onMaxChargeChange,
}: {
  minCharge: string;
  maxCharge: string;
  onMinChargeChange: (value: string) => void;
  onMaxChargeChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <div className="space-y-2">
        <Label>Minimum Charge</Label>
        <Input value={minCharge} onChange={(event) => onMinChargeChange(event.target.value)} placeholder="Optional" />
      </div>
      <div className="space-y-2">
        <Label>Maximum Charge</Label>
        <Input value={maxCharge} onChange={(event) => onMaxChargeChange(event.target.value)} placeholder="Optional" />
      </div>
    </div>
  );
}

export function RateWeightBreakEditor({
  weightBreaks,
  helperText,
  onAddWeightBreak,
  onUpdateWeightBreak,
  onRemoveWeightBreak,
}: {
  weightBreaks: RateWeightBreakDraft[];
  helperText: string;
  onAddWeightBreak: () => void;
  onUpdateWeightBreak: (index: number, field: keyof RateWeightBreakDraft, value: string) => void;
  onRemoveWeightBreak: (index: number) => void;
}) {
  return (
    <div className="space-y-3 rounded-lg border p-4">
      <div className="flex items-center justify-between">
        <div>
          <div className="font-medium">Weight Breaks</div>
          <div className="text-sm text-muted-foreground">{helperText}</div>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={onAddWeightBreak}>
          Add Tier
        </Button>
      </div>
      {weightBreaks.map((row, index) => (
        <div key={`${index}-${row.min_kg}-${row.rate}`} className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
          <Input
            value={row.min_kg}
            onChange={(event) => onUpdateWeightBreak(index, 'min_kg', event.target.value)}
            placeholder="Min KG"
          />
          <Input
            value={row.rate}
            onChange={(event) => onUpdateWeightBreak(index, 'rate', event.target.value)}
            placeholder="Rate"
          />
          <Button type="button" variant="ghost" onClick={() => onRemoveWeightBreak(index)}>
            Remove
          </Button>
        </div>
      ))}
    </div>
  );
}

export function RateFormFooter({
  saving,
  loadingOptions,
  submitLabel,
  onCancel,
  onSubmit,
}: {
  saving: boolean;
  loadingOptions: boolean;
  submitLabel: string;
  onCancel: () => void;
  onSubmit: () => void;
}) {
  return (
    <DialogFooter>
      <Button type="button" variant="outline" onClick={onCancel} disabled={saving}>
        Cancel
      </Button>
      <Button type="button" onClick={onSubmit} disabled={saving || loadingOptions}>
        {submitLabel}
      </Button>
    </DialogFooter>
  );
}
