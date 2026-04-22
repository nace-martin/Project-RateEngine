'use client';

import Link from 'next/link';
import React, { useRef, useState } from 'react';

import {
  V4RateCardUploadValidationError,
  uploadV4RateCardCSV,
  type V4RateCardUploadPreviewResponse,
  type V4RateCardUploadSuccessResponse,
} from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type UploadStatus = 'ready' | 'uploading' | 'preview' | 'success' | 'validation_error' | 'error';

type ValidationGridRow = {
  key: string;
  rowLabel: string;
  rowNumber: number | null;
  message: string;
};

function normalizeValidationErrors(errors: Record<string, string>): ValidationGridRow[] {
  const rows = Object.entries(errors).map(([key, message]) => {
    const match = /^row_(\d+)$/i.exec(key.trim());
    return {
      key,
      rowLabel: key,
      rowNumber: match ? Number(match[1]) : null,
      message,
    };
  });

  rows.sort((a, b) => {
    if (a.rowNumber !== null && b.rowNumber !== null) return a.rowNumber - b.rowNumber;
    if (a.rowNumber !== null) return -1;
    if (b.rowNumber !== null) return 1;
    return a.rowLabel.localeCompare(b.rowLabel);
  });

  return rows;
}

function statusBadgeClass(status: UploadStatus): string {
  switch (status) {
    case 'success':
      return 'border-green-200 bg-green-50 text-green-800';
    case 'preview':
      return 'border-amber-200 bg-amber-50 text-amber-800';
    case 'validation_error':
      return 'border-red-200 bg-red-50 text-red-800';
    case 'error':
      return 'border-red-200 bg-red-50 text-red-800';
    case 'uploading':
      return 'border-blue-200 bg-blue-50 text-blue-800';
    case 'ready':
    default:
      return 'border-blue-200 bg-blue-50 text-blue-800';
  }
}

function statusLabel(status: UploadStatus): string {
  switch (status) {
    case 'uploading':
      return 'Uploading';
    case 'success':
      return 'Success';
    case 'preview':
      return 'Preview Ready';
    case 'validation_error':
      return 'Validation Errors';
    case 'error':
      return 'Upload Failed';
    case 'ready':
    default:
      return 'Ready';
  }
}

