'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useToast } from '@/context/toast-context';
import {
  bulkUpsertCustomerDiscounts,
  CustomerDiscountBulkLine,
  DiscountType,
  getProductCodes,
  ProductCodeOption,
} from '@/lib/api';

interface BulkDiscountFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: {
    id: string;
    name: string;
  };
  onSuccess: () => void | Promise<void>;
}

const DISCOUNT_TYPES: { value: DiscountType; label: string }[] = [
  { value: 'PERCENTAGE', label: 'Percentage' },
  { value: 'FLAT_AMOUNT', label: 'Flat Amount' },
  { value: 'FIXED_CHARGE', label: 'Fixed Charge' },
  { value: 'RATE_REDUCTION', label: 'Rate Reduction' },
  { value: 'MARGIN_OVERRIDE', label: 'Margin Override' },
];

type DraftLine = CustomerDiscountBulkLine & {
  localId: string;
};

function buildEmptyLine(index: number): DraftLine {
  return {
    localId: `new-${index}`,
    product_code: '',
    discount_type: 'PERCENTAGE',
    discount_value: '',
    currency: 'PGK',
    min_charge: '',
    max_charge: '',
    valid_from: '',
    valid_until: '',
    notes: '',
  };
}

export default function BulkDiscountFormModal({
  open,
  onOpenChange,
  customer,
  onSuccess,
}: BulkDiscountFormModalProps) {
  const { toast } = useToast();
  const [rows, setRows] = useState<DraftLine[]>([buildEmptyLine(1), buildEmptyLine(2), buildEmptyLine(3)]);
  const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const loadProducts = async () => {
      try {
        setLoadingProducts(true);
        const data = await getProductCodes();
        if (!cancelled) {
          setProductCodes(data);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) {
          toast({ title: 'Error', description: 'Failed to load product codes', variant: 'destructive' });
        }
      } finally {
        if (!cancelled) {
          setLoadingProducts(false);
        }
      }
    };
    loadProducts();
    return () => {
      cancelled = true;
    };
  }, [open, toast]);

  useEffect(() => {
    if (open) {
      setRows([buildEmptyLine(1), buildEmptyLine(2), buildEmptyLine(3)]);
    }
  }, [open]);

  const groupedProductCodes = useMemo(() => {
    return productCodes.reduce((acc, pc) => {
      const key = pc.domain || 'OTHER';
      if (!acc[key]) acc[key] = [];
      acc[key].push(pc);
      return acc;
    }, {} as Record<string, ProductCodeOption[]>);
  }, [productCodes]);

  const updateRow = (localId: string, field: keyof DraftLine, value: string) => {
    setRows((prev) =>
      prev.map((row) =>
        row.localId === localId
          ? {
              ...row,
              [field]: value,
            }
          : row,
      ),
    );
  };

  const addRow = () => {
    setRows((prev) => [...prev, buildEmptyLine(prev.length + 1)]);
  };

  const removeRow = (localId: string) => {
    setRows((prev) => (prev.length <= 1 ? prev : prev.filter((row) => row.localId !== localId)));
  };

  const handleSubmit = async () => {
    const lines = rows.filter((row) => row.product_code && row.discount_value);
    if (lines.length === 0) {
      toast({ title: 'Error', description: 'Add at least one negotiated line item.', variant: 'destructive' });
      return;
    }

    setSaving(true);
    try {
      await bulkUpsertCustomerDiscounts({
        customer: customer.id,
        lines: lines.map((row) => ({
          product_code: row.product_code,
          discount_type: row.discount_type,
          discount_value: row.discount_value,
          currency: row.currency,
          min_charge: row.min_charge || null,
          max_charge: row.max_charge || null,
          valid_from: row.valid_from || null,
          valid_until: row.valid_until || null,
          notes: row.notes || '',
        })),
      });
      toast({ title: 'Success', description: 'Negotiated pricing saved successfully.' });
      await onSuccess();
      onOpenChange(false);
    } catch (err) {
      toast({
        title: 'Error',
        description: err instanceof Error ? err.message : 'Failed to save negotiated pricing.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-5xl max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Bulk Add Negotiated Pricing</DialogTitle>
          <DialogDescription>
            Add multiple negotiated line-item adjustments for {customer.name} in one save.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {rows.map((row, index) => (
            <Card key={row.localId} className="border-slate-200">
              <CardHeader className="pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Line {index + 1}</CardTitle>
                  <Button type="button" variant="outline" size="sm" onClick={() => removeRow(row.localId)}>
                    Remove
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label>Product Code</Label>
                    <Select value={row.product_code} onValueChange={(value) => updateRow(row.localId, 'product_code', value)}>
                      <SelectTrigger>
                        <SelectValue placeholder={loadingProducts ? 'Loading...' : 'Select product code'} />
                      </SelectTrigger>
                      <SelectContent className="max-h-[300px]">
                        {Object.entries(groupedProductCodes).map(([domain, codes]) => (
                          <div key={domain}>
                            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground bg-muted sticky top-0">
                              {domain}
                            </div>
                            {codes.map((pc) => (
                              <SelectItem key={String(pc.id)} value={String(pc.id)}>
                                <span className="font-mono text-sm">{pc.code}</span>
                                <span className="text-muted-foreground ml-2">- {pc.description}</span>
                              </SelectItem>
                            ))}
                          </div>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Discount Type</Label>
                    <Select
                      value={row.discount_type}
                      onValueChange={(value) => updateRow(row.localId, 'discount_type', value)}
                    >
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {DISCOUNT_TYPES.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label>Value</Label>
                    <Input
                      type="number"
                      step="0.01"
                      value={row.discount_value}
                      onChange={(e) => updateRow(row.localId, 'discount_value', e.target.value)}
                      placeholder="e.g. 10"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Currency</Label>
                    <Select value={row.currency} onValueChange={(value) => updateRow(row.localId, 'currency', value)}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="PGK">PGK</SelectItem>
                        <SelectItem value="AUD">AUD</SelectItem>
                        <SelectItem value="USD">USD</SelectItem>
                        <SelectItem value="SGD">SGD</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>

                  {row.discount_type === 'RATE_REDUCTION' && (
                    <>
                      <div className="space-y-2">
                        <Label>Minimum Charge</Label>
                        <Input
                          type="number"
                          step="0.01"
                          value={row.min_charge || ''}
                          onChange={(e) => updateRow(row.localId, 'min_charge', e.target.value)}
                          placeholder="Optional"
                        />
                      </div>
                      <div className="space-y-2">
                        <Label>Maximum Charge</Label>
                        <Input
                          type="number"
                          step="0.01"
                          value={row.max_charge || ''}
                          onChange={(e) => updateRow(row.localId, 'max_charge', e.target.value)}
                          placeholder="Optional"
                        />
                      </div>
                    </>
                  )}

                  <div className="space-y-2">
                    <Label>Valid From</Label>
                    <Input
                      type="date"
                      value={row.valid_from || ''}
                      onChange={(e) => updateRow(row.localId, 'valid_from', e.target.value)}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label>Valid Until</Label>
                    <Input
                      type="date"
                      value={row.valid_until || ''}
                      onChange={(e) => updateRow(row.localId, 'valid_until', e.target.value)}
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Notes</Label>
                  <Textarea
                    rows={2}
                    value={row.notes || ''}
                    onChange={(e) => updateRow(row.localId, 'notes', e.target.value)}
                    placeholder="Optional internal notes"
                  />
                </div>
              </CardContent>
            </Card>
          ))}

          <Button type="button" variant="outline" onClick={addRow}>
            Add Another Line
          </Button>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={saving}>
            {saving ? 'Saving...' : 'Save Negotiated Pricing'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
