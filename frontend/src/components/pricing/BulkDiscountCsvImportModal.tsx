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
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { useToast } from '@/context/toast-context';
import {
  bulkUpsertCustomerDiscounts,
  CustomerDiscountBulkLine,
  getProductCodes,
  ProductCodeOption,
} from '@/lib/api';
import { DISCOUNT_CSV_TEMPLATE, downloadDiscountCsvTemplate } from '@/components/pricing/discount-csv-template';

interface BulkDiscountCsvImportModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  customer: {
    id: string;
    name: string;
  };
  onSuccess: () => void | Promise<void>;
}

function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let current = '';
  let row: string[] = [];
  let inQuotes = false;

  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    const next = text[i + 1];

    if (char === '"') {
      if (inQuotes && next === '"') {
        current += '"';
        i += 1;
      } else {
        inQuotes = !inQuotes;
      }
      continue;
    }

    if (char === ',' && !inQuotes) {
      row.push(current.trim());
      current = '';
      continue;
    }

    if ((char === '\n' || char === '\r') && !inQuotes) {
      if (char === '\r' && next === '\n') {
        i += 1;
      }
      row.push(current.trim());
      current = '';
      if (row.some((cell) => cell.length > 0)) {
        rows.push(row);
      }
      row = [];
      continue;
    }

    current += char;
  }

  if (current.length > 0 || row.length > 0) {
    row.push(current.trim());
    if (row.some((cell) => cell.length > 0)) {
      rows.push(row);
    }
  }

  return rows;
}

export default function BulkDiscountCsvImportModal({
  open,
  onOpenChange,
  customer,
  onSuccess,
}: BulkDiscountCsvImportModalProps) {
  const { toast } = useToast();
  const [csvText, setCsvText] = useState('');
  const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    const loadProductCodes = async () => {
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

    loadProductCodes();
    return () => {
      cancelled = true;
    };
  }, [open, toast]);

  const productCodeMap = useMemo(() => {
    const map = new Map<string, ProductCodeOption>();
    for (const product of productCodes) {
      map.set(product.code.toUpperCase(), product);
    }
    return map;
  }, [productCodes]);

  const handleFileChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const text = await file.text();
    setCsvText(text);
  };

  const handleSubmit = async () => {
    if (!csvText.trim()) {
      toast({ title: 'Error', description: 'Paste CSV rows or choose a CSV file.', variant: 'destructive' });
      return;
    }
    if (loadingProducts) {
      toast({ title: 'Please wait', description: 'Product codes are still loading.', variant: 'destructive' });
      return;
    }

    try {
      const rows = parseCsv(csvText);
      if (rows.length < 2) {
        throw new Error('CSV must include a header row and at least one data row.');
      }

      const headers = rows[0].map((value) => value.trim().toLowerCase());
      const requiredHeaders = ['product_code', 'discount_type', 'discount_value'];
      for (const header of requiredHeaders) {
        if (!headers.includes(header)) {
          throw new Error(`CSV is missing required column: ${header}`);
        }
      }

      const dataLines: CustomerDiscountBulkLine[] = rows.slice(1).map((cells, index) => {
        const rowData = Object.fromEntries(headers.map((header, headerIndex) => [header, cells[headerIndex] || '']));
        const productCode = productCodeMap.get((rowData.product_code || '').toUpperCase());
        if (!productCode) {
          throw new Error(`Row ${index + 2}: unknown product_code '${rowData.product_code}'.`);
        }

        return {
          product_code: String(productCode.id),
          discount_type: rowData.discount_type as CustomerDiscountBulkLine['discount_type'],
          discount_value: rowData.discount_value,
          currency: rowData.currency || 'PGK',
          min_charge: rowData.min_charge || null,
          max_charge: rowData.max_charge || null,
          valid_from: rowData.valid_from || null,
          valid_until: rowData.valid_until || null,
          notes: rowData.notes || '',
        };
      });

      setSaving(true);
      await bulkUpsertCustomerDiscounts({
        customer: customer.id,
        lines: dataLines,
      });
      toast({ title: 'Success', description: 'CSV negotiated pricing imported successfully.' });
      await onSuccess();
      onOpenChange(false);
      setCsvText('');
    } catch (err) {
      toast({
        title: 'Import failed',
        description: err instanceof Error ? err.message : 'Failed to import CSV negotiated pricing.',
        variant: 'destructive',
      });
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-3xl">
        <DialogHeader>
          <DialogTitle>Import Negotiated Pricing CSV</DialogTitle>
          <DialogDescription>
            Import multiple negotiated discount rows for {customer.name}. Existing rows for the same product code will update.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-md border border-slate-200 bg-slate-50 p-3">
            <p className="text-sm text-slate-600">
              Download the template first if you want the exact column order and sample rows.
            </p>
            <Button type="button" variant="outline" onClick={downloadDiscountCsvTemplate}>
              Download Template
            </Button>
          </div>

          <div className="space-y-2">
            <Label htmlFor="discount-csv-file">Upload CSV File</Label>
            <Input id="discount-csv-file" type="file" accept=".csv,text/csv" onChange={handleFileChange} />
          </div>

          <div className="space-y-2">
            <Label htmlFor="discount-csv-text">CSV Content</Label>
            <Textarea
              id="discount-csv-text"
              rows={14}
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder={DISCOUNT_CSV_TEMPLATE}
            />
          </div>

          <div className="rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-600">
            Required columns: <span className="font-mono">product_code</span>, <span className="font-mono">discount_type</span>, <span className="font-mono">discount_value</span>
            <br />
            Optional columns: <span className="font-mono">currency</span>, <span className="font-mono">min_charge</span>, <span className="font-mono">max_charge</span>, <span className="font-mono">valid_from</span>, <span className="font-mono">valid_until</span>, <span className="font-mono">notes</span>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSubmit} disabled={saving || loadingProducts}>
            {saving ? 'Importing...' : 'Import CSV'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
