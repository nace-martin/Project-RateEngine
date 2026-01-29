'use client';

import { useState, useEffect } from 'react';
import { getRateCardsV3, RateCard } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import { Button } from '@/components/ui/button';
import Link from 'next/link';

export default function RateCardsPage() {
    const [rateCards, setRateCards] = useState<RateCard[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadRateCards();
    }, []);

    async function loadRateCards() {
        try {
            const cards = await getRateCardsV3();
            setRateCards(cards);
        } catch (error) {
            console.error('Failed to load rate cards:', error);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="container mx-auto py-10">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold">Rate Cards</h1>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>All Rate Cards</CardTitle>
                </CardHeader>
                <CardContent>
                    {loading ? (
                        <div className="text-center py-8 text-muted-foreground">Loading...</div>
                    ) : rateCards.length === 0 ? (
                        <div className="text-center py-8 text-muted-foreground">No rate cards found.</div>
                    ) : (
                        <Table>
                            <TableHeader>
                                <TableRow>
                                    <TableHead>Name</TableHead>
                                    <TableHead>Supplier</TableHead>
                                    <TableHead>Mode</TableHead>
                                    <TableHead>Origin Zone</TableHead>
                                    <TableHead>Dest Zone</TableHead>
                                    <TableHead>Valid From</TableHead>
                                    <TableHead>Actions</TableHead>
                                </TableRow>
                            </TableHeader>
                            <TableBody>
                                {rateCards.map((card) => (
                                    <TableRow key={card.id}>
                                        <TableCell className="font-medium">{card.name}</TableCell>
                                        <TableCell>{card.supplier_name || card.supplier}</TableCell>
                                        <TableCell>{card.mode}</TableCell>
                                        <TableCell>{card.origin_zone_name || card.origin_zone}</TableCell>
                                        <TableCell>{card.destination_zone_name || card.destination_zone}</TableCell>
                                        <TableCell>{new Date(card.valid_from).toLocaleDateString()}</TableCell>
                                        <TableCell>
                                            <Button variant="outline" size="sm" asChild>
                                                <Link href={`/pricing/rate-cards/${card.id}`}>View</Link>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))}
                            </TableBody>
                        </Table>
                    )}
                </CardContent>
            </Card>
        </div>
    );
}
