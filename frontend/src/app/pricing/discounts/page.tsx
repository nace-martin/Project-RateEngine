'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import {
    Card,
    CardContent,
    CardHeader,
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
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import { usePermissions } from '@/hooks/usePermissions';
import { useToast } from '@/context/toast-context';
import {
    getCustomerDiscounts,
    deleteCustomerDiscount,
    CustomerDiscount,
} from '@/lib/api';
import DiscountFormModal from '@/components/pricing/DiscountFormModal';
import {
    Percent,
    Search,
    Plus,
    Edit2,
    Trash2,
    RefreshCw,
    Filter,
    Tag,
    Users,
    Clock,
    TrendingDown,
} from 'lucide-react';

export default function DiscountsPage() {
    const [discounts, setDiscounts] = useState<CustomerDiscount[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [searchQuery, setSearchQuery] = useState('');
    const [filterType, setFilterType] = useState<string>('all');
    const [filterStatus, setFilterStatus] = useState<string>('all');
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingDiscount, setEditingDiscount] = useState<CustomerDiscount | null>(null);
    const [deleteTarget, setDeleteTarget] = useState<CustomerDiscount | null>(null);

    const { isAdmin } = usePermissions();
    const canManage = isAdmin;
    const { toast } = useToast();

    const fetchDiscounts = useCallback(async () => {
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
    }, [searchQuery]);

    useEffect(() => {
        fetchDiscounts();
    }, [fetchDiscounts]);

    // Summary statistics
    const stats = useMemo(() => {
        const active = discounts.filter(d => d.is_active !== false);
        const expired = discounts.filter(d => d.is_active === false);
        const uniqueCustomers = new Set(discounts.map(d => d.customer)).size;

        // Calculate total discount value saved (estimate)
        const percentageDiscounts = discounts.filter(d => d.discount_type === 'PERCENTAGE');
        const avgPercentage = percentageDiscounts.length > 0
            ? percentageDiscounts.reduce((sum, d) => sum + parseFloat(d.discount_value || '0'), 0) / percentageDiscounts.length
            : 0;

        return {
            total: discounts.length,
            active: active.length,
            expired: expired.length,
            uniqueCustomers,
            avgPercentage: avgPercentage.toFixed(1),
        };
    }, [discounts]);

    // Filtered discounts
    const filteredDiscounts = useMemo(() => {
        return discounts.filter(d => {
            // Type filter
            if (filterType !== 'all' && d.discount_type !== filterType) {
                return false;
            }
            // Status filter
            if (filterStatus === 'active' && d.is_active === false) {
                return false;
            }
            if (filterStatus === 'expired' && d.is_active !== false) {
                return false;
            }
            return true;
        });
    }, [discounts, filterType, filterStatus]);

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
            return <Badge variant="outline" className="text-amber-600 border-amber-300 bg-amber-50">Expired</Badge>;
        }
        return <Badge variant="outline" className="text-emerald-600 border-emerald-300 bg-emerald-50">Active</Badge>;
    };

    const getTypeBadge = (type: string, display?: string) => {
        const typeColors: Record<string, string> = {
            'PERCENTAGE': 'bg-blue-50 text-blue-700 border-blue-200',
            'MARGIN_OVERRIDE': 'bg-purple-50 text-purple-700 border-purple-200',
            'FLAT_AMOUNT': 'bg-green-50 text-green-700 border-green-200',
            'FIXED_CHARGE': 'bg-orange-50 text-orange-700 border-orange-200',
            'RATE_REDUCTION': 'bg-rose-50 text-rose-700 border-rose-200',
        };
        return (
            <Badge variant="outline" className={typeColors[type] || 'bg-slate-50'}>
                {display || type}
            </Badge>
        );
    };

    return (
        <div className="container mx-auto py-8 max-w-7xl space-y-6">
            {/* Header Section */}
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold flex items-center gap-2 text-slate-900">
                        <Percent className="h-6 w-6 text-primary" />
                        Customer Discounts
                    </h1>
                    <p className="text-muted-foreground mt-1">
                        Manage customer-specific pricing discounts and negotiated rates.
                    </p>
                </div>
                {canManage && (
                    <Button onClick={handleAddNew} className="gap-2">
                        <Plus className="h-4 w-4" />
                        Add Discount
                    </Button>
                )}
            </div>

            {/* Stats Cards */}
            <div className="grid gap-4 md:grid-cols-4">
                <Card className="border-slate-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-lg bg-primary/10">
                                <Tag className="h-5 w-5 text-primary" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Total Discounts</p>
                                <p className="text-2xl font-bold">{stats.total}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-lg bg-emerald-100">
                                <TrendingDown className="h-5 w-5 text-emerald-600" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Active</p>
                                <p className="text-2xl font-bold text-emerald-600">{stats.active}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-lg bg-amber-100">
                                <Clock className="h-5 w-5 text-amber-600" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Expired</p>
                                <p className="text-2xl font-bold text-amber-600">{stats.expired}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
                <Card className="border-slate-200">
                    <CardContent className="pt-6">
                        <div className="flex items-center gap-4">
                            <div className="p-3 rounded-lg bg-blue-100">
                                <Users className="h-5 w-5 text-blue-600" />
                            </div>
                            <div>
                                <p className="text-sm text-muted-foreground">Customers</p>
                                <p className="text-2xl font-bold text-blue-600">{stats.uniqueCustomers}</p>
                            </div>
                        </div>
                    </CardContent>
                </Card>
            </div>

            {/* Main Content */}
            <Card className="border-slate-200 shadow-sm">
                <CardHeader className="border-b bg-slate-50/50">
                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                        <div className="flex items-center gap-4">
                            {/* Search */}
                            <div className="relative">
                                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                                <Input
                                    placeholder="Search customer, product..."
                                    value={searchQuery}
                                    onChange={(e) => setSearchQuery(e.target.value)}
                                    className="pl-9 w-64"
                                />
                            </div>
                            {/* Filters */}
                            <Select value={filterType} onValueChange={setFilterType}>
                                <SelectTrigger className="w-40">
                                    <Filter className="h-4 w-4 mr-2 text-muted-foreground" />
                                    <SelectValue placeholder="Type" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Types</SelectItem>
                                    <SelectItem value="PERCENTAGE">Percentage</SelectItem>
                                    <SelectItem value="MARGIN_OVERRIDE">Margin Override</SelectItem>
                                    <SelectItem value="FLAT_AMOUNT">Flat Amount</SelectItem>
                                    <SelectItem value="RATE_REDUCTION">Rate Reduction</SelectItem>
                                </SelectContent>
                            </Select>
                            <Select value={filterStatus} onValueChange={setFilterStatus}>
                                <SelectTrigger className="w-32">
                                    <SelectValue placeholder="Status" />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="all">All Status</SelectItem>
                                    <SelectItem value="active">Active</SelectItem>
                                    <SelectItem value="expired">Expired</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <Button variant="outline" size="icon" onClick={fetchDiscounts} className="shrink-0">
                            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
                        </Button>
                    </div>
                </CardHeader>
                <CardContent className="p-0">
                    {error && <p className="p-4 text-sm text-red-600">{error}</p>}

                    <Table>
                        <TableHeader>
                            <TableRow className="bg-muted/30 hover:bg-muted/30">
                                <TableHead className="font-semibold">Customer</TableHead>
                                <TableHead className="font-semibold">Product Code</TableHead>
                                <TableHead className="font-semibold">Type</TableHead>
                                <TableHead className="text-right font-semibold">Value</TableHead>
                                <TableHead className="font-semibold">Valid Until</TableHead>
                                <TableHead className="font-semibold">Status</TableHead>
                                {canManage && <TableHead className="text-right font-semibold">Actions</TableHead>}
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {loading ? (
                                <TableRow>
                                    <TableCell colSpan={canManage ? 7 : 6} className="h-24 text-center text-muted-foreground">
                                        <div className="flex items-center justify-center gap-2">
                                            <RefreshCw className="h-4 w-4 animate-spin" />
                                            Loading discounts...
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ) : filteredDiscounts.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={canManage ? 7 : 6} className="h-32 text-center">
                                        <div className="flex flex-col items-center gap-2 text-muted-foreground">
                                            <Percent className="h-8 w-8 opacity-50" />
                                            <p>No discounts found</p>
                                            {canManage && (
                                                <Button variant="outline" size="sm" onClick={handleAddNew} className="mt-2">
                                                    <Plus className="h-4 w-4 mr-2" />
                                                    Add First Discount
                                                </Button>
                                            )}
                                        </div>
                                    </TableCell>
                                </TableRow>
                            ) : (
                                filteredDiscounts.map((discount) => (
                                    <TableRow key={discount.id} className="hover:bg-slate-50/50">
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
                                            {getTypeBadge(discount.discount_type, discount.discount_type_display)}
                                        </TableCell>
                                        <TableCell className="text-right font-semibold tabular-nums">
                                            {formatDiscountValue(discount)}
                                        </TableCell>
                                        <TableCell className="text-muted-foreground">
                                            {discount.valid_until
                                                ? new Date(discount.valid_until).toLocaleDateString()
                                                : '—'
                                            }
                                        </TableCell>
                                        <TableCell>
                                            {getStatusBadge(discount)}
                                        </TableCell>
                                        {canManage && (
                                            <TableCell className="text-right">
                                                <div className="flex items-center justify-end gap-1">
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8"
                                                        onClick={() => handleEdit(discount)}
                                                    >
                                                        <Edit2 className="h-4 w-4" />
                                                    </Button>
                                                    <Button
                                                        variant="ghost"
                                                        size="icon"
                                                        className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                                                        onClick={() => setDeleteTarget(discount)}
                                                    >
                                                        <Trash2 className="h-4 w-4" />
                                                    </Button>
                                                </div>
                                            </TableCell>
                                        )}
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>

                    {/* Footer with count */}
                    {filteredDiscounts.length > 0 && (
                        <div className="px-4 py-3 border-t bg-slate-50/50 text-sm text-muted-foreground">
                            Showing {filteredDiscounts.length} of {discounts.length} discounts
                        </div>
                    )}
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
                        <DialogTitle className="flex items-center gap-2">
                            <Trash2 className="h-5 w-5 text-destructive" />
                            Delete Discount
                        </DialogTitle>
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
