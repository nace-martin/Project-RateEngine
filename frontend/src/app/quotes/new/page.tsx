'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { listCustomers, createQuotation } from '@/lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface Customer {
  id: number;
  name: string;
}

export default function NewQuotationPage() {
    const router = useRouter();
    const [customers, setCustomers] = useState<Customer[]>([]);
    const [customer, setCustomer] = useState('');
    const [serviceType, setServiceType] = useState('IMPORT');
    const [incoterms, setIncoterms] = useState('FOB');
    const [scope, setScope] = useState('A2A');
    const [paymentTerm, setPaymentTerm] = useState('PREPAID');
    const [sellCurrency, setSellCurrency] = useState('PGK');
    const [isLoading, setIsLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchCustomers() {
            try {
                const customerData = await listCustomers();
                setCustomers(customerData);
            } catch (error) { 
                setError('Failed to load customers');
            }
        }
        fetchCustomers();
    }, []);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setIsLoading(true);
        setError(null);

        const quotationData = {
            customer: parseInt(customer, 10),
            service_type: serviceType,
            terms: incoterms,
            scope,
            payment_term: paymentTerm,
            sell_currency: sellCurrency,
            reference: `QT-${Date.now()}`,
            date: new Date().toISOString().split('T')[0],
        };

        try {
            const newQuotation = await createQuotation(quotationData);
            router.push(`/quotes/${newQuotation.id}/versions/new`);
        } catch (error: any) {
            setError(error.message || 'Failed to create quotation');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="container mx-auto p-4">
            <Card>
                <CardHeader>
                    <CardTitle>Create a New Quotation</CardTitle>
                </CardHeader>
                <CardContent>
                    <form onSubmit={handleSubmit} className="space-y-4">
                        <div>
                            <Label htmlFor="customer">Customer</Label>
                            <Select onValueChange={setCustomer} value={customer} required>
                                <SelectTrigger id="customer"><SelectValue placeholder="Select a customer" /></SelectTrigger>
                                <SelectContent>
                                    {customers.map((c) => (
                                        <SelectItem key={c.id} value={String(c.id)}>{c.name}</SelectItem>
                                    ))}
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <Label htmlFor="serviceType">Service Type</Label>
                            <Select onValueChange={setServiceType} value={serviceType}>
                                <SelectTrigger id="serviceType"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="IMPORT">Import</SelectItem>
                                    <SelectItem value="EXPORT">Export</SelectItem>
                                    <SelectItem value="DOMESTIC">Domestic</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <Label htmlFor="incoterms">Incoterms</Label>
                            <Select onValueChange={setIncoterms} value={incoterms}>
                                <SelectTrigger id="incoterms"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="EXW">EXW</SelectItem>
                                    <SelectItem value="FOB">FOB</SelectItem>
                                    <SelectItem value="CIP">CIP</SelectItem>
                                    <SelectItem value="CPT">CPT</SelectItem>
                                    <SelectItem value="DAP">DAP</SelectItem>
                                    <SelectItem value="DDP">DDP</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <Label htmlFor="scope">Scope</Label>
                            <Select onValueChange={setScope} value={scope}>
                                <SelectTrigger id="scope"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="D2D">Door–Door</SelectItem>
                                    <SelectItem value="D2A">Door–Airport</SelectItem>
                                    <SelectItem value="A2D">Airport–Door</SelectItem>
                                    <SelectItem value="A2A">Airport–Airport</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <Label htmlFor="paymentTerm">Payment Term</Label>
                            <Select onValueChange={setPaymentTerm} value={paymentTerm}>
                                <SelectTrigger id="paymentTerm"><SelectValue /></SelectTrigger>
                                <SelectContent>
                                    <SelectItem value="PREPAID">Prepaid</SelectItem>
                                    <SelectItem value="COLLECT">Collect</SelectItem>
                                </SelectContent>
                            </Select>
                        </div>

                        <div>
                            <Label htmlFor="sellCurrency">Sell Currency</Label>
                            <Input id="sellCurrency" value={sellCurrency} onChange={(e) => setSellCurrency(e.target.value.toUpperCase())} maxLength={3} />
                        </div>

                        {error && <p className="text-red-500">{error}</p>}

                        <Button type="submit" disabled={isLoading} className="w-full">
                            {isLoading ? 'Creating...' : 'Create Quotation'}
                        </Button>
                    </form>
                </CardContent>
            </Card>
        </div>
    );
}
