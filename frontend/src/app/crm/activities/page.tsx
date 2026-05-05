'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { CrmSubNav } from '@/components/crm/CrmSubNav';
import { TaskDialog } from '@/components/crm/TaskDialog';
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
import { useToast } from '@/context/toast-context';
import { completeTask, listOpportunities, listRecentInteractions, listTasks } from '@/lib/api/crm';
import { listCustomers } from '@/lib/api/parties';
import type { CompanySearchResult, Interaction, Opportunity, Task } from '@/lib/types';

type StatusFilter = 'OPEN' | 'PENDING' | 'COMPLETED' | 'CANCELLED' | 'ALL';
type DueBucketFilter = 'WORK_QUEUE' | 'OVERDUE' | 'TODAY' | 'THIS_WEEK' | 'COMPLETED' | 'ALL';

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

function isOverdue(value?: string | null): boolean {
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

function taskBucket(task: Task): string {
  if (task.status === 'COMPLETED') return 'Completed';
  if (isOverdue(task.due_date)) return 'Overdue';
  if (isToday(task.due_date)) return 'Due Today';
  if (isThisWeek(task.due_date)) return 'Due This Week';
  return 'Upcoming';
}

function statusBadgeVariant(status: string) {
  if (status === 'COMPLETED') return 'default';
  if (status === 'CANCELLED') return 'secondary';
  return 'outline';
}

export default function CrmActivitiesPage() {
  const { toast } = useToast();
  const [tasks, setTasks] = useState<Task[]>([]);
  const [customers, setCustomers] = useState<CompanySearchResult[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [taskDialogOpen, setTaskDialogOpen] = useState(false);
  const [editingTask, setEditingTask] = useState<Task | null>(null);
  const [completingTaskIds, setCompletingTaskIds] = useState<Set<string>>(() => new Set());
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('OPEN');
  const [dueBucketFilter, setDueBucketFilter] = useState<DueBucketFilter>('WORK_QUEUE');
  const [ownerFilter, setOwnerFilter] = useState('ALL');
  const [searchQuery, setSearchQuery] = useState('');

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [taskRows, customerRows, opportunityRows, interactionRows] = await Promise.all([
        listTasks(),
        listCustomers(),
        listOpportunities(),
        listRecentInteractions().catch(() => []),
      ]);
      setTasks(taskRows);
      setCustomers(customerRows);
      setOpportunities(opportunityRows);
      setInteractions(interactionRows);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load CRM activities.');
      setTasks([]);
      setCustomers([]);
      setOpportunities([]);
      setInteractions([]);
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
    tasks.forEach((task) => {
      if (task.owner_username) {
        owners.set(task.owner_username, task.owner_username);
      } else if (task.owner) {
        owners.set(String(task.owner), `Owner #${task.owner}`);
      }
    });
    return [...owners.entries()].sort((left, right) => left[1].localeCompare(right[1]));
  }, [tasks]);

  const counts = useMemo(() => {
    const pendingTasks = tasks.filter((task) => task.status === 'PENDING');
    return {
      overdue: pendingTasks.filter((task) => isOverdue(task.due_date)).length,
      today: pendingTasks.filter((task) => isToday(task.due_date)).length,
      week: pendingTasks.filter((task) => isThisWeek(task.due_date)).length,
      completed: tasks.filter((task) => task.status === 'COMPLETED').length,
    };
  }, [tasks]);

  const filteredTasks = useMemo(() => {
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return tasks
      .filter((task) => {
        if (dueBucketFilter === 'COMPLETED' && statusFilter === 'OPEN') return task.status === 'COMPLETED';
        if (statusFilter === 'ALL') return true;
        if (statusFilter === 'OPEN') return task.status === 'PENDING';
        return task.status === statusFilter;
      })
      .filter((task) => {
        if (dueBucketFilter === 'ALL') return true;
        if (dueBucketFilter === 'COMPLETED') return task.status === 'COMPLETED';
        if (task.status !== 'PENDING') return false;
        if (dueBucketFilter === 'OVERDUE') return isOverdue(task.due_date);
        if (dueBucketFilter === 'TODAY') return isToday(task.due_date);
        if (dueBucketFilter === 'THIS_WEEK') return isThisWeek(task.due_date);
        return isOverdue(task.due_date) || isToday(task.due_date) || isThisWeek(task.due_date);
      })
      .filter((task) => {
        if (ownerFilter === 'ALL') return true;
        return task.owner_username === ownerFilter || String(task.owner) === ownerFilter;
      })
      .filter((task) => {
        if (!normalizedQuery) return true;
        const company = task.company ? customerById.get(task.company) : null;
        const opportunity = task.opportunity ? opportunityById.get(task.opportunity) : null;
        return [
          task.description,
          company?.name,
          opportunity?.title,
          task.owner_username,
        ].some((value) => (value || '').toLowerCase().includes(normalizedQuery));
      })
      .sort((left, right) => {
        const leftCompleted = left.status === 'COMPLETED' ? 1 : 0;
        const rightCompleted = right.status === 'COMPLETED' ? 1 : 0;
        if (leftCompleted !== rightCompleted) return leftCompleted - rightCompleted;
        const leftDue = dateOnly(left.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        const rightDue = dateOnly(right.due_date)?.getTime() ?? Number.MAX_SAFE_INTEGER;
        if (leftDue !== rightDue) return leftDue - rightDue;
        return (left.description || '').localeCompare(right.description || '');
      });
  }, [customerById, dueBucketFilter, opportunityById, ownerFilter, searchQuery, statusFilter, tasks]);

  const handleDueBucketChange = (value: DueBucketFilter) => {
    setDueBucketFilter(value);
    if (value === 'COMPLETED' && statusFilter === 'OPEN') {
      setStatusFilter('COMPLETED');
    }
  };

  const openCreateDialog = () => {
    setEditingTask(null);
    setTaskDialogOpen(true);
  };

  const openEditDialog = (task: Task) => {
    setEditingTask(task);
    setTaskDialogOpen(true);
  };

  const handleCompleteTask = async (taskId: string) => {
    if (completingTaskIds.has(taskId)) return;
    setCompletingTaskIds((current) => new Set(current).add(taskId));
    try {
      await completeTask(taskId);
      toast({ title: 'Task Completed', variant: 'success' });
      void loadData();
    } catch (completeError) {
      toast({
        title: 'Action Failed',
        description: completeError instanceof Error ? completeError.message : 'The task was not completed.',
        variant: 'destructive',
      });
    } finally {
      setCompletingTaskIds((current) => {
        const next = new Set(current);
        next.delete(taskId);
        return next;
      });
    }
  };

  const editingCompany = editingTask?.company ? customerById.get(editingTask.company) || null : null;
  const editingOpportunity = editingTask?.opportunity ? opportunityById.get(editingTask.opportunity) || null : null;
  const recentActivity = interactions.slice(0, 8);

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="Activities"
          description="Manage CRM follow-up tasks and recent customer activity."
          actions={
            <Button type="button" onClick={openCreateDialog}>
              Create Task
            </Button>
          }
        />

        <CrmSubNav />

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-4 md:grid-cols-4">
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5">
                <p className="text-sm font-medium text-muted-foreground">Overdue</p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{loading ? '...' : counts.overdue}</p>
              </CardContent>
            </Card>
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5">
                <p className="text-sm font-medium text-muted-foreground">Due Today</p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{loading ? '...' : counts.today}</p>
              </CardContent>
            </Card>
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5">
                <p className="text-sm font-medium text-muted-foreground">Due This Week</p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{loading ? '...' : counts.week}</p>
              </CardContent>
            </Card>
            <Card className="border-slate-200 shadow-sm">
              <CardContent className="p-5">
                <p className="text-sm font-medium text-muted-foreground">Completed</p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{loading ? '...' : counts.completed}</p>
              </CardContent>
            </Card>
          </div>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div>
                <CardTitle>Task Work Queue</CardTitle>
                <CardDescription>Filter by due bucket, status, owner, or task context.</CardDescription>
              </div>
              <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap lg:justify-end">
                <Input
                  className="w-full sm:w-[260px]"
                  placeholder="Search tasks, accounts, opportunities"
                  value={searchQuery}
                  onChange={(event) => setSearchQuery(event.target.value)}
                />
                <Select value={dueBucketFilter} onValueChange={(value) => handleDueBucketChange(value as DueBucketFilter)}>
                  <SelectTrigger className="w-full sm:w-[150px]" aria-label="Due bucket filter">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="WORK_QUEUE">Work Queue</SelectItem>
                    <SelectItem value="OVERDUE">Overdue</SelectItem>
                    <SelectItem value="TODAY">Due Today</SelectItem>
                    <SelectItem value="THIS_WEEK">Due This Week</SelectItem>
                    <SelectItem value="COMPLETED">Completed</SelectItem>
                    <SelectItem value="ALL">All Dates</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as StatusFilter)}>
                  <SelectTrigger className="w-full sm:w-[145px]" aria-label="Status filter">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="OPEN">Open</SelectItem>
                    <SelectItem value="PENDING">Pending</SelectItem>
                    <SelectItem value="COMPLETED">Completed</SelectItem>
                    <SelectItem value="CANCELLED">Cancelled</SelectItem>
                    <SelectItem value="ALL">All Statuses</SelectItem>
                  </SelectContent>
                </Select>
                <Select value={ownerFilter} onValueChange={setOwnerFilter}>
                  <SelectTrigger className="w-full sm:w-[150px]" aria-label="Owner filter">
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
            </CardHeader>
            <CardContent className="px-6 pb-6 pt-2">
              <div className="overflow-hidden rounded-md border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Description</TableHead>
                      <TableHead>Company</TableHead>
                      <TableHead>Opportunity</TableHead>
                      <TableHead>Owner</TableHead>
                      <TableHead>Due Date</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {loading ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          Loading tasks...
                        </TableCell>
                      </TableRow>
                    ) : filteredTasks.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          No tasks match the selected filters.
                        </TableCell>
                      </TableRow>
                    ) : (
                      filteredTasks.map((task) => {
                        const company = task.company ? customerById.get(task.company) : null;
                        const opportunity = task.opportunity ? opportunityById.get(task.opportunity) : null;
                        return (
                          <TableRow key={task.id}>
                            <TableCell className="font-medium">{task.description}</TableCell>
                            <TableCell>
                              {company ? (
                                <Link className="text-primary hover:underline" href={`/customers/${company.id}/edit?returnTo=%2Fcrm%2Factivities`}>
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
                            <TableCell>{task.owner_username || (task.owner ? `Owner #${task.owner}` : '-')}</TableCell>
                            <TableCell>
                              <div className="flex flex-col">
                                <span>{formatDate(task.due_date)}</span>
                                <span className="text-xs text-muted-foreground">{taskBucket(task)}</span>
                              </div>
                            </TableCell>
                            <TableCell>
                              <Badge variant={statusBadgeVariant(task.status)}>{task.status}</Badge>
                            </TableCell>
                            <TableCell className="text-right">
                              <div className="flex flex-wrap justify-end gap-2">
                                {company ? (
                                  <Button asChild variant="outline" size="sm">
                                    <Link href={`/customers/${company.id}/edit?returnTo=%2Fcrm%2Factivities`}>View Account</Link>
                                  </Button>
                                ) : null}
                                {opportunity ? (
                                  <Button asChild variant="outline" size="sm">
                                    <Link href={`/crm/opportunities/${opportunity.id}`}>View Opportunity</Link>
                                  </Button>
                                ) : null}
                                <Button type="button" variant="outline" size="sm" onClick={() => openEditDialog(task)}>
                                  Edit
                                </Button>
                                {task.status === 'PENDING' ? (
                                  <Button
                                    type="button"
                                    variant="outline"
                                    size="sm"
                                    onClick={() => handleCompleteTask(task.id)}
                                    disabled={completingTaskIds.has(task.id)}
                                  >
                                    {completingTaskIds.has(task.id) ? 'Saving...' : 'Done'}
                                  </Button>
                                ) : null}
                              </div>
                            </TableCell>
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
              <CardTitle>Recent Activity</CardTitle>
              <CardDescription>Newest CRM interactions for account context.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3 px-6 pb-6 pt-2">
              {loading ? (
                <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  Loading activity...
                </p>
              ) : recentActivity.length === 0 ? (
                <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  No recent CRM activity.
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
                        {opportunity ? (
                          <Link className="text-xs font-medium text-primary hover:underline" href={`/crm/opportunities/${opportunity.id}`}>
                            {opportunity.title}
                          </Link>
                        ) : null}
                      </div>
                      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-900">{interaction.summary}</p>
                    </div>
                  );
                })
              )}
            </CardContent>
          </Card>
        </div>

        <TaskDialog
          open={taskDialogOpen}
          onOpenChange={(nextOpen) => {
            setTaskDialogOpen(nextOpen);
            if (!nextOpen) {
              setEditingTask(null);
            }
          }}
          task={editingTask}
          defaults={{
            company: editingCompany,
            opportunity: editingOpportunity,
            description: editingTask?.description || '',
            dueDate: editingTask?.due_date,
            status: editingTask?.status || 'PENDING',
          }}
          onSaved={() => {
            void loadData();
          }}
        />
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
