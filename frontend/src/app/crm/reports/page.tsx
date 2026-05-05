'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { CrmSubNav } from '@/components/crm/CrmSubNav';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import ProtectedRoute from '@/components/protected-route';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { listOpportunities, listRecentInteractions, listTasks } from '@/lib/api/crm';
import { listCustomers } from '@/lib/api/parties';
import {
  daysSinceInteraction,
  engagementStatus,
  formatEngagementDate,
} from '@/lib/crm-engagement-health';
import type { CompanySearchResult, Interaction, Opportunity, Task } from '@/lib/types';

const opportunityStatuses = ['NEW', 'QUALIFIED', 'QUOTED', 'WON', 'LOST'];
const openOpportunityStatuses = new Set(['NEW', 'QUALIFIED', 'QUOTED']);

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

function firstDayOfMonthIso(): string {
  const date = new Date();
  date.setDate(1);
  return date.toISOString().slice(0, 10);
}

function dateOnly(value?: string | null): Date | null {
  if (!value) return null;
  const raw = value.includes('T') ? value : `${value}T00:00:00`;
  const date = new Date(raw);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value?: string | null): string {
  const date = dateOnly(value);
  if (!date) return '-';
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: '2-digit' });
}

function isWithinDateRange(value: string | null | undefined, startDate: string, endDate: string): boolean {
  const date = dateOnly(value);
  if (!date) return false;
  const start = dateOnly(startDate);
  const end = dateOnly(endDate);
  if (start && date < start) return false;
  if (end) {
    end.setHours(23, 59, 59, 999);
    if (date > end) return false;
  }
  return true;
}

function startOfToday(): Date {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date;
}

function daysOverdue(value?: string | null): number {
  const dueDate = dateOnly(value);
  if (!dueDate) return 0;
  const diff = startOfToday().getTime() - dueDate.getTime();
  return Math.max(0, Math.floor(diff / (24 * 60 * 60 * 1000)));
}

