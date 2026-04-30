'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { InteractionLogSheet } from '@/components/crm/InteractionLogSheet';
import { CrmSubNav } from '@/components/crm/CrmSubNav';
import ProtectedRoute from '@/components/protected-route';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { listOpportunities, listRecentInteractions, listTasks } from '@/lib/api/crm';
import type { Interaction, Opportunity, Task } from '@/lib/types';

const openStatuses = new Set(['NEW', 'QUALIFIED', 'QUOTED']);
const taskOpenStatuses = new Set(['PENDING']);
const interactionLabels: Record<string, string> = {
  CALL: 'Call',
  MEETING: 'Meeting',
  EMAIL: 'Email',
  SITE_VISIT: 'Site Visit',
  SYSTEM: 'System',
};

function startOfToday(): Date {
  const date = new Date();
  date.setHours(0, 0, 0, 0);
  return date;
}

function endOfThisWeek(): Date {
  const date = startOfToday();
  date.setDate(date.getDate() + 7);
  return date;
}

function dateOnly(value?: string | null): Date | null {
  if (!value) return null;
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value?: string | null): string {
  const date = dateOnly(value);
  if (!date) return '-';
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

function priorityRank(value?: string | null): number {
  if (value === 'HIGH') return 0;
  if (value === 'MEDIUM') return 1;
  return 2;
}

function oldestActivityRank(value?: string | null): number {
  if (!value) return 0;
  const time = new Date(value).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function isOverdueDate(value?: string | null): boolean {
  const dueDate = dateOnly(value);
  if (!dueDate) return false;
  return dueDate < startOfToday();
}

function isToday(value?: string | null): boolean {
  const dueDate = dateOnly(value);
  if (!dueDate) return false;
  return dueDate.getTime() === startOfToday().getTime();
}

function isThisWeek(value?: string | null): boolean {
  const dueDate = dateOnly(value);
  if (!dueDate) return false;
  const today = startOfToday();
  const weekEnd = endOfThisWeek();
  return dueDate > today && dueDate <= weekEnd;
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

function statusBadgeVariant(status: string) {
  if (status === 'WON') return 'default';
  if (status === 'LOST') return 'destructive';
  if (status === 'QUOTED') return 'secondary';
  return 'outline';
}

export default function CrmDashboardPage() {
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quickLogOpen, setQuickLogOpen] = useState(false);

  const loadDashboardData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [opportunityRows, taskRows, interactionRows] = await Promise.all([
        listOpportunities(),
        listTasks(),
        listRecentInteractions(),
      ]);
      setOpportunities(opportunityRows);
      setTasks(taskRows);
      setInteractions(interactionRows);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Failed to load CRM dashboard.');
      setOpportunities([]);
      setTasks([]);
      setInteractions([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboardData();
  }, [loadDashboardData]);

  const opportunityById = useMemo(() => {
    return new Map(opportunities.map((opportunity) => [opportunity.id, opportunity]));
  }, [opportunities]);

  const openOpportunities = useMemo(() => {
    return opportunities.filter((opportunity) => openStatuses.has(opportunity.status));
  }, [opportunities]);

  const pipelineRevenue = useMemo(() => {
    return openOpportunities.reduce((total, opportunity) => {
      const value = Number(opportunity.estimated_revenue || 0);
      return Number.isNaN(value) ? total : total + value;
    }, 0);
  }, [openOpportunities]);

  const wonThisMonth = useMemo(() => {
    const now = new Date();
    return opportunities.filter((opportunity) => {
      if (opportunity.status !== 'WON' || !opportunity.won_at) return false;
      const wonAt = new Date(opportunity.won_at);
      return wonAt.getFullYear() === now.getFullYear() && wonAt.getMonth() === now.getMonth();
    }).length;
  }, [opportunities]);

  const openTasks = useMemo(() => {
    return tasks.filter((task) => taskOpenStatuses.has(task.status));
  }, [tasks]);

  const overdueTasks = useMemo(() => {
    return openTasks.filter((task) => isOverdueDate(task.due_date));
  }, [openTasks]);

  const priorityOpportunities = useMemo(() => {
    return [...openOpportunities]
      .sort((a, b) => {
        const overdueA = isOverdueDate(a.next_action_date) ? 0 : 1;
        const overdueB = isOverdueDate(b.next_action_date) ? 0 : 1;
        if (overdueA !== overdueB) return overdueA - overdueB;
        const priorityDelta = priorityRank(a.priority) - priorityRank(b.priority);
        if (priorityDelta !== 0) return priorityDelta;
        return oldestActivityRank(a.last_activity_at) - oldestActivityRank(b.last_activity_at);
      })
      .slice(0, 8);
  }, [openOpportunities]);

  const tasksDue = useMemo(() => {
    return openTasks
      .filter((task) => isOverdueDate(task.due_date) || isToday(task.due_date) || isThisWeek(task.due_date))
      .sort((a, b) => {
        const aTime = dateOnly(a.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        const bTime = dateOnly(b.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        return aTime - bTime;
      })
      .slice(0, 10);
  }, [openTasks]);

  const recentActivity = useMemo(() => {
    return [...interactions]
      .sort((a, b) => {
        const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
        const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
        return bTime - aTime;
      })
      .slice(0, 10);
  }, [interactions]);

  const taskBucket = (task: Task): string => {
    if (isOverdueDate(task.due_date)) return 'Overdue';
    if (isToday(task.due_date)) return 'Today';
    if (isThisWeek(task.due_date)) return 'This week';
    return 'Upcoming';
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="CRM"
          description="Pipeline, follow-ups, and recent CRM activity."
          actions={
            <>
              <Button type="button" variant="outline" onClick={() => setQuickLogOpen(true)}>
                Log Activity
              </Button>
              <Button asChild>
                <Link href="/crm/opportunities/new">New Opportunity</Link>
              </Button>
            </>
          }
        />

        <CrmSubNav />

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <div className="space-y-6">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="pb-2">
              <CardTitle className="text-lg">Priority Opportunities</CardTitle>
              <CardDescription>Overdue follow-ups first, then priority and oldest activity.</CardDescription>
            </CardHeader>
            <CardContent className="px-6 pb-6 pt-2">
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Company</TableHead>
                      <TableHead>Title</TableHead>
                      <TableHead>Service</TableHead>
                      <TableHead>Route</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Priority</TableHead>
                      <TableHead className="text-right">Est. Revenue</TableHead>
                      <TableHead>Next Action</TableHead>
                      <TableHead>Last Activity</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                          Loading opportunities...
                        </TableCell>
                      </TableRow>
                    ) : priorityOpportunities.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={9} className="h-24 text-center text-muted-foreground">
                          No open opportunities.
                        </TableCell>
                      </TableRow>
                    ) : (
                      priorityOpportunities.map((opportunity) => (
                        <TableRow key={opportunity.id}>
                          <TableCell>{opportunity.company_name || '-'}</TableCell>
                          <TableCell className="font-medium">
                            <Link className="text-primary hover:underline" href={`/crm/opportunities/${opportunity.id}`}>
                              {opportunity.title}
                            </Link>
                          </TableCell>
                          <TableCell>{opportunity.service_type || '-'}</TableCell>
                          <TableCell>{[opportunity.origin, opportunity.destination].filter(Boolean).join(' - ') || '-'}</TableCell>
                          <TableCell>
                            <Badge variant={statusBadgeVariant(opportunity.status)}>{opportunity.status}</Badge>
                          </TableCell>
                          <TableCell>{opportunity.priority || '-'}</TableCell>
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

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
            <KpiCard
              label="Open Opportunities"
              value={loading ? '...' : String(openOpportunities.length)}
              detail="NEW, QUALIFIED, and QUOTED"
            />
            <KpiCard
              label="Open Pipeline"
              value={loading ? '...' : formatCurrency(pipelineRevenue, 'PGK')}
              detail="Estimated revenue across open opportunities"
            />
            <KpiCard
              label="Won This Month"
              value={loading ? '...' : String(wonThisMonth)}
              detail="Opportunities with won_at in the current month"
            />
            <KpiCard
              label="Overdue Tasks"
              value={loading ? '...' : String(overdueTasks.length)}
              detail="Pending tasks past due date"
            />
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Tasks Due</CardTitle>
                <CardDescription>Overdue, today, and this week.</CardDescription>
              </CardHeader>
              <CardContent className="px-6 pb-6 pt-2">
                <div className="overflow-hidden rounded-md border border-slate-200">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Description</TableHead>
                        <TableHead>Context</TableHead>
                        <TableHead>Owner</TableHead>
                        <TableHead>Due</TableHead>
                        <TableHead>Status</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {loading ? (
                        <TableRow>
                          <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                            Loading tasks...
                          </TableCell>
                        </TableRow>
                      ) : tasksDue.length === 0 ? (
                        <TableRow>
                          <TableCell colSpan={5} className="h-24 text-center text-muted-foreground">
                            No tasks due this week.
                          </TableCell>
                        </TableRow>
                      ) : (
                        tasksDue.map((task) => {
                          const opportunity = task.opportunity ? opportunityById.get(task.opportunity) : null;
                          return (
                            <TableRow key={task.id}>
                              <TableCell className="font-medium">{task.description}</TableCell>
                              <TableCell>
                                {opportunity ? (
                                  <Link className="text-primary hover:underline" href={`/crm/opportunities/${opportunity.id}`}>
                                    {opportunity.title}
                                  </Link>
                                ) : task.company ? (
                                  'Company linked'
                                ) : (
                                  '-'
                                )}
                              </TableCell>
                              <TableCell>{task.owner_username || '-'}</TableCell>
                              <TableCell>
                                <div className="flex flex-col">
                                  <span>{formatDate(task.due_date)}</span>
                                  <span className="text-xs text-muted-foreground">{taskBucket(task)}</span>
                                </div>
                              </TableCell>
                              <TableCell>{task.status}</TableCell>
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
              <CardHeader className="pb-2">
                <CardTitle className="text-lg">Recent Activity</CardTitle>
                <CardDescription>Newest CRM interactions.</CardDescription>
              </CardHeader>
              <CardContent className="space-y-3 px-6 pb-6 pt-2">
                {loading ? (
                  <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                    Loading activity...
                  </p>
                ) : recentActivity.length === 0 ? (
                  <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                    No recent activity.
                  </p>
                ) : (
                  recentActivity.map((interaction) => {
                    const opportunity = interaction.opportunity ? opportunityById.get(interaction.opportunity) : null;
                    const isSystem = Boolean(interaction.is_system_generated);
                    return (
                      <div key={interaction.id} className="rounded-md border border-slate-200 bg-white p-4">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge variant={isSystem ? 'secondary' : 'outline'}>
                            {isSystem ? 'SYSTEM' : interactionLabels[interaction.interaction_type] || interaction.interaction_type}
                          </Badge>
                          <span className="text-xs text-muted-foreground">{formatDateTime(interaction.created_at)}</span>
                          {interaction.company_name ? (
                            <span className="text-xs font-medium text-slate-600">{interaction.company_name}</span>
                          ) : null}
                        </div>
                        {opportunity ? (
                          <Link className="mt-2 block text-xs font-medium text-primary hover:underline" href={`/crm/opportunities/${opportunity.id}`}>
                            {opportunity.title}
                          </Link>
                        ) : interaction.opportunity ? (
                          <p className="mt-2 text-xs font-medium text-slate-600">Opportunity linked</p>
                        ) : null}
                        <p className="mt-2 whitespace-pre-wrap text-sm text-slate-900">{interaction.summary}</p>
                      </div>
                    );
                  })
                )}
              </CardContent>
            </Card>
          </div>
        </div>

        <InteractionLogSheet
          open={quickLogOpen}
          onOpenChange={(nextOpen) => {
            setQuickLogOpen(nextOpen);
            if (!nextOpen) {
              void loadDashboardData();
            }
          }}
        />
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
