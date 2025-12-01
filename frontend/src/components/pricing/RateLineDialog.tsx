import React, { useEffect, useState } from 'react';
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';
import {
    getServiceComponents,
    ServiceComponent,
    RateLine,
    createRateLine,
    updateRateLine,
} from '@/lib/api';
import { Plus, Trash2 } from 'lucide-react';

interface RateLineDialogProps {
    isOpen: boolean;
    onClose: () => void;
    onSave: () => void;
    cardId: string;
    initialData?: RateLine | null;
}

export function RateLineDialog({
    isOpen,
    onClose,
    onSave,
    cardId,
    initialData,
}: RateLineDialogProps) {
    const [components, setComponents] = useState<ServiceComponent[]>([]);
    const [loading, setLoading] = useState(false);
    const [saving, setSaving] = useState(false);

    // Form State
    const [componentId, setComponentId] = useState('');
    const [method, setMethod] = useState('FLAT');
    const [minCharge, setMinCharge] = useState('0');
    const [description, setDescription] = useState('');
    const [percentValue, setPercentValue] = useState('0');
    const [percentOf, setPercentOf] = useState('');

    // Breaks State
    const [breaks, setBreaks] = useState<{ from: string; to: string; rate: string }[]>([
        { from: '0', to: '', rate: '0' },
    ]);

    useEffect(() => {
        if (isOpen) {
            loadComponents();
            if (initialData) {
                // Populate form
                setComponentId(initialData.component); // This might be ID or Code depending on serializer? Serializer expects ID for write.
                // Wait, initialData comes from RateCardSerializer which nests RateLineSerializer.
                // RateLineSerializer has `component` (ID) and `component_code`.
                // So `initialData.component` should be the ID.
                setMethod(initialData.method);
                setMinCharge(String(initialData.min_charge));
                setDescription(initialData.description || '');
                setPercentValue(String(initialData.percent_value || 0));
                setPercentOf(initialData.percent_of_component || '');

                if (initialData.breaks && initialData.breaks.length > 0) {
                    setBreaks(initialData.breaks.map(b => ({
                        from: String(b.from_value),
                        to: b.to_value ? String(b.to_value) : '',
                        rate: String(b.rate)
                    })));
                } else {
                    setBreaks([{ from: '0', to: '', rate: '0' }]);
                }
            } else {
                // Reset form
                setComponentId('');
                setMethod('FLAT');
                setMinCharge('0');
                setDescription('');
                setPercentValue('0');
                setPercentOf('');
                setBreaks([{ from: '0', to: '', rate: '0' }]);
            }
        }
    }, [isOpen, initialData]);

    async function loadComponents() {
        try {
            setLoading(true);
            const data = await getServiceComponents();
            setComponents(data);
        } catch (err) {
            console.error(err);
        } finally {
            setLoading(false);
        }
    }

    const handleAddBreak = () => {
        setBreaks([...breaks, { from: '', to: '', rate: '0' }]);
    };

    const handleRemoveBreak = (index: number) => {
        setBreaks(breaks.filter((_, i) => i !== index));
    };

    const handleBreakChange = (index: number, field: 'from' | 'to' | 'rate', value: string) => {
        const newBreaks = [...breaks];
        newBreaks[index][field] = value;
        setBreaks(newBreaks);
    };

    const handleSave = async () => {
        try {
            setSaving(true);

            // Construct payload
            const payload: Partial<RateLine> & { card: string } = {
                card: cardId,
                component: componentId, // ID
                method,
                min_charge: parseFloat(minCharge) || 0,
                description,
                unit: 'KG', // Defaulting for now, maybe add field
            };

            if (method === 'PERCENT') {
                payload.percent_value = parseFloat(percentValue) / 100; // Assuming input is percentage (e.g. 20 for 20%)
                // Wait, backend expects decimal 0.20.
                // If user types 20, we divide by 100? Or user types 0.20?
                // Let's assume user types 0.20 for now to match backend raw value, or add logic.
                // Actually, let's stick to raw value for simplicity or 0-100 if UI suggests %.
                // I'll assume raw value for now: 0.2
                payload.percent_value = parseFloat(percentValue);
                // percent_of_component expects ID or Code? 
                // RateLine model: percent_of_component = ForeignKey(ServiceComponent).
                // So it expects ID.
                // But `percentOf` state might be code if I selected from dropdown?
                // I need to find the ID from the code if I used code.
                // Let's assume `percentOf` holds the ID.
                if (percentOf) payload.percent_of_component = percentOf;
            }

            // Handle Breaks
            // Backend RateLineSerializer has `breaks` as read-only nested serializer?
            // If so, I can't write breaks via RateLine create/update directly unless I override create/update.
            // OR I have to create RateLine first, then create RateBreaks.
            // This is a common DRF pattern.
            // If I didn't implement writable nested serializer, I need to do it in two steps or update serializer.
            // I'll assume I need to update serializer to be writable or use a custom view.
            // BUT, for now, let's try to send it and see if it fails.
            // If it fails, I'll need to fix the backend.

            // Actually, I should check `RateLineSerializer` again.
            // `breaks = RateBreakSerializer(many=True, read_only=True)`
            // It is READ ONLY.
            // So I cannot save breaks via RateLine endpoint.

            // I have two options:
            // 1. Make `breaks` writable in serializer.
            // 2. Create RateLine, then loop and create RateBreaks via a RateBreak endpoint.

            // Option 1 is better for atomicity.
            // I will need to update `RateLineSerializer` in backend.

            // For now, I'll construct the payload assuming I'll fix the backend.
            if (method === 'WEIGHT_BREAK' || method === 'PER_UNIT') {
                payload.breaks = breaks.map(b => ({
                    from_value: parseFloat(b.from) || 0,
                    to_value: b.to ? parseFloat(b.to) : null,
                    rate: parseFloat(b.rate) || 0
                    // eslint-disable-next-line @typescript-eslint/no-explicit-any
                })) as any;
            }

            if (initialData) {
                await updateRateLine(initialData.id, payload);
            } else {
                await createRateLine(payload);
            }

            onSave();
            onClose();
        } catch (err) {
            console.error(err);
            alert('Failed to save rate line');
        } finally {
            setSaving(false);
        }
    };

    return (
        <Dialog open={isOpen} onOpenChange={onClose}>
            <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                    <DialogTitle>{initialData ? 'Edit Rate Line' : 'Add Rate Line'}</DialogTitle>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Component</Label>
                            <Select value={componentId} onValueChange={setComponentId} disabled={loading}>
                                <SelectTrigger>
                                    <SelectValue placeholder="Select component" />
                                </SelectTrigger>
                                <SelectContent>
                                    {components.map((c) => (
                                        <SelectItem key={c.id} value={c.id}>
                                            {c.code} - {c.description}
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
                                    <SelectItem value="FLAT">Flat Fee</SelectItem>
                                    <SelectItem value="PER_UNIT">Per Unit (e.g. Per Kg)</SelectItem>
                                    <SelectItem value="WEIGHT_BREAK">Weight Break</SelectItem>
                                    <SelectItem value="PERCENT">Percentage</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label>Description (Optional)</Label>
                        <Input value={description} onChange={(e) => setDescription(e.target.value)} />
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Min Charge</Label>
                            <Input type="number" value={minCharge} onChange={(e) => setMinCharge(e.target.value)} />
                        </div>
                        {/* Unit input could go here */}
                    </div>

                    {method === 'PERCENT' && (
                        <div className="grid grid-cols-2 gap-4 p-4 border rounded-md bg-slate-50">
                            <div className="space-y-2">
                                <Label>Percent Value (e.g. 0.20 for 20%)</Label>
                                <Input type="number" step="0.01" value={percentValue} onChange={(e) => setPercentValue(e.target.value)} />
                            </div>
                            <div className="space-y-2">
                                <Label>Percent Of Component</Label>
                                <Select value={percentOf} onValueChange={setPercentOf}>
                                    <SelectTrigger>
                                        <SelectValue placeholder="Select component" />
                                    </SelectTrigger>
                                    <SelectContent>
                                        {components.map((c) => (
                                            <SelectItem key={c.id} value={c.id}>
                                                {c.code}
                                            </SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                    )}

                    {(method === 'WEIGHT_BREAK' || method === 'PER_UNIT') && (
                        <div className="space-y-2">
                            <div className="flex justify-between items-center">
                                <Label>Rate Breaks</Label>
                                {method === 'WEIGHT_BREAK' && (
                                    <Button variant="outline" size="sm" onClick={handleAddBreak}>
                                        <Plus className="w-3 h-3 mr-1" /> Add Break
                                    </Button>
                                )}
                            </div>
                            <div className="border rounded-md p-2 space-y-2">
                                {breaks.map((brk, index) => (
                                    <div key={index} className="flex items-center gap-2">
                                        <Input
                                            placeholder="From"
                                            type="number"
                                            value={brk.from}
                                            onChange={(e) => handleBreakChange(index, 'from', e.target.value)}
                                            className="w-24"
                                        />
                                        <span>-</span>
                                        <Input
                                            placeholder="To (Empty=Max)"
                                            type="number"
                                            value={brk.to}
                                            onChange={(e) => handleBreakChange(index, 'to', e.target.value)}
                                            className="w-24"
                                        />
                                        <span>:</span>
                                        <Input
                                            placeholder="Rate"
                                            type="number"
                                            value={brk.rate}
                                            onChange={(e) => handleBreakChange(index, 'rate', e.target.value)}
                                            className="w-24"
                                        />
                                        {method === 'WEIGHT_BREAK' && breaks.length > 1 && (
                                            <Button variant="ghost" size="icon" onClick={() => handleRemoveBreak(index)}>
                                                <Trash2 className="w-4 h-4 text-red-500" />
                                            </Button>
                                        )}
                                    </div>
                                ))}
                            </div>
                            {method === 'PER_UNIT' && <p className="text-xs text-muted-foreground">For Per Unit, enter a single break (e.g. 0 - Empty : Rate)</p>}
                        </div>
                    )}

                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={onClose}>Cancel</Button>
                    <Button onClick={handleSave} disabled={saving}>
                        {saving ? 'Saving...' : 'Save'}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