export function RateCardUploader() {
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [status, setStatus] = useState<UploadStatus>('ready');
  const [result, setResult] = useState<V4RateCardUploadSuccessResponse | null>(null);
  const [previewResult, setPreviewResult] = useState<V4RateCardUploadPreviewResponse | null>(null);
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [runtimeError, setRuntimeError] = useState<string | null>(null);

  const validationRows = normalizeValidationErrors(validationErrors);

  const hasValidationErrors = validationRows.length > 0;

  function resetMessages() {
    setResult(null);
    setPreviewResult(null);
    setRuntimeError(null);
    setValidationErrors({});
  }

  function handleChooseFile() {
    fileInputRef.current?.click();
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setStatus('ready');
    resetMessages();
  }

  async function handleUpload(dryRun = false) {
    if (!selectedFile) return;

    setStatus('uploading');
    resetMessages();

    try {
      const uploadResult = await uploadV4RateCardCSV(selectedFile, { dryRun });
      if ('dry_run' in uploadResult && uploadResult.dry_run) {
        setPreviewResult(uploadResult);
        setStatus('preview');
      } else {
        setResult(uploadResult);
        setStatus('success');
      }
    } catch (error) {
      if (error instanceof V4RateCardUploadValidationError) {
        setValidationErrors(error.errors);
        setRuntimeError(error.message);
        setStatus('validation_error');
        return;
      }

      const message = error instanceof Error ? error.message : 'Unexpected upload error';
      setRuntimeError(message);
      setStatus('error');
    }
  }

  return (
    <div className="space-y-6">
      <Card className="border-blue-100 shadow-sm">
        <CardHeader className="border-b border-blue-100 bg-gradient-to-r from-blue-50 to-white">
          <CardTitle className="text-xl font-semibold text-slate-900">
            V4 Rate Card Bulk Uploader
          </CardTitle>
          <div className="text-sm text-slate-600">
            Upload a CSV to create or update Export, Import, and Domestic V4 sell rates in one transaction.
          </div>
        </CardHeader>

        <CardContent className="space-y-5 pt-6">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={handleFileChange}
          />

          <div className="grid gap-4 rounded-xl border border-slate-200 bg-slate-50/60 p-4 md:grid-cols-[1fr_auto_auto_auto] md:items-end">
            <div className="space-y-2">
              <div className="text-xs font-semibold tracking-wide text-slate-500 uppercase">
                Selected File
              </div>
              <div className="min-h-10 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
                {selectedFile ? selectedFile.name : 'No file selected'}
              </div>
              <div className="text-xs text-slate-500">
                Required columns: <span className="font-mono">rate_type, origin_code, destination_code, product_code, currency, amount, valid_from, valid_until</span>
              </div>
            </div>

            <Button
              type="button"
              variant="outline"
              className="border-blue-200 text-blue-800 hover:bg-blue-50"
              onClick={handleChooseFile}
              disabled={status === 'uploading'}
            >
              Choose File
            </Button>

            <Button
              type="button"
              variant="outline"
              className="border-amber-200 text-amber-800 hover:bg-amber-50"
              onClick={() => void handleUpload(true)}
              disabled={!selectedFile || status === 'uploading'}
            >
              Preview CSV
            </Button>

            <Button
              type="button"
              className="bg-blue-700 text-white hover:bg-blue-800"
              onClick={() => void handleUpload(false)}
              disabled={!selectedFile || status === 'uploading'}
              loading={status === 'uploading'}
              loadingText="Uploading rates..."
            >
              Upload Rates
            </Button>
          </div>

          <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3">
            <div className="text-sm font-medium text-slate-700">Status:</div>
            <Badge className={statusBadgeClass(status)}>{statusLabel(status)}</Badge>
            {selectedFile && (
              <div className="text-xs text-slate-500">
                File size: <span className="font-mono tabular-nums">{Math.ceil(selectedFile.size / 1024)} KB</span>
              </div>
            )}
          </div>

          {runtimeError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
              {runtimeError}
            </div>
          )}

          {result && (
            <div className="space-y-3 rounded-xl border border-green-200 bg-green-50/80 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="border-green-200 bg-green-100 text-green-800">Success</Badge>
                <div className="text-sm font-medium text-green-900">{result.message}</div>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-green-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Processed</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{result.processed_rows}</div>
                </div>
                <div className="rounded-lg border border-green-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Created</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{result.created_rows}</div>
                </div>
                <div className="rounded-lg border border-green-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Updated</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{result.updated_rows}</div>
                </div>
              </div>

              <div className="text-sm">
                <Link href="/pricing/rate-cards" className="text-blue-700 underline underline-offset-2 hover:text-blue-900">
                  Return to Rate Cards grid
                </Link>
              </div>
            </div>
          )}

          {previewResult && (
            <div className="space-y-3 rounded-xl border border-amber-200 bg-amber-50/80 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge className="border-amber-200 bg-amber-100 text-amber-800">Dry Run</Badge>
                <div className="text-sm font-medium text-amber-950">{previewResult.message}</div>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-lg border border-amber-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Processed</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{previewResult.processed_rows}</div>
                </div>
                <div className="rounded-lg border border-amber-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Would Create</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{previewResult.created_rows}</div>
                </div>
                <div className="rounded-lg border border-amber-200 bg-white px-3 py-2">
                  <div className="text-xs uppercase tracking-wide text-slate-500">Would Update</div>
                  <div className="font-mono tabular-nums text-lg text-slate-900">{previewResult.updated_rows}</div>
                </div>
              </div>

              <div className="overflow-auto rounded-xl border border-amber-200 bg-white">
                <table className="w-full min-w-[760px] text-sm">
                  <thead className="bg-amber-50">
                    <tr>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Row</th>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Action</th>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Table</th>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Product</th>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Coverage</th>
                      <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-amber-900">Validity</th>
                    </tr>
                  </thead>
                  <tbody>
                    {previewResult.preview_rows.map((row) => (
                      <tr key={`${row.row_number}-${row.product_code}-${row.valid_from}`} className="border-t border-amber-100">
                        <td className="px-3 py-2 font-mono text-slate-700">{row.row_number}</td>
                        <td className="px-3 py-2">
                          <Badge variant="outline">{row.action}</Badge>
                        </td>
                        <td className="px-3 py-2 text-slate-700">{row.table_name}</td>
                        <td className="px-3 py-2 text-slate-700">{row.product_code}</td>
                        <td className="px-3 py-2 text-slate-700">
                          {row.coverage} ({row.currency})
                        </td>
                        <td className="px-3 py-2 text-slate-700">
                          {row.valid_from} to {row.valid_until}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="border-slate-200 shadow-sm">
        <CardHeader className="pb-3">
          <CardTitle className="text-base text-slate-900">Validation Errors</CardTitle>
          <div className="text-sm text-slate-600">
            Row-level validation failures are listed below. Use the row identifier to cross-reference the source spreadsheet.
          </div>
        </CardHeader>
        <CardContent>
          {hasValidationErrors ? (
            <div className="overflow-auto rounded-xl border border-slate-200 bg-white" style={{ maxHeight: 360 }}>
              <table className="w-full min-w-[720px] border-separate border-spacing-0 text-sm">
                <thead className="sticky top-0 z-10 bg-blue-50">
                  <tr>
                    <th className="border-b border-blue-100 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-blue-900">
                      Row
                    </th>
                    <th className="border-b border-blue-100 px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-blue-900">
                      Error Detail
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {validationRows.map((row) => (
                    <tr key={row.key} className="align-top odd:bg-white even:bg-slate-50/70">
                      <td className="border-b border-slate-100 px-3 py-2 font-mono tabular-nums text-slate-800 whitespace-nowrap">
                        {row.rowLabel}
                      </td>
                      <td className="border-b border-slate-100 px-3 py-2 text-slate-700">
                        {row.message}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="rounded-lg border border-slate-200 bg-slate-50 px-4 py-6 text-sm text-slate-500">
              No validation errors to display.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default RateCardUploader;
