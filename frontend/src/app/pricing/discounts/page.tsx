'use client';

import { useState, useEffect } from 'react';
import {
    Card,
    CardContent,
    CardDescription,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
    Dialog,
    DialogContent,
    DialogDescription,
    DialogFooter,
    DialogHeader,
    DialogTitle,
} from "@/components/ui/dialog";
import { usePermissions } from '@/hooks/usePermissions';
import { useToast } from '@/context/toast-context';
import {
    getCustomerDiscounts,
    deleteCustomerDiscount,
    CustomerDiscount,
} from '@/lib/api';
import DiscountFormModal from '@/components/pricing/DiscountFormModal';

export default function DiscountsPage() {
    const [discounts, setDiscounts] = useState<CustomerDiscount[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingDiscount, setEditingDiscount] = useState<CustomerDiscount | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<CustomerDiscount | null>(null);

    const { isAdmin, isManager } = usePermissions();
    const canManage = isAdmin || isManager;
    const { toast } = useToast();

    const fetchDiscounts = async () => {
        setLoading(true);
        try {
            const data = await getCustomerDiscounts(
                searchQuery ? { search: searchQuery } : undefined
            );
            setDiscounts(data);
            setError(null);
        } catch (err) {
            console.error('Failed to fetch discounts', err);
            setError('Failed to load discounts.');
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchDiscounts();
    }, [searchQuery]);

    const handleAddNew = () => {
        setEditingDiscount(null);
        setIsModalOpen(true);
    };

    const handleEdit = (discount: CustomerDiscount) => {
        setEditingDiscount(discount);
        setIsModalOpen(true);
    };

    const handleDeleteConfirm = async () => {
        if (!deleteTarget) return;
        try {
            await deleteCustomerDiscount(deleteTarget.id);
            toast({ title: 'Discount deleted', description: 'The discount has been removed.' });
            setDeleteTarget(null);
            fetchDiscounts();
        } catch (err) {
            toast({
                title: 'Delete failed',
                description: err instanceof Error ? err.message : 'Unknown error',
                variant: 'destructive'
            });
        }
    };

    const handleModalSuccess = () => {
        setIsModalOpen(false);
        setEditingDiscount(null);
        fetchDiscounts();
    };

    const formatDiscountValue = (d: CustomerDiscount) => {
        switch (d.discount_type) {
            case 'PERCENTAGE':
                return `${d.discount_value}%`;
            case 'MARGIN_OVERRIDE':
                return `${d.discount_value}% margin`;
            case 'FLAT_AMOUNT':
            case 'FIXED_CHARGE':
            case 'RATE_REDUCTION':
                return `${d.currency} ${parseFloat(d.discount_value).toFixed(2)}`;
            default:
                return d.discount_value;
        }
    };

    const getStatusBadge = (d: CustomerDiscount) => {
        if (d.is_active === false) {
            return <Badge variant="outline" className="text-amber-600 border-amber-300">Expired</Badge>;
        }
        return <Badge variant="outline" className="text-emerald-600 border-emerald-300">Active</Badge>;
    };

    return (
        <div className="container mx-auto py-8 max-w-7xl">
            <Card>
                <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-6">
                    <div className="space-y-1.5">
                        <CardTitle>Customer Discounts</CardTitle>
                        <CardDescription>
                            Manage customer-specific pricing discounts and negotiated rates.
                        </CardDescription>
                    </div>
                    {canManage && (
                        <Button onClick={handleAddNew}>Add Discount</Button>
                    )}
                </CardHeader>
                <CardContent>
                    {/* Search Bar */}
                    <div className="mb-4">
                        <Input
                            placeholder="Search by customer, product code, or notes..."
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                            className="max-w-md"
                        />
                    </div>

                    {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

                    <div className="rounded-md border border-slate-200">
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Customer</TableHead>
                                    <TableHead>Product Code</TableHead>
                                    <TableHead>Type</TableHead>
                                    <TableHead className="text-right">Value</TableHead>
                                    <TableHead>Valid Until</TableHead>
                                    <TableHead>Status</TableHead>
                                    {canManage && <TableHead className="text-right">Actions</TableHead>}
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {loading ? (
                                    <TableRow>
                                        <TableCell colSpan={canManage ? 7 : 6} className="h-24 text-center text-muted-foreground">
                                            Loading...
                                        </TableCell>
                                    </TableRow>
                                ) : discounts.length === 0 ? (
                                    <TableRow>
                                        <TableCell colSpan={canManage ? 7 : 6} className="h-24 text-center text-muted-foreground">
                                            No discounts found. {canManage && 'Click "Add Discount" to create one.'}
                                        </TableCell>
                                    </TableRow>
                                ) : (
                                    discounts.map((discount) => (
                                        <TableRow key={discount.id}>
                                            <TableCell className="font-medium">
                                                {discount.customer_name}
                                            </TableCell>
                                            <TableCell>
                                                <div className="flex flex-col">
                                                    <span className="font-mono text-sm">{discount.product_code_code}</span>
                                                    <span className="text-xs text-muted-foreground truncate max-w-[200px]">
                                                        {discount.product_code_description}
                                                    </span>
                                                </div>
                                            </TableCell>
                                            <TableCell>
                                                <Badge variant="secondary">
                                                    {discount.discount_type_display || discount.discount_type}
                                                </Badge>
                                            </TableCell>
                                            <TableCell className="text-right font-medium">
                                                {formatDiscountValue(discount)}
                                            </TableCell>
                                            <TableCell>
                                                {discount.valid_until
                                                    ? new Date(discount.valid_until).toLocaleDateString()
                                                    : '—'
                                                }
                                            </TableCell>
                                            <TableCell>
                                                {getStatusBadge(discount)}
                                            </TableCell>
                                            {canManage && (
                                                <TableCell className="text-right space-x-2">
                                                    <Button variant="ghost" size="sm" onClick={() => handleEdit(discount)}>
                                                        Edit
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="sm"
                                                        className="text-red-600 hover:text-red-700"
                                                        onClick={() => setDeleteTarget(discount)}
                                                    >
                                                        Delete
                                                    </Button>
                                                </TableCell>
                                            )}
                                        </TableRow>
                                    ))
                                )}
                            </TableBody>
                        </Table>
                    </div>
                </CardContent>
            </Card>

            {/* Add/Edit Modal */}
            <DiscountFormModal
                open={isModalOpen}
                onOpenChange={setIsModalOpen}
                discount={editingDiscount}
                onSuccess={handleModalSuccess}
            />

            {/* Delete Confirmation Dialog */}
            <Dialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
                <DialogContent>
                    <DialogHeader>
                        <DialogTitle>Delete Discount</DialogTitle>
                        <DialogDescription>
                            Are you sure you want to delete this discount for{' '}
                            <strong>{deleteTarget?.customer_name}</strong> on{' '}
                            <strong>{deleteTarget?.product_code_code}</strong>?
                            This action cannot be undone.
                        </DialogDescription>
                    </DialogHeader>
                    <DialogFooter>
                        <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
                        <Button variant="destructive" onClick={handleDeleteConfirm}>Delete</Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
}
