'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { createRateCardV3, searchCompanies, searchLocations } from '@/lib/api';
import { CompanySearchResult, LocationSearchResult } from '@/lib/types';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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
import { Check, ChevronsUpDown } from 'lucide-react';
import {
    Command,
    CommandEmpty,
    CommandGroup,
    CommandInput,
    CommandItem,
} from "@/components/ui/command"
import {
    Popover,
    PopoverContent,
    PopoverTrigger,
} from "@/components/ui/popover"
import { useToast } from '@/context/toast-context';
import { useConfirm } from '@/hooks/useConfirm';
import { useAsyncAction } from '@/hooks/useAsyncAction';
import { cn } from "@/lib/utils"
import PageActionBar from '@/components/navigation/PageActionBar';
import PageBackButton from '@/components/navigation/PageBackButton';
import PageCancelButton from '@/components/navigation/PageCancelButton';
import { useUnsavedChangesGuard } from '@/hooks/useUnsavedChangesGuard';
import { useReturnTo } from '@/hooks/useReturnTo';
export default function CreateRateCardPage() {
    const router = useRouter();
    const { toast } = useToast();
    const confirm = useConfirm();
    const [suppliers, setSuppliers] = useState<CompanySearchResult[]>([]);

    // Form State
    const [name, setName] = useState('');
    const [supplierId, setSupplierId] = useState('');
    const [supplierSearchOpen, setSupplierSearchOpen] = useState(false);
    const [mode, setMode] = useState('AIR');

    // Location State
    const [originLocationId, setOriginLocationId] = useState('');
    const [destinationLocationId, setDestinationLocationId] = useState('');
    const [originSearchOpen, setOriginSearchOpen] = useState(false);
    const [destinationSearchOpen, setDestinationSearchOpen] = useState(false);
    const [originLocations, setOriginLocations] = useState<LocationSearchResult[]>([]);
    const [destinationLocations, setDestinationLocations] = useState<LocationSearchResult[]>([]);
    const [currency, setCurrency] = useState('AUD');
    const [scope, setScope] = useState('BUY');
    const [priority, setPriority] = useState('100');
    const [validFrom, setValidFrom] = useState('');
    const isDirty = useMemo(
        () => Boolean(name || supplierId || originLocationId || destinationLocationId || mode !== 'AIR' || currency !== 'AUD' || scope !== 'BUY' || priority !== '100' || validFrom),
        [name, supplierId, originLocationId, destinationLocationId, mode, currency, scope, priority, validFrom]
    );
    const canCreateRateCard = Boolean(name.trim() && supplierId && originLocationId && destinationLocationId);
    useUnsavedChangesGuard(isDirty);
    const returnTo = useReturnTo();
    const confirmLeave = async () => {
        if (!isDirty) {
            return true;
        }
        return confirm({
            title: 'Discard rate card draft?',
            description: 'You have unsaved rate card details. Leaving now will discard them.',
            confirmLabel: 'Discard draft',
            cancelLabel: 'Stay here',
            variant: 'destructive',
        });
    };

    useEffect(() => {
        async function loadData() {
            try {
                // Pre-load some suppliers and locations? Or search on demand.
                const s = await searchCompanies('');
                setSuppliers(s);
                const l = await searchLocations('');
                setOriginLocations(l);
                setDestinationLocations(l);
            } catch (err) {
                console.error(err);
            }
        }
        loadData();
    }, []);

    const createRateCardAction = useAsyncAction(async () => {
            const payload = {
                name,
                supplier: supplierId,
                mode,
                origin_location_id: originLocationId,
                destination_location_id: destinationLocationId,
                currency,
                scope,
                priority: parseInt(priority),
                valid_from: validFrom || new Date().toISOString().split('T')[0],
            };

            return createRateCardV3(payload);
        }, {
            onSuccess: async (newCard) => {
                toast({
                    title: 'Rate card created',
                    description: 'The new rate card is ready for editing.',
                    variant: 'success',
                });
                router.push(`/pricing/rate-cards/${newCard.id}`);
            },
        });
    const saving = createRateCardAction.isRunning;
    const error = createRateCardAction.error;
    const handleSave = () => {
        void createRateCardAction.run().catch(() => undefined);
    };

    return (
        <div className="container mx-auto py-8 space-y-6">
            <div>
                <PageBackButton fallbackHref="/pricing/rate-cards" returnTo={returnTo} isDirty={isDirty} confirmLeave={confirmLeave} disabled={saving} />
                <h1 className="text-3xl font-bold tracking-tight">Create Rate Card</h1>
            </div>

            <Card className="max-w-2xl">
                <CardHeader>
                    <CardTitle>Rate Card Details</CardTitle>
                </CardHeader>
                <CardContent className={`space-y-4 ${saving ? "pointer-events-none opacity-70" : ""}`}>
                    <div className="space-y-2">
                        <Label>Name</Label>
                        <Input value={name} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setName(e.target.value)} placeholder="e.g. EFM AU - BNE to POM" />
                    </div>

                    <div className="space-y-2 flex flex-col">
                        <Label>Supplier</Label>
                        <Popover open={supplierSearchOpen} onOpenChange={setSupplierSearchOpen}>
                            <PopoverTrigger asChild>
                                <Button
                                    variant="outline"
                                    role="combobox"
                                    aria-expanded={supplierSearchOpen}
                                    className="justify-between"
                                >
                                    {supplierId
                                        ? suppliers.find((s) => s.id.toString() === supplierId)?.name
                                        : "Select supplier..."}
                                    <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                </Button>
                            </PopoverTrigger>
                            <PopoverContent className="w-[400px] p-0">
                                <Command>
                                    <CommandInput placeholder="Search supplier..." />
                                    <CommandEmpty>No supplier found.</CommandEmpty>
                                    <CommandGroup>
                                        {suppliers.map((supplier) => (
                                            <CommandItem
                                                key={supplier.id}
                                                value={supplier.name}
                                                onSelect={() => {
                                                    setSupplierId(supplier.id.toString())
                                                    setSupplierSearchOpen(false)
                                                }}
                                            >
                                                <Check
                                                    className={cn(
                                                        "mr-2 h-4 w-4",
                                                        supplierId === supplier.id.toString() ? "opacity-100" : "opacity-0"
                                                    )}
                                                />
                                                {supplier.name}
                                            </CommandItem>
                                        ))}
                                    </CommandGroup>
                                </Command>
                            </PopoverContent>
                        </Popover>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Mode</Label>
                            <Select value={mode} onValueChange={setMode}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="AIR">Air</SelectItem>
                                    <SelectItem value="OCEAN">Ocean</SelectItem>
                                    <SelectItem value="ROAD">Road</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Scope</Label>
                            <Select value={scope} onValueChange={setScope}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="BUY">Buy (Cost)</SelectItem>
                                    <SelectItem value="SELL">Sell (Price)</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2 flex flex-col">
                            <Label>Origin Location</Label>
                            <Popover open={originSearchOpen} onOpenChange={setOriginSearchOpen}>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        role="combobox"
                                        aria-expanded={originSearchOpen}
                                        className="justify-between"
                                    >
                                        {originLocationId
                                            ? originLocations.find((l) => l.id === originLocationId)?.display_name
                                            : "Select Origin..."}
                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-[300px] p-0">
                                    <Command>
                                        <CommandInput placeholder="Search origin..." onValueChange={async (val) => {
                                            const res = await searchLocations(val);
                                            setOriginLocations(res);
                                        }} />
                                        <CommandEmpty>No location found.</CommandEmpty>
                                        <CommandGroup>
                                            {originLocations.map((loc) => (
                                                <CommandItem
                                                    key={loc.id}
                                                    value={loc.display_name}
                                                    onSelect={() => {
                                                        setOriginLocationId(loc.id)
                                                        setOriginSearchOpen(false)
                                                    }}
                                                >
                                                    <Check
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            originLocationId === loc.id ? "opacity-100" : "opacity-0"
                                                        )}
                                                    />
                                                    {loc.display_name} ({loc.code})
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </Command>
                                </PopoverContent>
                            </Popover>
                        </div>
                        <div className="space-y-2 flex flex-col">
                            <Label>Destination Location</Label>
                            <Popover open={destinationSearchOpen} onOpenChange={setDestinationSearchOpen}>
                                <PopoverTrigger asChild>
                                    <Button
                                        variant="outline"
                                        role="combobox"
                                        aria-expanded={destinationSearchOpen}
                                        className="justify-between"
                                    >
                                        {destinationLocationId
                                            ? destinationLocations.find((l) => l.id === destinationLocationId)?.display_name
                                            : "Select Destination..."}
                                        <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
                                    </Button>
                                </PopoverTrigger>
                                <PopoverContent className="w-[300px] p-0">
                                    <Command>
                                        <CommandInput placeholder="Search destination..." onValueChange={async (val) => {
                                            const res = await searchLocations(val);
                                            setDestinationLocations(res);
                                        }} />
                                        <CommandEmpty>No location found.</CommandEmpty>
                                        <CommandGroup>
                                            {destinationLocations.map((loc) => (
                                                <CommandItem
                                                    key={loc.id}
                                                    value={loc.display_name}
                                                    onSelect={() => {
                                                        setDestinationLocationId(loc.id)
                                                        setDestinationSearchOpen(false)
                                                    }}
                                                >
                                                    <Check
                                                        className={cn(
                                                            "mr-2 h-4 w-4",
                                                            destinationLocationId === loc.id ? "opacity-100" : "opacity-0"
                                                        )}
                                                    />
                                                    {loc.display_name} ({loc.code})
                                                </CommandItem>
                                            ))}
                                        </CommandGroup>
                                    </Command>
                                </PopoverContent>
                            </Popover>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-4">
                        <div className="space-y-2">
                            <Label>Currency</Label>
                            <Select value={currency} onValueChange={setCurrency}>
                                <SelectTrigger>
                                    <SelectValue />
                                </SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="AUD">AUD</SelectItem>
                                    <SelectItem value="PGK">PGK</SelectItem>
                                    <SelectItem value="USD">USD</SelectItem>
                                    <SelectItem value="EUR">EUR</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>
                        <div className="space-y-2">
                            <Label>Priority</Label>
                            <Input type="number" value={priority} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPriority(e.target.value)} />
                        </div>
                    </div>

                    <div className="space-y-2">
                        <Label>Valid From</Label>
                        <Input type="date" value={validFrom} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setValidFrom(e.target.value)} />
                    </div>

                </CardContent>
            </Card>

            {error ? (
                <Alert variant="destructive" className="max-w-2xl">
                    <AlertDescription>{error}</AlertDescription>
                </Alert>
            ) : null}

            <PageActionBar className="max-w-2xl">
                <PageCancelButton
                    href={returnTo || "/pricing/rate-cards"}
                    isDirty={isDirty}
                    confirmLeave={confirmLeave}
                    confirmMessage="Discard this new rate card?"
                    disabled={saving}
                />
                <Button onClick={handleSave} disabled={saving || !canCreateRateCard} loading={saving} loadingText="Creating rate card...">
                    Create Rate Card
                </Button>
            </PageActionBar>
        </div>
    );
}