function formatCurrency(value: number): string {
  return `PGK ${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function ownerLabel(value?: string | number | null): string {
  if (!value) return 'Unassigned';
  return String(value);
}

function KpiCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <Card className="border-slate-200 shadow-sm">
      <CardContent className="p-5">
        <p className="text-sm font-medium text-muted-foreground">{label}</p>
        <p className="mt-2 text-2xl font-semibold text-slate-900">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{detail}</p>
      </CardContent>
    </Card>
  );
}

export default function CrmReportsPage() {
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [customers, setCustomers] = useState<CompanySearchResult[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(firstDayOfMonthIso());
  const [endDate, setEndDate] = useState(todayIso());
  const [ownerFilter, setOwnerFilter] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [serviceTypeFilter, setServiceTypeFilter] = useState('ALL');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [interactionRows, taskRows, opportunityRows, customerRows] = await Promise.all([
        listRecentInteractions(),
        listTasks(),
        listOpportunities(),
        listCustomers(),
      ]);
      setInteractions(interactionRows);
      setTasks(taskRows);
      setOpportunities(opportunityRows);
      setCustomers(customerRows);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load CRM reports.');
      setInteractions([]);
      setTasks([]);
      setOpportunities([]);
      setCustomers([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadData();
  }, [loadData]);

  const customerById = useMemo(() => {
    return new Map(customers.map((customer) => [customer.id, customer]));
  }, [customers]);

  const opportunityById = useMemo(() => {
    return new Map(opportunities.map((opportunity) => [opportunity.id, opportunity]));
  }, [opportunities]);

  const ownerOptions = useMemo(() => {
    const owners = new Map<string, string>();
    interactions.forEach((interaction) => {
      if (interaction.author_username) owners.set(interaction.author_username, interaction.author_username);
      else if (interaction.author) owners.set(String(interaction.author), `User #${interaction.author}`);
    });
    tasks.forEach((task) => {
      if (task.owner_username) owners.set(task.owner_username, task.owner_username);
      else if (task.owner) owners.set(String(task.owner), `User #${task.owner}`);
    });
    opportunities.forEach((opportunity) => {
      if (opportunity.owner_username) owners.set(opportunity.owner_username, opportunity.owner_username);
      else if (opportunity.owner) owners.set(String(opportunity.owner), `User #${opportunity.owner}`);
    });
    customers.forEach((customer) => {
      if (customer.account_owner_username) owners.set(customer.account_owner_username, customer.account_owner_username);
      else if (customer.account_owner) owners.set(String(customer.account_owner), `User #${customer.account_owner}`);
    });
    return [...owners.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [customers, interactions, opportunities, tasks]);

  const serviceTypeOptions = useMemo(() => {
    return [...new Set(opportunities.map((opportunity) => opportunity.service_type).filter(Boolean))]
      .sort((left, right) => left.localeCompare(right));
  }, [opportunities]);

  const filteredInteractions = useMemo(() => {
    return interactions.filter((interaction) => {
      if (!isWithinDateRange(interaction.created_at, startDate, endDate)) return false;
      if (ownerFilter === 'ALL') return true;
      return interaction.author_username === ownerFilter || String(interaction.author || '') === ownerFilter;
    });
  }, [endDate, interactions, ownerFilter, startDate]);

  const filteredOpportunities = useMemo(() => {
    return opportunities.filter((opportunity) => {
      if (ownerFilter !== 'ALL' && opportunity.owner_username !== ownerFilter && String(opportunity.owner || '') !== ownerFilter) {
        return false;
      }
      if (statusFilter !== 'ALL' && opportunity.status !== statusFilter) return false;
      if (serviceTypeFilter !== 'ALL' && opportunity.service_type !== serviceTypeFilter) return false;
      return true;
    });
  }, [opportunities, ownerFilter, serviceTypeFilter, statusFilter]);

  const filteredTasks = useMemo(() => {
    return tasks.filter((task) => {
      if (ownerFilter !== 'ALL' && task.owner_username !== ownerFilter && String(task.owner || '') !== ownerFilter) return false;
      const opportunity = task.opportunity ? opportunityById.get(task.opportunity) : null;
      if (serviceTypeFilter !== 'ALL' && opportunity?.service_type !== serviceTypeFilter) return false;
      return true;
    });
  }, [opportunityById, ownerFilter, serviceTypeFilter, tasks]);

  const activityByUser = useMemo(() => {
    const rows = new Map<string, {
      label: string;
      interactions: number;
      meetings: number;
      calls: number;
      emails: number;
      siteVisits: number;
      lastActivity: string | null;
    }>();

    filteredInteractions.forEach((interaction) => {
      const key = interaction.author_username || (interaction.author ? String(interaction.author) : 'Unassigned');
      const row = rows.get(key) || {
        label: ownerLabel(interaction.author_username || interaction.author),
        interactions: 0,
        meetings: 0,
        calls: 0,
        emails: 0,
        siteVisits: 0,
        lastActivity: null,
      };

      row.interactions += 1;
      if (interaction.interaction_type === 'MEETING') row.meetings += 1;
      if (interaction.interaction_type === 'CALL') row.calls += 1;
      if (interaction.interaction_type === 'EMAIL') row.emails += 1;
      if (interaction.interaction_type === 'SITE_VISIT') row.siteVisits += 1;
      if (!row.lastActivity || (interaction.created_at && new Date(interaction.created_at) > new Date(row.lastActivity))) {
        row.lastActivity = interaction.created_at || row.lastActivity;
      }
      rows.set(key, row);
    });

    return [...rows.values()].sort((left, right) => right.interactions - left.interactions);
  }, [filteredInteractions]);

  const overdueFollowUps = useMemo(() => {
    return filteredTasks
      .filter((task) => task.status === 'PENDING' && daysOverdue(task.due_date) > 0)
      .sort((left, right) => daysOverdue(right.due_date) - daysOverdue(left.due_date));
  }, [filteredTasks]);

  const customerEngagementRisk = useMemo(() => {
    const openCounts = filteredOpportunities.reduce((counts, opportunity) => {
      if (openOpportunityStatuses.has(opportunity.status)) {
        counts.set(opportunity.company, (counts.get(opportunity.company) || 0) + 1);
      }
      return counts;
    }, new Map<string, number>());

    return customers
      .filter((customer) => {
        if (ownerFilter !== 'ALL' && customer.account_owner_username !== ownerFilter && String(customer.account_owner || '') !== ownerFilter) {
          return false;
        }
        return true;
      })
      .map((customer) => ({
        customer,
        days: daysSinceInteraction(customer.last_interaction_at),
        status: engagementStatus(customer.last_interaction_at),
        openOpportunities: openCounts.get(customer.id) || 0,
      }))
      .sort((left, right) => {
        if (left.days === null && right.days !== null) return -1;
        if (left.days !== null && right.days === null) return 1;
        return (right.days ?? Number.MAX_SAFE_INTEGER) - (left.days ?? Number.MAX_SAFE_INTEGER);
      })
      .slice(0, 12);
  }, [customers, filteredOpportunities, ownerFilter]);

  const opportunityOutcome = useMemo(() => {
    const statusCounts = opportunityStatuses.reduce((counts, status) => {
      counts[status] = filteredOpportunities.filter((opportunity) => opportunity.status === status).length;
      return counts;
    }, {} as Record<string, number>);

    const now = new Date();
    const month = now.getMonth();
    const year = now.getFullYear();
    const isThisMonth = (value?: string | null) => {
      const date = dateOnly(value);
      return Boolean(date && date.getMonth() === month && date.getFullYear() === year);
    };

    const pipelineValue = filteredOpportunities
      .filter((opportunity) => openOpportunityStatuses.has(opportunity.status))
      .reduce((total, opportunity) => {
        const value = Number(opportunity.estimated_revenue || 0);
        return Number.isNaN(value) ? total : total + value;
      }, 0);

    return {
      statusCounts,
      wonThisMonth: filteredOpportunities.filter((opportunity) => opportunity.status === 'WON' && isThisMonth(opportunity.won_at || opportunity.updated_at)).length,
      lostThisMonth: filteredOpportunities.filter((opportunity) => opportunity.status === 'LOST' && isThisMonth(opportunity.updated_at)).length,
      pipelineValue,
    };
  }, [filteredOpportunities]);

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="CRM Reports"
          description="Simple CRM reports for activity, follow-ups, engagement risk, and outcomes."
          actions={
            <Button asChild variant="outline">
              <Link href="/crm/activities">Open Activities</Link>
            </Button>
          }
        />

        <CrmSubNav />

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Filters</CardTitle>
            <CardDescription>Filters are applied client-side to the loaded CRM data.</CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-5">
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Start date</p>
              <Input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">End date</p>
              <Input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} />
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Owner</p>
              <Select value={ownerFilter} onValueChange={setOwnerFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Owners</SelectItem>
                  {ownerOptions.map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Status</p>
              <Select value={statusFilter} onValueChange={setStatusFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Statuses</SelectItem>
                  {opportunityStatuses.map((status) => (
                    <SelectItem key={status} value={status}>
                      {status}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Service type</p>
              <Select value={serviceTypeFilter} onValueChange={setServiceTypeFilter}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ALL">All Services</SelectItem>
                  {serviceTypeOptions.map((serviceType) => (
                    <SelectItem key={serviceType} value={serviceType}>
                      {serviceType}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <div className="mt-6 space-y-6">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Activity by User</CardTitle>
              <CardDescription>Interactions logged in the selected date range.</CardDescription>
            </CardHeader>
            <CardContent className="px-6 pb-6 pt-2">
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User / Account Manager</TableHead>
                      <TableHead className="text-right">Interactions</TableHead>
                      <TableHead className="text-right">Meetings</TableHead>
                      <TableHead className="text-right">Calls</TableHead>
                      <TableHead className="text-right">Emails</TableHead>
                      <TableHead className="text-right">Site Visits</TableHead>
                      <TableHead>Last Activity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          Loading activity...
                        </TableCell>
                      </TableRow>
                    ) : activityByUser.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          No activity found for the selected filters.
                        </TableCell>
                      </TableRow>
                    ) : (
                      activityByUser.map((row) => (
                        <TableRow key={row.label}>
                          <TableCell className="font-medium">{row.label}</TableCell>
                          <TableCell className="text-right">{row.interactions}</TableCell>
                          <TableCell className="text-right">{row.meetings}</TableCell>
                          <TableCell className="text-right">{row.calls}</TableCell>
                          <TableCell className="text-right">{row.emails}</TableCell>
                          <TableCell className="text-right">{row.siteVisits}</TableCell>
                          <TableCell>{formatDate(row.lastActivity)}</TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
              <div>
                <CardTitle>Overdue Follow-Ups</CardTitle>
                <CardDescription>Pending tasks past due date.</CardDescription>
              </div>
              <Button asChild variant="outline">
                <Link href="/crm/activities">Open Activities</Link>
              </Button>
            </CardHeader>
            <CardContent className="px-6 pb-6 pt-2">
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Task</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>Opportunity</TableHead>
                      <TableHead>Due Date</TableHead>
                      <TableHead className="text-right">Days Overdue</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                          Loading tasks...
                        </TableCell>
                      </TableRow>
                    ) : overdueFollowUps.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={6} className="h-24 text-center text-muted-foreground">
                          No overdue follow-ups.
                        </TableCell>
                      </TableRow>
                    ) : (
                      overdueFollowUps.map((task) => {
                        const company = task.company ? customerById.get(task.company) : null;
                        const opportunity = task.opportunity ? opportunityById.get(task.opportunity) : null;
                        return (
                          <TableRow key={task.id}>
                            <TableCell className="font-medium">{task.description}</TableCell>
                            <TableCell>{task.owner_username || ownerLabel(task.owner)}</TableCell>
                            <TableCell>
                              {company ? (
                                <Link className="text-primary hover:underline" href={`/customers/${company.id}/edit?returnTo=%2Fcrm%2Freports`}>
                                  {company.name}
                                </Link>
                              ) : task.company ? 'Company linked' : '-'}
                            </TableCell>
                            <TableCell>
                              {opportunity ? (
                                <Link className="text-primary hover:underline" href={`/crm/opportunities/${opportunity.id}`}>
                                  {opportunity.title}
                                </Link>
                              ) : task.opportunity ? 'Opportunity linked' : '-'}
                            </TableCell>
                            <TableCell>{formatDate(task.due_date)}</TableCell>
                            <TableCell className="text-right">{daysOverdue(task.due_date)}</TableCell>
                          </TableRow>
                        );
                      })
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Customer Engagement Risk</CardTitle>
              <CardDescription>Accounts ordered by oldest or missing CRM interaction.</CardDescription>
            </CardHeader>
            <CardContent className="px-6 pb-6 pt-2">
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Company</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead>Last Interaction</TableHead>
                      <TableHead>Days Since Interaction</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Open Opportunities</TableHead>
                      <TableHead className="text-right">Action</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          Loading accounts...
                        </TableCell>
                      </TableRow>
                    ) : customerEngagementRisk.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          No customer engagement data found.
                        </TableCell>
                      </TableRow>
                    ) : (
                      customerEngagementRisk.map(({ customer, days, status, openOpportunities }) => (
                        <TableRow key={customer.id}>
                          <TableCell className="font-medium">{customer.name}</TableCell>
                          <TableCell>{customer.account_owner_username || ownerLabel(customer.account_owner)}</TableCell>
                          <TableCell>{formatEngagementDate(customer.last_interaction_at)}</TableCell>
                          <TableCell>{days === null ? '-' : days}</TableCell>
                          <TableCell>
                            <Badge variant={status === 'Dormant' || status === 'Never Contacted' ? 'destructive' : 'outline'}>
                              {status}
                            </Badge>
                          </TableCell>
                          <TableCell>{openOpportunities}</TableCell>
                          <TableCell className="text-right">
                            <Button asChild variant="outline" size="sm">
                              <Link href={`/customers/${customer.id}/edit?returnTo=%2Fcrm%2Freports`}>View Account</Link>
                            </Button>
                          </TableCell>
                        </TableRow>
                      ))
                    )}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle>Opportunity Outcomes</CardTitle>
              <CardDescription>Status counts and current open pipeline from filtered opportunities.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5 px-6 pb-6 pt-2">
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3 xl:grid-cols-5">
                {opportunityStatuses.map((status) => (
                  <KpiCard
                    key={status}
                    label={status}
                    value={loading ? '...' : String(opportunityOutcome.statusCounts[status] || 0)}
                    detail="Opportunities"
                  />
                ))}
              </div>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                <KpiCard
                  label="Won This Month"
                  value={loading ? '...' : String(opportunityOutcome.wonThisMonth)}
                  detail="Filtered opportunities"
                />
                <KpiCard
                  label="Lost This Month"
                  value={loading ? '...' : String(opportunityOutcome.lostThisMonth)}
                  detail="Filtered opportunities"
                />
                <KpiCard
                  label="Open Pipeline"
                  value={loading ? '...' : formatCurrency(opportunityOutcome.pipelineValue)}
                  detail="NEW, QUALIFIED, and QUOTED"
                />
              </div>
              <div className="text-right">
                <Button asChild variant="outline">
                  <Link href="/crm/opportunities">View Opportunities</Link>
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
