'use client';

import { useState, useEffect } from 'react';
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
import { useToast } from '@/context/toast-context';
import CompanySearchCombobox from '@/components/CompanySearchCombobox';
import {
    CustomerDiscount,
    ProductCodeOption,
    DiscountType,
    createCustomerDiscount,
    updateCustomerDiscount,
    getProductCodes,
} from '@/lib/api';

interface DiscountFormModalProps {
    open: boolean;
    onOpenChange: (open: boolean) => void;
    discount: CustomerDiscount | null;
    onSuccess: () => void;
}

const DISCOUNT_TYPES: { value: DiscountType; label: string; description: string }[] = [
    { value: 'PERCENTAGE', label: 'Percentage', description: 'Reduce sell price by X%' },
    { value: 'FLAT_AMOUNT', label: 'Flat Amount', description: 'Subtract fixed amount from sell price' },
    { value: 'FIXED_CHARGE', label: 'Fixed Charge', description: 'Replace sell price with fixed amount' },
    { value: 'RATE_REDUCTION', label: 'Rate Reduction', description: 'Set rate per kg' },
    { value: 'MARGIN_OVERRIDE', label: 'Margin Override', description: 'Apply custom margin %' },
];

export default function DiscountFormModal({
    open,
    onOpenChange,
    discount,
    onSuccess
}: DiscountFormModalProps) {
    const isEditing = !!discount;
    const { toast } = useToast();

    // Form state
    const [customerId, setCustomerId] = useState<string>('');
    const [customerName, setCustomerName] = useState<string>('');
    const [selectedCompany, setSelectedCompany] = useState<{ id: string; name: string } | null>(null);
    const [productCodeId, setProductCodeId] = useState<string>('');
    const [discountType, setDiscountType] = useState<DiscountType>('PERCENTAGE');
    const [discountValue, setDiscountValue] = useState<string>('');
    const [minCharge, setMinCharge] = useState<string>('');
    const [maxCharge, setMaxCharge] = useState<string>('');
    const [currency, setCurrency] = useState<string>('PGK');
    const [validFrom, setValidFrom] = useState<string>('');
    const [validUntil, setValidUntil] = useState<string>('');
    const [notes, setNotes] = useState<string>('');

    // Product codes for dropdown
    const [productCodes, setProductCodes] = useState<ProductCodeOption[]>([]);
    const [loadingProducts, setLoadingProducts] = useState(false);
    const [productFilter, setProductFilter] = useState<string>('');
    const [saving, setSaving] = useState(false);

    // Load product codes on mount
    useEffect(() => {
        const load = async () => {
            setLoadingProducts(true);
            try {
                const data = await getProductCodes();
                setProductCodes(data);
            } catch (err) {
                console.error('Failed to load product codes', err);
            } finally {
                setLoadingProducts(false);
            }
        };
        load();
    }, []);

    // Populate form when editing
    useEffect(() => {
        if (discount) {
            setCustomerId(discount.customer);
            setCustomerName(discount.customer_name);
            setSelectedCompany({ id: discount.customer, name: discount.customer_name });
            setProductCodeId(discount.product_code);
            setDiscountType(discount.discount_type);
            setDiscountValue(discount.discount_value);
            setMinCharge(discount.min_charge || '');
            setMaxCharge(discount.max_charge || '');
            setCurrency(discount.currency);
            setValidFrom(discount.valid_from || '');
            setValidUntil(discount.valid_until || '');
            setNotes(discount.notes || '');
        } else {
            // Reset form for new discount
            setCustomerId('');
            setCustomerName('');
            setSelectedCompany(null);
            setProductCodeId('');
            setDiscountType('PERCENTAGE');
            setDiscountValue('');
            setMinCharge('');
            setMaxCharge('');
            setCurrency('PGK');
            setValidFrom('');
            setValidUntil('');
            setNotes('');
            setProductFilter('');
        }
    }, [discount, open]);

    const handleCustomerSelect = (company: { id: string; name: string } | null) => {
        setSelectedCompany(company);
        if (company) {
            setCustomerId(company.id);
            setCustomerName(company.name);
        } else {
            setCustomerId('');
            setCustomerName('');
        }
    };

    const handleSubmit = async () => {
        if (!customerId) {
            toast({ title: 'Error', description: 'Please select a customer', variant: 'destructive' });
            return;
        }
        if (!productCodeId) {
            toast({ title: 'Error', description: 'Please select a product code', variant: 'destructive' });
            return;
        }
        if (!discountValue || parseFloat(discountValue) <= 0) {
            toast({ title: 'Error', description: 'Please enter a valid discount value', variant: 'destructive' });
            return;
        }

        setSaving(true);
        try {
            const payload: Record<string, unknown> = {
                customer: customerId,
                product_code: productCodeId,
                discount_type: discountType,
                discount_value: discountValue,
                currency,
                valid_from: validFrom || null,
                valid_until: validUntil || null,
                notes: notes || '',
            };

            // Add min/max charges for RATE_REDUCTION type
            if (discountType === 'RATE_REDUCTION') {
                payload.min_charge = minCharge ? parseFloat(minCharge) : null;
                payload.max_charge = maxCharge ? parseFloat(maxCharge) : null;
            }

            if (isEditing && discount) {
                await updateCustomerDiscount(discount.id, payload);
                toast({ title: 'Success', description: 'Discount updated successfully' });
            } else {
                await createCustomerDiscount(payload);
                toast({ title: 'Success', description: 'Discount created successfully' });
            }

            onSuccess();
        } catch (err) {
            toast({
                title: 'Error',
                description: err instanceof Error ? err.message : 'Failed to save discount',
                variant: 'destructive'
            });
        } finally {
            setSaving(false);
        }
    };

    const getValueLabel = () => {
        switch (discountType) {
            case 'PERCENTAGE':
            case 'MARGIN_OVERRIDE':
                return 'Percentage (%)';
            case 'RATE_REDUCTION':
                return 'Rate per kg';
            default:
                return 'Amount';
        }
    };

    // Filter and group product codes by domain
    const filteredProducts = productCodes.filter(pc => {
        if (!productFilter) return true;
        const search = productFilter.toLowerCase();
        return pc.code.toLowerCase().includes(search) ||
            pc.description.toLowerCase().includes(search);
    });

    const groupedProductCodes = filteredProducts.reduce((acc, pc) => {
        const domain = pc.domain || 'OTHER';
        if (!acc[domain]) acc[domain] = [];
        acc[domain].push(pc);
        return acc;
    }, {} as Record<string, ProductCodeOption[]>);

    return (
        <Dialog open={open} onOpenChange={onOpenChange}>
            <DialogContent className="max-w-lg">
                <DialogHeader>
                    <DialogTitle>{isEditing ? 'Edit Discount' : 'Add Customer Discount'}</DialogTitle>
                    <DialogDescription>
                        {isEditing
                            ? 'Update the discount configuration for this customer.'
                            : 'Create a new customer-specific discount on a product code.'
                        }
                    </DialogDescription>
                </DialogHeader>

                <div className="grid gap-4 py-4">
                    {/* Customer Selection */}
                    <div className="space-y-2">
                        <Label htmlFor="customer">Customer</Label>
                        {isEditing ? (
                            <Input value={customerName} disabled />
                        ) : (
                            <CompanySearchCombobox
                                value={selectedCompany}
                                onSelect={handleCustomerSelect}
                                placeholder="Search for customer..."
                            />
                        )}
                    </div>

                    {/* Product Code Selection */}
                    <div className="space-y-2">
                        <Label htmlFor="product_code">Product Code</Label>
                        <Select
                            value={productCodeId}
                            onValueChange={setProductCodeId}
                            disabled={isEditing}
                        >
                            <SelectTrigger>
                                <SelectValue placeholder={loadingProducts ? 'Loading...' : 'Select product code'} />
                            </SelectTrigger>
                            <SelectContent className="max-h-[300px]">
                                {/* Search Input */}
                                <div className="sticky top-0 p-2 bg-background border-b">
                                    <Input
                                        placeholder="Search products..."
                                        value={productFilter}
                                        onChange={(e) => setProductFilter(e.target.value)}
                                        className="h-8"
                                        onClick={(e) => e.stopPropagation()}
                                        onKeyDown={(e) => e.stopPropagation()}
                                    />
                                </div>
                                {/* Product List */}
                                {Object.keys(groupedProductCodes).length === 0 ? (
                                    <div className="px-3 py-4 text-sm text-muted-foreground text-center">
                                        {productFilter ? 'No products match your search' : 'No products available'}
                                    </div>
                                ) : (
                                    Object.entries(groupedProductCodes).map(([domain, codes]) => (
                                        <div key={domain}>
                                            <div className="px-2 py-1.5 text-xs font-semibold text-muted-foreground bg-muted sticky top-[52px]">
                                                {domain} ({codes.length})
                                            </div>
                                            {codes.map((pc) => (
                                                <SelectItem key={String(pc.id)} value={String(pc.id)}>
                                                    <span className="font-mono text-sm">{pc.code}</span>
                                                    <span className="text-muted-foreground ml-2">- {pc.description}</span>
                                                </SelectItem>
                                            ))}
                                        </div>
                                    ))
                                )}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Discount Type */}
                    <div className="space-y-2">
                        <Label htmlFor="discount_type">Discount Type</Label>
                        <Select value={discountType} onValueChange={(v) => setDiscountType(v as DiscountType)}>
                            <SelectTrigger>
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {DISCOUNT_TYPES.map((dt) => (
                                    <SelectItem key={dt.value} value={dt.value}>
                                        <div className="flex flex-col">
                                            <span>{dt.label}</span>
                                            <span className="text-xs text-muted-foreground">{dt.description}</span>
                                        </div>
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    {/* Value and Currency */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="discount_value">{getValueLabel()}</Label>
                            <Input
                                id="discount_value"
                                type="number"
                                step="0.01"
                                value={discountValue}
                                onChange={(e) => setDiscountValue(e.target.value)}
                                placeholder="e.g. 10"
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="currency">Currency</Label>
                            <Select value={currency} onValueChange={setCurrency}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="PGK">PGK</SelectItem>
                                    <SelectItem value="AUD">AUD</SelectItem>
                                    <SelectItem value="USD">USD</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    {/* Min/Max Charges - Only for RATE_REDUCTION */}
                    {discountType === 'RATE_REDUCTION' && (
                        <div className="grid grid-cols-2 gap-4 p-3 bg-muted/50 rounded-lg border border-dashed">
                            <div className="space-y-2">
                                <Label htmlFor="min_charge">Minimum Charge (optional)</Label>
                                <Input
                                    id="min_charge"
                                    type="number"
                                    step="0.01"
                                    value={minCharge}
                                    onChange={(e) => setMinCharge(e.target.value)}
                                    placeholder="e.g. 50"
                                />
                                <p className="text-xs text-muted-foreground">Floor charge regardless of weight</p>
                            </div>
                            <div className="space-y-2">
                                <Label htmlFor="max_charge">Maximum Charge (optional)</Label>
                                <Input
                                    id="max_charge"
                                    type="number"
                                    step="0.01"
                                    value={maxCharge}
                                    onChange={(e) => setMaxCharge(e.target.value)}
                                    placeholder="e.g. 500"
                                />
                                <p className="text-xs text-muted-foreground">Cap on total charge</p>
                            </div>
                        </div>
                    )}

                    {/* Validity Dates */}
                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label htmlFor="valid_from">Valid From (optional)</Label>
                            <Input
                                id="valid_from"
                                type="date"
                                value={validFrom}
                                onChange={(e) => setValidFrom(e.target.value)}
                            />
                        </div>
                        <div className="space-y-2">
                            <Label htmlFor="valid_until">Valid Until (optional)</Label>
                            <Input
                                id="valid_until"
                                type="date"
                                value={validUntil}
                                onChange={(e) => setValidUntil(e.target.value)}
                            />
                        </div>
                    </div>

                    {/* Notes */}
                    <div className="space-y-2">
                        <Label htmlFor="notes">Notes (optional)</Label>
                        <Textarea
                            id="notes"
                            value={notes}
                            onChange={(e) => setNotes(e.target.value)}
                            placeholder="Internal notes about this discount..."
                            rows={2}
                        />
                    </div>
                </div>

                <DialogFooter>
                    <Button variant="outline" onClick={() => onOpenChange(false)}>
                        Cancel
                    </Button>
                    <Button onClick={handleSubmit} disabled={saving}>
                        {saving ? 'Saving...' : (isEditing ? 'Update' : 'Create')}
                    </Button>
                </DialogFooter>
            </DialogContent>
        </Dialog>
    );
}
