'use client';

import React, { useState } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { createSpotRate, type SpotRate } from '@/lib/api';
import CompanySearchCombobox from '@/components/CompanySearchCombobox';
import { type CompanySearchResult } from '@/lib/types';

import { Textarea } from '@/components/ui/textarea';

interface CreateSpotRateDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: (spotRate: SpotRate) => void;
    quoteId: string;
    originLocationId: string;
    destinationLocationId: string;
    mode: string;
}

export function CreateSpotRateDialog({
    isOpen,
    onClose,
    onSuccess,
    quoteId,
    originLocationId,
    destinationLocationId,
    mode,
}: CreateSpotRateDialogProps) {
    const [supplier, setSupplier] = useState<CompanySearchResult | null>(null);
    const [currency, setCurrency] = useState('AUD');
    const [validUntil, setValidUntil] = useState('');
    const [notes, setNotes] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    const handleSave = async () => {
        if (!supplier) {
            setError('Please select a supplier');
            return;
        }

        try {
            setSaving(true);
            setError(null);

            const newSpotRate = await createSpotRate({
                quote: quoteId,
                supplier: supplier.id,
                origin_location: originLocationId,
                destination_location: destinationLocationId,
                mode: mode,
                currency: currency,
                valid_until: validUntil || undefined,
                notes: notes,
            });

            onSuccess(newSpotRate);
            onClose();

            // Reset form
            setSupplier(null);
            setCurrency('AUD');
            setValidUntil('');
            setNotes('');
        } catch (err: unknown) {
            console.error(err);
            const message = err instanceof Error ? err.message : 'Failed to create spot rate';
            setError(message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-md">
                <DialogHeader>
                    <DialogTitle>Create Spot Rate</DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Supplier</Label>
                        <CompanySearchCombobox
                            value={supplier}
                            onSelect={setSupplier}
                        />
                    </div>

                    <div className="space-y-2">
                        <Label>Currency</Label>
                        <Select value={currency} onValueChange={setCurrency}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="AUD">AUD</SelectItem>
                                <SelectItem value="USD">USD</SelectItem>
                                <SelectItem value="PGK">PGK</SelectItem>
                                <SelectItem value="EUR">EUR</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="space-y-2">
                        <Label>Notes (Optional)</Label>
                        <Textarea
                            value={notes}
                            onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNotes(e.target.value)}
                            placeholder="Add any notes about this spot rate..."
                            rows={3}
                        />
                    </div>

                    {error && (
                        <div className="text-sm text-red-600 bg-red-50 p-2 rounded">
                            {error}
                        </div>
                    )}
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancel</Button>
                    <Button onClick={handleSave} disabled={saving || !supplier}>
                        {saving ? 'Creating...' : 'Create Spot Rate'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
