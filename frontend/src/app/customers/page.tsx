'use client';

import { useState, useEffect, useMemo } from 'react';
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
import { Input } from "@/components/ui/input";
import { apiClient } from '@/lib/api';
import ProtectedRoute from '@/components/protected-route';
import { useAuth } from '@/context/auth-context';
import { usePermissions } from '@/hooks/usePermissions';

interface Address {
  country: string;
}

interface Customer {
  id: string;
  company_name: string;
  contact_person_name?: string;
  primary_address: Address | null;
}

interface CustomerApiRow {
  id?: string;
  name?: string;
  company_name?: string;
  contact_person_name?: string;
  primary_address?: Address | null;
}

interface PaginatedCustomers {
  results?: CustomerApiRow[];
}

const normalizeCustomers = (payload: unknown): Customer[] => {
  const rawRows: CustomerApiRow[] = Array.isArray(payload)
    ? payload
    : (payload as PaginatedCustomers)?.results ?? [];

  return rawRows
    .filter((row): row is CustomerApiRow => Boolean(row && row.id))
    .map((row) => ({
      id: String(row.id),
      company_name: row.company_name || row.name || "",
      contact_person_name: row.contact_person_name || "",
      primary_address: row.primary_address ?? null,
    }));
};

export default function CustomersPage() {
  const [customers, setCustomers] = useState<Customer[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [companyFilter, setCompanyFilter] = useState('');
  const [contactFilter, setContactFilter] = useState('');
  const [countryFilter, setCountryFilter] = useState('');
  const { token, loading } = useAuth();
  const { isAdmin } = usePermissions();

  useEffect(() => {
    if (loading || !token) {
      return;
    }

    const getCustomers = async () => {
      try {
        const res = await apiClient.get('/api/v3/customers/');
        setCustomers(normalizeCustomers(res.data));
        setError(null);
      } catch (err) {
        console.error('Failed to fetch customers', err);
        setError('Failed to fetch customers.');
      }
    };

    getCustomers();
  }, [loading, token]);

  const filteredCustomers = useMemo(() => {
    const companyQuery = companyFilter.trim().toLowerCase();
    const contactQuery = contactFilter.trim().toLowerCase();
    const countryQuery = countryFilter.trim().toLowerCase();

    return customers.filter((customer) => {
      const company = (customer.company_name || '').toLowerCase();
      const contact = (customer.contact_person_name || '').toLowerCase();
      const country = (customer.primary_address?.country || '').toLowerCase();

      if (companyQuery && !company.includes(companyQuery)) return false;
      if (contactQuery && !contact.includes(contactQuery)) return false;
      if (countryQuery && !country.includes(countryQuery)) return false;
      return true;
    });
  }, [customers, companyFilter, contactFilter, countryFilter]);

  const clearFilters = () => {
    setCompanyFilter('');
    setContactFilter('');
    setCountryFilter('');
  };

  return (
    <ProtectedRoute>
      <div className="container mx-auto py-8 max-w-7xl">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-6">
            <div className="space-y-1.5">
              <CardTitle>Customers</CardTitle>
              <CardDescription>
                A list of all customers, agents, and partners in the system.
              </CardDescription>
            </div>
            {isAdmin && (
              <Link href="/customers/new">
                <Button>Add New Customer</Button>
              </Link>
            )}
          </CardHeader>
          <CardContent>
            {error && <p className="mb-4 text-sm text-red-600">{error}</p>}

            <div className="mb-4 grid gap-3 md:grid-cols-4">
              <Input
                placeholder="Search company name"
                value={companyFilter}
                onChange={(e) => setCompanyFilter(e.target.value)}
              />
              <Input
                placeholder="Search contact person"
                value={contactFilter}
                onChange={(e) => setContactFilter(e.target.value)}
              />
              <Input
                placeholder="Filter by country code"
                value={countryFilter}
                onChange={(e) => setCountryFilter(e.target.value)}
              />
              <Button
                type="button"
                variant="outline"
                onClick={clearFilters}
                disabled={!companyFilter && !contactFilter && !countryFilter}
              >
                Clear Filters
              </Button>
            </div>

            <p className="mb-3 text-sm text-muted-foreground">
              Showing {filteredCustomers.length} of {customers.length} customers
            </p>

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
                  {filteredCustomers.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={isAdmin ? 4 : 3} className="h-24 text-center text-muted-foreground">
                        {customers.length === 0 ? 'No customers found.' : 'No matching customers found.'}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredCustomers.map((customer) => (
                      <TableRow key={customer.id}>
                        <TableCell className="font-medium">
                          {customer.company_name}
                        </TableCell>
                        <TableCell>{customer.contact_person_name}</TableCell>
                        <TableCell>{customer.primary_address?.country || '-'}</TableCell>
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
    </ProtectedRoute>
  );
}
