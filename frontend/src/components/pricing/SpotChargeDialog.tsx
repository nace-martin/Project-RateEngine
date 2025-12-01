'use client';

import React, { useState, useEffect } from 'react';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
    createSpotCharge,
    updateSpotCharge,
    getServiceComponents,
    type SpotCharge,
    type ServiceComponent,
} from '@/lib/api';

interface SpotChargeDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
    spotRateId: string;
    initialData?: SpotCharge | null;
}

export function SpotChargeDialog({
    isOpen,
    onClose,
    onSuccess,
    spotRateId,
    initialData,
}: SpotChargeDialogProps) {
    const [components, setComponents] = useState<ServiceComponent[]>([]);
    const [componentId, setComponentId] = useState('');
    const [method, setMethod] = useState('FLAT');
    const [unit, setUnit] = useState('');
    const [rate, setRate] = useState('');
    const [minCharge, setMinCharge] = useState('');
    const [description, setDescription] = useState('');
    const [percentValue, setPercentValue] = useState('');
    const [percentOfComponent, setPercentOfComponent] = useState('');
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Fetch components
    useEffect(() => {
        const fetchComponents = async () => {
            try {
                const data = await getServiceComponents();
                setComponents(data);
            } catch (err) {
                console.error('Failed to fetch components:', err);
            }
        };
        fetchComponents();
    }, []);

    // Load initial data if editing
    useEffect(() => {
        if (initialData) {
            setComponentId(initialData.component);
            setMethod(initialData.method);
            setUnit(initialData.unit || '');
            setRate(initialData.rate);
            setMinCharge(initialData.min_charge);
            setDescription(initialData.description);
            setPercentValue(initialData.percent_value || '');
            setPercentOfComponent(initialData.percent_of_component || '');
        } else {
            // Reset for new
            setComponentId('');
            setMethod('FLAT');
            setUnit('');
            setRate('');
            setMinCharge('');
            setDescription('');
            setPercentValue('');
            setPercentOfComponent('');
        }
    }, [initialData, isOpen]);

    const handleSave = async () => {
        if (!componentId) {
            setError('Please select a component');
            return;
        }

        try {
            setSaving(true);
            setError(null);

            const chargeData: Partial<SpotCharge> = {
                spot_rate: spotRateId,
                component: componentId,
                method: method,
                unit: unit || undefined,
                rate: rate || '0',
                min_charge: minCharge || '0',
                description: description,
            };

            if (method === 'PERCENT') {
                chargeData.percent_value = percentValue;
                chargeData.percent_of_component = percentOfComponent;
            }

            if (initialData?.id) {
                await updateSpotCharge(initialData.id, chargeData);
            } else {
                await createSpotCharge(chargeData);
            }

            onSuccess();
            onClose();
        } catch (err: unknown) {
            console.error(err);
            const message = err instanceof Error ? err.message : 'Failed to save spot charge';
            setError(message);
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>{initialData ? 'Edit' : 'Add'} Spot Charge</DialogTitle>
                </DialogHeader>

                <div className="space-y-4 py-4">
                    <div className="space-y-2">
                        <Label>Component</Label>
                        <Select value={componentId} onValueChange={setComponentId}>
                            <SelectTrigger>
                                <SelectValue placeholder="Select component" />
                            </SelectTrigger>
                            <SelectContent>
                                {components.map((comp) => (
                                    <SelectItem key={comp.id} value={comp.id}>
                                        {comp.code} - {comp.description}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="space-y-2">
                        <Label>Method</Label>
                        <Select value={method} onValueChange={setMethod}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                <SelectItem value="FLAT">Flat Amount</SelectItem>
                                <SelectItem value="PER_UNIT">Per Unit</SelectItem>
                                <SelectItem value="PERCENT">Percentage</SelectItem>
                            </SelectContent>
                        </Select>
                    </div>

                    {method === 'PERCENT' ? (
                        <>
                            <div className="space-y-2">
                                <Label>Percentage Value (e.g., 0.10 for 10%)</Label>
                                <Input
                                    type="number"
                                    step="0.0001"
                                    value={percentValue}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPercentValue(e.target.value)}
                                    placeholder="0.10"
                                />
                            </div>
                            <div className="space-y-2">
                                <Label>Percentage Of Component</Label>
                                <Select value={percentOfComponent} onValueChange={setPercentOfComponent}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select component" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {components.map((comp) => (
                                            <SelectItem key={comp.id} value={comp.id}>
                                                {comp.code} - {comp.description}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </>
                    ) : (
                        <>
                            {method === 'PER_UNIT' && (
                                <div className="space-y-2">
                                    <Label>Unit</Label>
                                    <Select value={unit} onValueChange={setUnit}>
                                        <SelectTrigger>
                                            <SelectValue placeholder="Select unit" />
                                        </SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="KG">KG</SelectItem>
                                            <SelectItem value="CWT">CWT</SelectItem>
                                            <SelectItem value="CBM">CBM</SelectItem>
                                            <SelectItem value="SHIPMENT">Shipment</SelectItem>
                                        </SelectContent>
                                    </Select>
                                </div>
                            )}

                            <div className="space-y-2">
                                <Label>Rate</Label>
                                <Input
                                    type="number"
                                    step="0.01"
                                    value={rate}
                                    onChange={(e: React.ChangeEvent<HTMLInputElement>) => setRate(e.target.value)}
                                    placeholder="0.00"
                                />
                            </div>
                        </>
                    )}

                    <div className="space-y-2">
                        <Label>Min Charge</Label>
                        <Input
                            type="number"
                            step="0.01"
                            value={minCharge}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setMinCharge(e.target.value)}
                            placeholder="0.00"
                        />
                    </div>

                    <div className="space-y-2">
                        <Label>Description (Optional)</Label>
                        <Input
                            value={description}
                            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setDescription(e.target.value)}
                            placeholder="e.g., Emergency handling fee"
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
                    <Button onClick={handleSave} disabled={saving || !componentId}>
                        {saving ? 'Saving...' : initialData ? 'Update' : 'Add'} Charge
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
