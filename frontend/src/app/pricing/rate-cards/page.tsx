'use client';

import { useState, useEffect } from 'react';
import { getRateCardsV3, RateCard } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import Link from 'next/link';

export default function RateCardsPage() {
    const [cards, setCards] = useState<RateCard[]>([]);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        loadCards();
    }, []);

    async function loadCards() {
        try {
            const data = await getRateCardsV3();
            setCards(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    }

    return (
        <div className="container mx-auto py-10">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold">Rate Cards</h1>
                <Button asChild>
                    <Link href="/pricing/rate-cards/new">Create Rate Card</Link>
                </Button>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>All Rate Cards</CardTitle>
                </CardHeader>
                <CardContent>
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
                            {loading ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center">
                                        Loading...
                                    </TableCell>
                                </TableRow>
                            ) : cards.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={7} className="text-center">
                                        No rate cards found.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                cards.map((card) => (
                                    <TableRow key={card.id}>
                                        <TableCell className="font-medium">{card.name}</TableCell>
                                        <TableCell>{card.supplier_name || card.supplier}</TableCell>
                                        <TableCell>{card.mode}</TableCell>
                                        <TableCell>{card.origin_zone}</TableCell>
                                        <TableCell>{card.destination_zone}</TableCell>
                                        <TableCell>{new Date(card.valid_from).toLocaleDateString()}</TableCell>
                                        <TableCell>
                                            <Button variant="outline" size="sm" asChild>
                                                <Link href={`/pricing/rate-cards/${card.id}`}>Edit</Link>
                                            </Button>
                                        </TableCell>
                                    </TableRow>
                                ))
                            )}
                        </TableBody>
                    </Table>
                </CardContent>
            </Card>
        </div>
    );
}
