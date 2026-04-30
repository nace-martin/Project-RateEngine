'use client';

import { useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';

import ProtectedRoute from '@/components/protected-route';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { listOpportunities } from '@/lib/api/crm';
import type { Opportunity } from '@/lib/types';

const statusOptions = ['NEW', 'QUALIFIED', 'QUOTED', 'WON', 'LOST'];
const serviceTypeOptions = ['AIR', 'SEA', 'CUSTOMS', 'DOMESTIC', 'MULTIMODAL'];

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
}

function formatDateTime(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function formatCurrency(value?: string | number | null, currency?: string): string {
  if (value === null || value === undefined || value === '') return '-';
  const amount = Number(value);
  if (Number.isNaN(amount)) return String(value);
  return `${currency || 'PGK'} ${amount.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function statusBadgeVariant(status: string) {
  if (status === 'WON') return 'default';
  if (status === 'LOST') return 'destructive';
  if (status === 'QUOTED') return 'secondary';
  return 'outline';
}

export default function OpportunityListPage() {
  const router = useRouter();
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState('all');
  const [serviceType, setServiceType] = useState('all');

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    listOpportunities({
      status: status === 'all' ? undefined : status,
      service_type: serviceType === 'all' ? undefined : serviceType,
    })
      .then((rows) => {
        if (!active) return;
        setOpportunities(rows);
      })
      .catch((fetchError: Error) => {
        if (!active) return;
        setError(fetchError.message || 'Failed to load opportunities.');
        setOpportunities([]);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [status, serviceType]);

  const filteredOpportunities = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return opportunities;
    return opportunities.filter((opportunity) => {
      const haystack = [
        opportunity.company_name,
        opportunity.title,
        opportunity.service_type,
        opportunity.origin,
        opportunity.destination,
        opportunity.status,
        opportunity.priority,
        opportunity.owner_username,
      ]
        .filter(Boolean)
        .join(' ')
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [opportunities, search]);

  const clearFilters = () => {
    setSearch('');
    setStatus('all');
    setServiceType('all');
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="Opportunities"
          description="Review active and closed CRM opportunities before dashboards and pipeline boards are added."
        />

        <Card className="border-slate-200 shadow-sm">
          <CardHeader className="pb-2">
            <CardTitle className="text-lg">Opportunity Register</CardTitle>
            <CardDescription>
              Search by customer, title, service, route, status, priority, or owner.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5 px-6 pb-6 pt-2">
            <div className="grid grid-cols-1 gap-3 lg:grid-cols-12">
              <Input
                className="lg:col-span-5"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search opportunities"
              />
              <select
                value={status}
                onChange={(event) => setStatus(event.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring lg:col-span-2"
              >
                <option value="all">All statuses</option>
                {statusOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <select
                value={serviceType}
                onChange={(event) => setServiceType(event.target.value)}
                className="h-9 rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring lg:col-span-3"
              >
                <option value="all">All service types</option>
                {serviceTypeOptions.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
              <Button
                type="button"
                variant="outline"
                onClick={clearFilters}
                disabled={!search && status === 'all' && serviceType === 'all'}
                className="lg:col-span-2"
              >
                Clear Filters
              </Button>
            </div>

            {error ? (
              <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
                {error}
              </div>
            ) : null}

            <p className="text-sm text-muted-foreground">
              Showing {filteredOpportunities.length} of {opportunities.length} opportunities
            </p>

            <div className="overflow-hidden rounded-md border border-slate-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Company</TableHead>
                    <TableHead>Title</TableHead>
                    <TableHead>Service</TableHead>
                    <TableHead>Origin</TableHead>
                    <TableHead>Destination</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Owner</TableHead>
                    <TableHead className="text-right">Est. Revenue</TableHead>
                    <TableHead>Next Action</TableHead>
                    <TableHead>Last Activity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={11} className="h-24 text-center text-muted-foreground">
                        Loading opportunities...
                      </TableCell>
                    </TableRow>
                  ) : filteredOpportunities.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={11} className="h-24 text-center text-muted-foreground">
                        {opportunities.length === 0 ? 'No opportunities found.' : 'No matching opportunities found.'}
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredOpportunities.map((opportunity) => (
                      <TableRow
                        key={opportunity.id}
                        className="cursor-pointer"
                        onClick={() => router.push(`/crm/opportunities/${opportunity.id}`)}
                      >
                        <TableCell className="font-medium">{opportunity.company_name || '-'}</TableCell>
                        <TableCell>{opportunity.title}</TableCell>
                        <TableCell>{opportunity.service_type || '-'}</TableCell>
                        <TableCell>{opportunity.origin || '-'}</TableCell>
                        <TableCell>{opportunity.destination || '-'}</TableCell>
                        <TableCell>
                          <Badge variant={statusBadgeVariant(opportunity.status)}>
                            {opportunity.status}
                          </Badge>
                        </TableCell>
                        <TableCell>{opportunity.priority || '-'}</TableCell>
                        <TableCell>{opportunity.owner_username || '-'}</TableCell>
                        <TableCell className="text-right tabular-nums">
                          {formatCurrency(opportunity.estimated_revenue, opportunity.estimated_currency)}
                        </TableCell>
                        <TableCell>{formatDate(opportunity.next_action_date)}</TableCell>
                        <TableCell>{formatDateTime(opportunity.last_activity_at)}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </CardContent>
        </Card>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
