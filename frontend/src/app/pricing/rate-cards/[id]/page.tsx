'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { getRateCardV3, RateCard } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { RateLineDialog } from '@/components/pricing/RateLineDialog';
import { RateLine } from '@/lib/api';
import { ImportRatesDialog } from '@/components/pricing/ImportRatesDialog';
import { Upload, ArrowLeft, Edit, Plus } from 'lucide-react';
import { Badge } from '@/components/ui/badge';

export default function RateCardDetailPage() {
    const params = useParams();
    const router = useRouter();
    const id = params.id as string;
    const [rateCard, setRateCard] = useState<RateCard | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Dialog State
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [selectedLine, setSelectedLine] = useState<RateLine | null>(null);
    const [isImportOpen, setIsImportOpen] = useState(false);

    const fetchCard = useCallback(async () => {
        try {
            setLoading(true);
            const data = await getRateCardV3(id);
            setRateCard(data);
        } catch (err) {
            setError('Failed to load rate card details.');
            console.error(err);
        } finally {
            setLoading(false);
        }
    }, [id]);

    useEffect(() => {
        fetchCard();
    }, [fetchCard]);

    const handleAddLine = () => {
        setSelectedLine(null);
        setIsDialogOpen(true);
    };

    const handleEditLine = (line: RateLine) => {
        setSelectedLine(line);
        setIsDialogOpen(true);
    };

    const handleSaveLine = () => {
        fetchCard(); // Refresh data
    };

    if (loading && !rateCard) return <div className="p-8">Loading...</div>;
    if (error || !rateCard) return <div className="p-8 text-red-500">{error || 'Rate card not found'}</div>;

    return (
        <div className="container mx-auto py-8 space-y-6">
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-4">
                    <Button variant="ghost" onClick={() => router.back()}>
                        <ArrowLeft className="w-4 h-4 mr-2" />
                        Back
                    </Button>
                    <h1 className="text-3xl font-bold tracking-tight">{rateCard.name}</h1>
                </div>
                <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setIsImportOpen(true)}>
                        <Upload className="w-4 h-4 mr-2" />
                        Import CSV
                    </Button>
                    <Button variant="outline">
                        <Edit className="w-4 h-4 mr-2" />
                        Edit Details
                    </Button>
                    <Button onClick={handleAddLine}>
                        <Plus className="w-4 h-4 mr-2" />
                        Add Line
                    </Button>
                </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                <Card className="md:col-span-2">
                    <CardHeader>
                        <CardTitle>Rate Lines</CardTitle>
                    </CardHeader>
                    <CardContent>
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Component</TableHead>
                                    <TableHead>Method</TableHead>
                                    <TableHead>Min Charge</TableHead>
                                    <TableHead>Rates / Breaks</TableHead>
                                    <TableHead>Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rateCard.lines?.map((line) => (
                                    <TableRow key={line.id}>
                                        <TableCell className="font-medium">
                                            {line.component_code}
                                            {line.description && (
                                                <div className="text-xs text-muted-foreground">{line.description}</div>
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <Badge variant="outline">{line.method}</Badge>
                                            {line.unit && <span className="ml-2 text-xs text-muted-foreground">/ {line.unit}</span>}
                                        </TableCell>
                                        <TableCell>
                                            {line.min_charge > 0 ? `${rateCard.currency} ${line.min_charge}` : '-'}
                                        </TableCell>
                                        <TableCell>
                                            {line.method === 'WEIGHT_BREAK' ? (
                                                <div className="space-y-1 text-sm">
                                                    {line.breaks.map((b) => (
                                                        <div key={b.id} className="flex justify-between w-48">
                                                            <span>{b.from_value} - {b.to_value || 'Max'}:</span>
                                                            <span className="font-mono">{b.rate}</span>
                                                        </div>
                                                    ))}
                                                </div>
                                            ) : line.method === 'PERCENT' ? (
                                                <span>{Number(line.percent_value) * 100}% of {line.percent_of_component}</span>
                                            ) : (
                                                // For FLAT or PER_UNIT, check breaks if rate is there
                                                line.breaks.length > 0 ? (
                                                    <span>{line.breaks[0].rate}</span>
                                                ) : '-'
                                            )}
                                        </TableCell>
                                        <TableCell>
                                            <Button variant="ghost" size="sm" onClick={() => handleEditLine(line)}>Edit</Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                                {!rateCard.lines?.length && (
                                    <TableRow>
                                        <TableCell colSpan={5} className="text-center py-8 text-muted-foreground">
                                            No rate lines found.
                                        </TableCell>
                                    </TableRow>
                                )}
                            </TableBody>
                        </Table>
                    </CardContent>
                </Card>

                <div className="space-y-6">
                    <Card>
                        <CardHeader>
                            <CardTitle>Configuration</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Supplier</div>
                                <div>{rateCard.supplier_name}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Mode</div>
                                <div>{rateCard.mode}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Currency</div>
                                <div>{rateCard.currency}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Scope</div>
                                <div>{rateCard.scope}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Priority</div>
                                <div>{rateCard.priority}</div>
                            </div>
                        </CardContent>
                    </Card>

                    <Card>
                        <CardHeader>
                            <CardTitle>Validity</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Valid From</div>
                                <div>{rateCard.valid_from || 'N/A'}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Valid Until</div>
                                <div>{rateCard.valid_until || 'Indefinite'}</div>
                            </div>
                        </CardContent>
                    </Card>
                    <Card>
                        <CardHeader>
                            <CardTitle>Zones</CardTitle>
                        </CardHeader>
                        <CardContent className="space-y-4">
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Origin</div>
                                <div>{rateCard.origin_zone_name || rateCard.origin_zone}</div>
                            </div>
                            <div>
                                <div className="text-sm font-medium text-muted-foreground">Destination</div>
                                <div>{rateCard.destination_zone_name || rateCard.destination_zone}</div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </div>

            <RateLineDialog
                isOpen={isDialogOpen}
                onClose={() => setIsDialogOpen(false)}
                onSave={handleSaveLine}
                cardId={id}
                initialData={selectedLine}
            />

            <ImportRatesDialog
                isOpen={isImportOpen}
                onClose={() => setIsImportOpen(false)}
                onSuccess={handleSaveLine}
                cardId={id}
            />
        </div>
    );
}
