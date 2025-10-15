'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { listStations, createQuoteVersion } from '@/lib/api';
import { useAuth } from '@/context/auth-context';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface Station {
  id: number;
  iata_code: string;
}

interface Piece {
  length_cm: number;
  width_cm: number;
  height_cm: number;
  weight_kg: number;
  count: number;
}

interface Charge {
  stage: string;
  code: string;
  description: string;
  basis: string;
  qty: number;
  unit_price: number;
  side: string;
  currency: string;
}

export default function NewQuoteVersionPage() {
    const params = useParams();
    const router = useRouter();
    const { token } = useAuth();
    const quotationId = typeof params.id === 'string' ? params.id : Array.isArray(params.id) ? params.id[0] : undefined;

    const [stations, setStations] = useState<Station[]>([]);
    const [origin, setOrigin] = useState('');
    const [destination, setDestination] = useState('');
    const [pieces, setPieces] = useState<Piece[]>([{ length_cm: 0, width_cm: 0, height_cm: 0, weight_kg: 0, count: 1 }]);
    const [charges, setCharges] = useState<Charge[]>([{ stage: 'AIR', code: 'FREIGHT', description: 'Air Freight', basis: 'PER_KG', qty: 1, unit_price: 0, side: 'BUY', currency: 'PGK' }]);
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        if (!token) {
            return;
        }
        const authToken = token;
        async function fetchStations() {
            try {
                const stationData = await listStations(authToken);
                setStations(stationData);
            } catch (error) {
                setError('Failed to load stations');
            }
        }
        fetchStations();
    }, [token]);

    const handleAddPiece = () => {
        setPieces([...pieces, { length_cm: 0, width_cm: 0, height_cm: 0, weight_kg: 0, count: 1 }]);
    };

    const handleRemovePiece = (index: number) => {
        const newPieces = pieces.filter((_, i) => i !== index);
        setPieces(newPieces);
    };

    const handlePieceChange = (index: number, field: keyof Piece, value: any) => {
        const newPieces = [...pieces];
        newPieces[index][field] = value;
        setPieces(newPieces);
    };

    const handleAddCharge = () => {
        setCharges([...charges, { stage: 'AIR', code: '', description: '', basis: 'FLAT', qty: 1, unit_price: 0, side: 'BUY', currency: 'PGK' }]);
    };

    const handleRemoveCharge = (index: number) => {
        const newCharges = charges.filter((_, i) => i !== index);
        setCharges(newCharges);
    };

    const handleChargeChange = (
        index: number,
        field: keyof Charge,
        value: Charge[keyof Charge]
    ) => {
        const newCharges = [...charges];
        newCharges[index] = { ...newCharges[index], [field]: value } as Charge;
        setCharges(newCharges);
    };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        if (!token || !quotationId) {
            setError('Authentication error. Please sign in again.');
            setIsLoading(false);
            return;
        }
        const authToken = token;

        const versionData = {
            origin: parseInt(origin, 10),
            destination: parseInt(destination, 10),
            pieces,
            charges,
            // These fields are required by the model, but not part of this form.
            // We can add them later or set defaults in the backend.
            volumetric_divisor: 6000,
            volumetric_weight_kg: 0,
            chargeable_weight_kg: 0,
            sell_currency: 'PGK',
            valid_from: new Date().toISOString().split('T')[0],
            valid_to: new Date().toISOString().split('T')[0],
        };

        try {
            await createQuoteVersion(authToken, quotationId, versionData);
            router.push(`/quotes/${quotationId}`);
        } catch (error: any) {
            setError(error.message || 'Failed to save quote version');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="container mx-auto p-4">
            <Card>
                <CardHeader>
                    <CardTitle>Add New Version for Quotation #{quotationId}</CardTitle>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div className="grid grid-cols-2 gap-4">
                            <div>
                                <Label htmlFor="origin">Origin</Label>
                                <Select onValueChange={setOrigin} value={origin} required>
                                    <SelectTrigger id="origin"><SelectValue placeholder="Select origin" /></SelectTrigger>
                                    <SelectContent>
                                        {stations.map((s) => (
                                            <SelectItem key={s.id} value={String(s.id)}>{s.iata_code}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                            <div>
                                <Label htmlFor="destination">Destination</Label>
                                <Select onValueChange={setDestination} value={destination} required>
                                    <SelectTrigger id="destination"><SelectValue placeholder="Select destination" /></SelectTrigger>
                                    <SelectContent>
                                        {stations.map((s) => (
                                            <SelectItem key={s.id} value={String(s.id)}>{s.iata_code}</SelectItem>
                                        ))}
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>

                        <div>
                            <Label>Pieces</Label>
                            {pieces.map((piece, index) => (
                                <div key={index} className="flex items-center gap-2 p-2 border rounded-md">
                                    <Input type="number" placeholder="L (cm)" value={piece.length_cm} onChange={(e) => handlePieceChange(index, 'length_cm', e.target.value)} />
                                    <Input type="number" placeholder="W (cm)" value={piece.width_cm} onChange={(e) => handlePieceChange(index, 'width_cm', e.target.value)} />
                                    <Input type="number" placeholder="H (cm)" value={piece.height_cm} onChange={(e) => handlePieceChange(index, 'height_cm', e.target.value)} />
                                    <Input type="number" placeholder="Weight (kg)" value={piece.weight_kg} onChange={(e) => handlePieceChange(index, 'weight_kg', e.target.value)} required />
                                    <Input type="number" placeholder="Count" value={piece.count} onChange={(e) => handlePieceChange(index, 'count', e.target.value)} required />
                                    <Button type="button" variant="destructive" size="sm" onClick={() => handleRemovePiece(index)}>Remove</Button>
                                </div>
                            ))}
                            <Button type="button" variant="outline" size="sm" onClick={handleAddPiece} className="mt-2">Add Piece</Button>
                        </div>

                        <div>
                            <Label>Charges</Label>
                            {charges.map((charge, index) => (
                                <div key={index} className="grid grid-cols-5 gap-2 p-2 border rounded-md">
                                    <Input placeholder="Description" value={charge.description} onChange={(e) => handleChargeChange(index, 'description', e.target.value)} required />
                                    <Input
                                        type="number"
                                        placeholder="Unit Price"
                                        value={charge.unit_price}
                                        onChange={(e) =>
                                            handleChargeChange(
                                                index,
                                                'unit_price',
                                                Number(e.target.value) || 0
                                            )
                                        }
                                        required
                                    />
                                    <Select
                                        onValueChange={(value) =>
                                            handleChargeChange(index, 'side', value)
                                        }
                                        value={charge.side}
                                    >
                                        <SelectTrigger><SelectValue /></SelectTrigger>
                                        <SelectContent>
                                            <SelectItem value="BUY">Buy</SelectItem>
                                            <SelectItem value="SELL">Sell</SelectItem>
                                        </SelectContent>
                                    </Select>
                                    <Input placeholder="Currency" value={charge.currency} onChange={(e) => handleChargeChange(index, 'currency', e.target.value.toUpperCase())} maxLength={3} required />
                                    <Button type="button" variant="destructive" size="sm" onClick={() => handleRemoveCharge(index)}>Remove</Button>
                                </div>
                            ))}
                            <Button type="button" variant="outline" size="sm" onClick={handleAddCharge} className="mt-2">Add Charge</Button>
                        </div>

                        {error && <p className="text-red-500">{error}</p>}

                        <Button type="submit" disabled={isLoading} className="w-full">
                            {isLoading ? 'Saving...' : 'Calculate & Save Version'}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
