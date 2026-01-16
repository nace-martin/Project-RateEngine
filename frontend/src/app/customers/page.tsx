'use client';

import { useState, useEffect } from 'react';
import Link from "next/link";
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
import { apiClient } from '@/lib/api';
import { usePermissions } from '@/hooks/usePermissions';

interface Address {
  country: string;
}

interface Customer {
  id: number;
  company_name: string;
  contact_person_name: string;
  primary_address: Address | null;
}

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const { isAdmin } = usePermissions();

  useEffect(() => {
    const getCustomers = async () => {
      try {
        const res = await apiClient.get<Customer[]>('/api/v3/customers/');
        setCustomers(res.data);
        setError(null);
      } catch (err) {
        console.error('Failed to fetch customers', err);
        setError('Failed to fetch customers.');
      }
    };

    getCustomers();
  }, []);

  return (
    <div className="container mx-auto py-8 max-w-7xl">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-6">
          <div className="space-y-1.5">
            <CardTitle>Customers</CardTitle>
            <CardDescription>
              A list of all customers, agents, and partners in the system.
            </CardDescription>
          </div>
          {/* Only Admin can add new customers */}
          {isAdmin && (
            <Link href="/customers/new">
              <Button>Add New Customer</Button>
            </Link>
          )}
        </CardHeader>
        <CardContent>
          {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

          <div className="rounded-md border border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[300px]">Company Name</TableHead>
                  <TableHead>Contact Person</TableHead>
                  <TableHead>Country</TableHead>
                  {isAdmin && <TableHead className="text-right">Actions</TableHead>}
                </TableRow>
              </TableHeader>
              <TableBody>
                {customers.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={isAdmin ? 4 : 3} className="h-24 text-center text-muted-foreground">
                      No customers found.
                    </TableCell>
                  </TableRow>
                ) : (
                  customers.map((customer) => (
                    <TableRow key={customer.id}>
                      <TableCell className="font-medium">
                        {customer.company_name}
                      </TableCell>
                      <TableCell>{customer.contact_person_name}</TableCell>
                      <TableCell>{customer.primary_address?.country || '—'}</TableCell>
                      {/* Only Admin can edit customers */}
                      {isAdmin && (
                        <TableCell className="text-right">
                          <Button variant="ghost" size="sm" asChild>
                            <Link href={`/customers/${customer.id}/edit`}>
                              Edit
                            </Link>
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
    </div>
  );
}
