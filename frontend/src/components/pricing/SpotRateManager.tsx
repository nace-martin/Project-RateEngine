'use client';

import React, { useState, useEffect } from 'react';
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    CardDescription,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Plus, Edit, Trash2 } from 'lucide-react';
import {
    getSpotRates,
    deleteSpotRate,
    deleteSpotCharge,
    type SpotRate,
    type SpotCharge,
} from '@/lib/api';
import { CreateSpotRateDialog } from './CreateSpotRateDialog';
import { SpotChargeDialog } from './SpotChargeDialog';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';

interface SpotRateManagerProps {
    quoteId: string;
    originLocationId: string;
    destinationLocationId: string;
    mode: string;
}

export function SpotRateManager({
    quoteId,
    originLocationId,
    destinationLocationId,
    mode,
}: SpotRateManagerProps) {
    const [spotRates, setSpotRates] = useState<SpotRate[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [isCreateDialogOpen, setIsCreateDialogOpen] = useState(false);
    const [isChargeDialogOpen, setIsChargeDialogOpen] = useState(false);
    const [selectedSpotRateId, setSelectedSpotRateId] = useState<string | null>(null);
    const [selectedCharge, setSelectedCharge] = useState<SpotCharge | null>(null);

    const fetchSpotRates = async () => {
        try {
            setLoading(true);
            setError(null);
            const data = await getSpotRates(quoteId);
            setSpotRates(data);
        } catch (err: unknown) {
            console.error(err);
            const message = err instanceof Error ? err.message : 'Failed to load spot rates';
            setError(message);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        fetchSpotRates();
    }, [quoteId]);

    const handleCreateSpotRate = (newSpotRate: SpotRate) => {
        setSpotRates((prev) => [...prev, newSpotRate]);
    };

    const handleDeleteSpotRate = async (id: string) => {
        if (!confirm('Are you sure you want to delete this spot rate and all its charges?')) {
            return;
        }

        try {
            await deleteSpotRate(id);
            setSpotRates((prev) => prev.filter((sr) => sr.id !== id));
        } catch (err: unknown) {
            console.error(err);
            const message = err instanceof Error ? err.message : 'Failed to delete spot rate';
            alert(message);
        }
    };

    const handleAddCharge = (spotRateId: string) => {
        setSelectedSpotRateId(spotRateId);
        setSelectedCharge(null);
        setIsChargeDialogOpen(true);
    };

    const handleEditCharge = (spotRateId: string, charge: SpotCharge) => {
        setSelectedSpotRateId(spotRateId);
        setSelectedCharge(charge);
        setIsChargeDialogOpen(true);
    };

    const handleDeleteCharge = async (chargeId: string) => {
        if (!confirm('Are you sure you want to delete this charge?')) {
            return;
        }

        try {
            await deleteSpotCharge(chargeId);
            // Refresh spot rates to get updated charges
            fetchSpotRates();
        } catch (err: unknown) {
            console.error(err);
            const message = err instanceof Error ? err.message : 'Failed to delete charge';
            alert(message);
        }
    };

    const handleChargeSuccess = () => {
        fetchSpotRates();
    };

    if (loading) {
        return (
            <Card>
                <CardContent className="py-8 text-center text-muted-foreground">
                    Loading spot rates...
                </CardContent>
            </Card>
        );
    }

    return (
        <>
            <Card>
                <CardHeader>
                    <div className="flex items-center justify-between">
                        <div>
                            <CardTitle>Spot Rates</CardTitle>
                            <CardDescription>
                                Manual spot rates for this quote from specific suppliers
                            </CardDescription>
                        </div>
                        <Button onClick={() => setIsCreateDialogOpen(true)}>
                            <Plus className="w-4 h-4 mr-2" />
                            Add Spot Rate
                        </Button>
                    </div>
                </CardHeader>
                <CardContent>
                    {error && (
                        <Alert variant="destructive" className="mb-4">
                            <AlertTitle>Error</AlertTitle>
                            <AlertDescription>{error}</AlertDescription>
                        </Alert>
                    )}

                    {spotRates.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">
                            No spot rates added yet. Click &quot;Add Spot Rate&quot; to begin.
                        </div>
                    ) : (
                        <div className="space-y-6">
                            {spotRates.map((spotRate) => (
                                <div key={spotRate.id} className="border rounded-lg p-4">
                                    <div className="flex items-start justify-between mb-4">
                                        <div>
                                            <div className="flex items-center gap-2">
                                                <h3 className="text-lg font-semibold">
                                                    {spotRate.supplier_name || 'Supplier'}
                                                </h3>
                                                <Badge variant="outline">{spotRate.currency}</Badge>
                                            </div>
                                            <p className="text-sm text-muted-foreground">
                                                {spotRate.origin_location_name || spotRate.origin_location} →{' '}
                                                {spotRate.destination_location_name || spotRate.destination_location}
                                            </p>
                                            {spotRate.valid_until && (
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    Valid until: {spotRate.valid_until}
                                                </p>
                                            )}
                                            {spotRate.notes && (
                                                <p className="text-xs text-muted-foreground mt-1">
                                                    {spotRate.notes}
                                                </p>
                                            )}
                                        </div>
                                        <div className="flex gap-2">
                                            <Button
                                                variant="outline"
                                                size="sm"
                                                onClick={() => handleAddCharge(spotRate.id)}
                                            >
                                                <Plus className="w-4 h-4 mr-1" />
                                                Add Charge
                                            </Button>
                                            <Button
                                                variant="ghost"
                                                size="sm"
                                                onClick={() => handleDeleteSpotRate(spotRate.id)}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </Button>
                                        </div>
                                    </div>

                                    {spotRate.charges && spotRate.charges.length > 0 ? (
                                        <Table>
                                            <TableHeader>
                                                <TableRow>
                                                    <TableHead>Component</TableHead>
                                                    <TableHead>Method</TableHead>
                                                    <TableHead className="text-right">Rate</TableHead>
                                                    <TableHead className="text-right">Min Charge</TableHead>
                                                    <TableHead className="text-right">Actions</TableHead>
                                                </TableRow>
                                            </TableHeader>
                                            <TableBody>
                                                {spotRate.charges.map((charge) => (
                                                    <TableRow key={charge.id}>
                                                        <TableCell>
                                                            <div className="font-medium">{charge.component_code}</div>
                                                            {charge.description && (
                                                                <div className="text-xs text-muted-foreground">
                                                                    {charge.description}
                                                                </div>
                                                            )}
                                                        </TableCell>
                                                        <TableCell>
                                                            <Badge variant="outline">{charge.method}</Badge>
                                                            {charge.unit && (
                                                                <span className="ml-2 text-xs text-muted-foreground">
                                                                    / {charge.unit}
                                                                </span>
                                                            )}
                                                        </TableCell>
                                                        <TableCell className="text-right">
                                                            {charge.method === 'PERCENT'
                                                                ? `${Number(charge.percent_value) * 100}%`
                                                                : charge.rate}
                                                        </TableCell>
                                                        <TableCell className="text-right">{charge.min_charge}</TableCell>
                                                        <TableCell className="text-right">
                                                            <div className="flex justify-end gap-2">
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    onClick={() => handleEditCharge(spotRate.id, charge)}
                                                                >
                                                                    <Edit className="w-4 h-4" />
                                                                </Button>
                                                                <Button
                                                                    variant="ghost"
                                                                    size="sm"
                                                                    onClick={() => charge.id && handleDeleteCharge(charge.id)}
                                                                >
                                                                    <Trash2 className="w-4 h-4 text-destructive" />
                                                                </Button>
                                                            </div>
                                                        </TableCell>
                                                    </TableRow>
                                                ))}
                                            </TableBody>
                                        </Table>
                                    ) : (
                                        <div className="text-sm text-muted-foreground text-center py-4 border-t">
                                            No charges added yet
                                        </div>
                                    )}
                                </div>
                            ))}
                        </div>
                    )}
                </CardContent>
            </Card>

            <CreateSpotRateDialog
                isOpen={isCreateDialogOpen}
                onClose={() => setIsCreateDialogOpen(false)}
                onSuccess={handleCreateSpotRate}
                quoteId={quoteId}
                originLocationId={originLocationId}
                destinationLocationId={destinationLocationId}
                mode={mode}
            />

            {selectedSpotRateId && (
                <SpotChargeDialog
                    isOpen={isChargeDialogOpen}
                    onClose={() => setIsChargeDialogOpen(false)}
                    onSuccess={handleChargeSuccess}
                    spotRateId={selectedSpotRateId}
                    initialData={selectedCharge}
                />
            )}
        </>
    );
}
