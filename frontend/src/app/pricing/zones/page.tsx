'use client';

import { useState, useEffect } from 'react';
import { getZones, createZone, Zone } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
} from '@/components/ui/table';
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogTrigger,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

export default function ZonesPage() {
    const [zones, setZones] = useState<Zone[]>([]);
    const [loading, setLoading] = useState(true);
    const [isDialogOpen, setIsDialogOpen] = useState(false);
    const [newZone, setNewZone] = useState<Partial<Zone>>({
        code: '',
        name: '',
        mode: 'AIR',
    });

    useEffect(() => {
        loadZones();
    }, []);

    async function loadZones() {
        try {
            const data = await getZones();
            setZones(data);
        } catch (error) {
            console.error(error);
        } finally {
            setLoading(false);
        }
    }

    async function handleCreate() {
        try {
            await createZone(newZone);
            setIsDialogOpen(false);
            loadZones();
            setNewZone({ code: '', name: '', mode: 'AIR' });
        } catch (error) {
            console.error(error);
            alert('Failed to create zone');
        }
    }

    return (
        <div className="container mx-auto py-10">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-3xl font-bold">Zone Management</h1>
                <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
                    <DialogTrigger asChild>
                        <Button>Create Zone</Button>
                    </DialogTrigger>
                    <DialogContent>
                        <DialogHeader>
                            <DialogTitle>Create New Zone</DialogTitle>
                        </DialogHeader>
                        <div className="grid gap-4 py-4">
                            <div className="grid gap-2">
                                <Label>Code</Label>
                                <Input
                                    value={newZone.code}
                                    onChange={(e) => setNewZone({ ...newZone, code: e.target.value })}
                                    placeholder="e.g. AU_EAST"
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label>Name</Label>
                                <Input
                                    value={newZone.name}
                                    onChange={(e) => setNewZone({ ...newZone, name: e.target.value })}
                                    placeholder="e.g. Australia East Coast"
                                />
                            </div>
                            <div className="grid gap-2">
                                <Label>Mode</Label>
                                <Select
                                    value={newZone.mode}
                                    onValueChange={(val) => setNewZone({ ...newZone, mode: val })}
                                >
                                    <SelectTrigger>
                                        <SelectValue />
                                    </SelectTrigger>
                                    <SelectContent>
                                        <SelectItem value="AIR">Air</SelectItem>
                                        <SelectItem value="SEA">Sea</SelectItem>
                                        <SelectItem value="ROAD">Road</SelectItem>
                                    </SelectContent>
                                </Select>
                            </div>
                        </div>
                        <Button onClick={handleCreate}>Save Zone</Button>
                    </DialogContent>
                </Dialog>
            </div>

            <Card>
                <CardHeader>
                    <CardTitle>Existing Zones</CardTitle>
                </CardHeader>
                <CardContent>
                    <Table>
                        <TableHeader>
                            <TableRow>
                                <TableHead>Code</TableHead>
                                <TableHead>Name</TableHead>
                                <TableHead>Mode</TableHead>
                                <TableHead>Members</TableHead>
                            </TableRow>
                        </TableHeader>
                        <TableBody>
                            {loading ? (
                                <TableRow>
                                    <TableCell colSpan={4} className="text-center">
                                        Loading...
                                    </TableCell>
                                </TableRow>
                            ) : zones.length === 0 ? (
                                <TableRow>
                                    <TableCell colSpan={4} className="text-center">
                                        No zones found.
                                    </TableCell>
                                </TableRow>
                            ) : (
                                zones.map((zone) => (
                                    <TableRow key={zone.id}>
                                        <TableCell className="font-medium">{zone.code}</TableCell>
                                        <TableCell>{zone.name}</TableCell>
                                        <TableCell>{zone.mode}</TableCell>
                                        <TableCell>{zone.members?.length || 0} locations</TableCell>
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
