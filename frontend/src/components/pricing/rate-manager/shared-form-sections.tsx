'use client';

import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

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
