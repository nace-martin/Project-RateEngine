'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';

import { InteractionLogSheet } from '@/components/crm/InteractionLogSheet';
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
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { getOpportunity, listInteractionsByOpportunity, listQuotesByOpportunity, listTasksByOpportunity } from '@/lib/api/crm';
import type { CompanySearchResult, Interaction, Opportunity, Task, V3QuoteComputeResponse } from '@/lib/types';

const interactionLabels: Record<string, string> = {
  CALL: 'Call',
  MEETING: 'Meeting',
  EMAIL: 'Email',
  SITE_VISIT: 'Site Visit',
  SYSTEM: 'System',
};

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

function formatMeasure(value?: string | number | null, suffix = ''): string {
  if (value === null || value === undefined || value === '') return '-';
  return `${value}${suffix}`;
}

function statusBadgeVariant(status: string) {
  if (status === 'WON') return 'default';
  if (status === 'LOST') return 'destructive';
  if (status === 'QUOTED') return 'secondary';
  return 'outline';
}

function DetailItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="space-y-1">
      <dt className="text-xs font-medium uppercase text-muted-foreground">{label}</dt>
      <dd className="text-sm text-slate-900">{value}</dd>
    </div>
  );
}

function TimelineItem({ interaction }: { interaction: Interaction }) {
  const isSystem = Boolean(interaction.is_system_generated);
  return (
    <div className="rounded-md border border-slate-200 bg-white p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={isSystem ? 'secondary' : 'outline'}>
          {isSystem ? 'SYSTEM' : interactionLabels[interaction.interaction_type] || interaction.interaction_type}
        </Badge>
        {interaction.system_event_type ? (
          <span className="text-xs font-medium text-slate-500">{interaction.system_event_type.replaceAll('_', ' ')}</span>
        ) : null}
        <span className="text-xs text-muted-foreground">{formatDateTime(interaction.created_at)}</span>
        {interaction.author_username ? (
          <span className="text-xs text-muted-foreground">by {interaction.author_username}</span>
        ) : null}
      </div>
      <p className="mt-3 whitespace-pre-wrap text-sm text-slate-900">{interaction.summary}</p>
      {interaction.outcomes ? (
        <p className="mt-2 whitespace-pre-wrap text-sm text-muted-foreground">{interaction.outcomes}</p>
      ) : null}
      {(interaction.next_action || interaction.next_action_date) ? (
        <p className="mt-3 text-sm text-slate-700">
          <span className="font-medium">Next action:</span>{' '}
          {interaction.next_action || 'Follow up'}
          {interaction.next_action_date ? ` by ${formatDate(interaction.next_action_date)}` : ''}
        </p>
      ) : null}
    </div>
  );
}

export default function OpportunityDetailPage() {
  const params = useParams<{ id: string }>();
  const [opportunity, setOpportunity] = useState<Opportunity | null>(null);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [quotes, setQuotes] = useState<V3QuoteComputeResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [quickLogOpen, setQuickLogOpen] = useState(false);

  const loadOpportunityData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [opportunityRow, interactionRows, taskRows, quoteRows] = await Promise.all([
        getOpportunity(params.id),
        listInteractionsByOpportunity(params.id),
        listTasksByOpportunity(params.id).catch(() => []),
        listQuotesByOpportunity(params.id).catch(() => []),
      ]);
      setOpportunity(opportunityRow);
      setInteractions(interactionRows);
      setTasks(taskRows);
      setQuotes(quoteRows);
    } catch (fetchError) {
      setError(fetchError instanceof Error ? fetchError.message : 'Failed to load opportunity.');
      setOpportunity(null);
      setInteractions([]);
      setTasks([]);
      setQuotes([]);
    } finally {
      setLoading(false);
    }
  }, [params.id]);

  useEffect(() => {
    void loadOpportunityData();
  }, [loadOpportunityData]);

  const sortedInteractions = useMemo(() => {
    return [...interactions].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return bTime - aTime;
    });
  }, [interactions]);

  const prefilledCompany: CompanySearchResult | null = opportunity
    ? {
      id: opportunity.company,
      name: opportunity.company_name || 'Selected company',
    }
    : null;

  const formatQuoteTotal = (quote: V3QuoteComputeResponse): string => {
    const totals = quote.latest_version?.totals;
    const amount = totals?.total_sell_fcy_incl_gst || totals?.total_sell_fcy || totals?.total_sell_pgk;
    const currency = totals?.total_sell_fcy_currency || totals?.currency || quote.output_currency || 'PGK';
    return formatCurrency(amount, currency);
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title={opportunity?.title || 'Opportunity Detail'}
          description={opportunity?.company_name ? `CRM opportunity for ${opportunity.company_name}` : 'Review CRM opportunity activity.'}
          actions={
            <div className="flex flex-wrap items-center gap-2">
              <Button variant="outline" asChild>
                <Link href="/crm/opportunities">Back to Opportunities</Link>
              </Button>
              {opportunity ? (
                <Button variant="outline" asChild>
                  <Link href={`/crm/opportunities/${opportunity.id}/edit`}>Edit</Link>
                </Button>
              ) : null}
              {opportunity ? (
                <Button type="button" onClick={() => setQuickLogOpen(true)}>
                  Log Activity
                </Button>
              ) : null}
            </div>
          }
        />

        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        {loading ? (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-6 text-sm text-muted-foreground">Loading opportunity...</CardContent>
          </Card>
        ) : opportunity ? (
          <>
            <Card className="border-slate-200 shadow-sm">
              <CardHeader className="pb-2">
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  <div>
                    <CardTitle className="text-lg">{opportunity.title}</CardTitle>
                    <CardDescription className="mt-1">
                      {[opportunity.origin, opportunity.destination].filter(Boolean).join(' - ') || 'No route set'}
                    </CardDescription>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Badge variant={statusBadgeVariant(opportunity.status)}>{opportunity.status}</Badge>
                    <Badge variant="outline">{opportunity.priority}</Badge>
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-6 pb-6 pt-2">
                <dl className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
                  <DetailItem label="Company" value={opportunity.company_name || '-'} />
                  <DetailItem label="Service Type" value={opportunity.service_type || '-'} />
                  <DetailItem label="Direction" value={opportunity.direction || opportunity.scope || '-'} />
                  <DetailItem label="Owner" value={opportunity.owner_username || '-'} />
                  <DetailItem label="Origin" value={opportunity.origin || '-'} />
                  <DetailItem label="Destination" value={opportunity.destination || '-'} />
                  <DetailItem label="Weight" value={formatMeasure(opportunity.estimated_weight_kg, ' kg')} />
                  <DetailItem label="Volume" value={formatMeasure(opportunity.estimated_volume_cbm, ' cbm')} />
                  <DetailItem label="FCL Count" value={formatMeasure(opportunity.estimated_fcl_count)} />
                  <DetailItem label="Estimated Revenue" value={formatCurrency(opportunity.estimated_revenue, opportunity.estimated_currency)} />
                  <DetailItem label="Next Action" value={opportunity.next_action || '-'} />
                  <DetailItem label="Next Action Date" value={formatDate(opportunity.next_action_date)} />
                  <DetailItem label="Last Activity" value={formatDateTime(opportunity.last_activity_at)} />
                  <DetailItem label="Won At" value={formatDateTime(opportunity.won_at)} />
                  <DetailItem label="Won Reason" value={opportunity.won_reason || '-'} />
                  <DetailItem label="Lost Reason" value={opportunity.lost_reason || '-'} />
                </dl>
              </CardContent>
            </Card>

            <Tabs defaultValue="timeline" className="space-y-4">
              <TabsList>
                <TabsTrigger value="timeline">Timeline</TabsTrigger>
                <TabsTrigger value="quotes">Quotes</TabsTrigger>
                <TabsTrigger value="tasks">Tasks</TabsTrigger>
              </TabsList>

              <TabsContent value="timeline" className="space-y-3">
                <Card className="border-slate-200 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg">Timeline</CardTitle>
                    <CardDescription>Newest interactions linked to this opportunity first.</CardDescription>
                  </CardHeader>
                  <CardContent className="space-y-3 px-6 pb-6 pt-2">
                    {sortedInteractions.length === 0 ? (
                      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                        No activity logged yet.
                      </p>
                    ) : (
                      sortedInteractions.map((interaction) => (
                        <TimelineItem key={interaction.id} interaction={interaction} />
                      ))
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="quotes">
                <Card className="border-slate-200 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg">Quotes</CardTitle>
                    <CardDescription>Quotes linked to this CRM opportunity.</CardDescription>
                  </CardHeader>
                  <CardContent className="px-6 pb-6 pt-2">
                    {quotes.length === 0 ? (
                      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                        No quotes linked to this opportunity.
                      </p>
                    ) : (
                      <div className="overflow-hidden rounded-md border border-slate-200">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Quote</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Created</TableHead>
                              <TableHead className="text-right">Total Sell</TableHead>
                              <TableHead className="text-right">Action</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {quotes.map((quote) => (
                              <TableRow key={quote.id}>
                                <TableCell className="font-medium">{quote.quote_number || quote.id}</TableCell>
                                <TableCell>{quote.status}</TableCell>
                                <TableCell>{formatDateTime(quote.created_at)}</TableCell>
                                <TableCell className="text-right tabular-nums">{formatQuoteTotal(quote)}</TableCell>
                                <TableCell className="text-right">
                                  <Button variant="ghost" size="sm" asChild>
                                    <Link href={`/quotes/${quote.id}`}>View</Link>
                                  </Button>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>

              <TabsContent value="tasks">
                <Card className="border-slate-200 shadow-sm">
                  <CardHeader className="pb-2">
                    <CardTitle className="text-lg">Tasks</CardTitle>
                    <CardDescription>Basic tasks linked to this opportunity.</CardDescription>
                  </CardHeader>
                  <CardContent className="px-6 pb-6 pt-2">
                    {tasks.length === 0 ? (
                      <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                        No tasks linked to this opportunity.
                      </p>
                    ) : (
                      <div className="overflow-hidden rounded-md border border-slate-200">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Description</TableHead>
                              <TableHead>Owner</TableHead>
                              <TableHead>Due Date</TableHead>
                              <TableHead>Status</TableHead>
                              <TableHead>Completed</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {tasks.map((task) => (
                              <TableRow key={task.id}>
                                <TableCell className="font-medium">{task.description}</TableCell>
                                <TableCell>{task.owner_username || '-'}</TableCell>
                                <TableCell>{formatDate(task.due_date)}</TableCell>
                                <TableCell>{task.status}</TableCell>
                                <TableCell>{formatDateTime(task.completed_at)}</TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </CardContent>
                </Card>
              </TabsContent>
            </Tabs>
          </>
        ) : (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-6 text-sm text-muted-foreground">Opportunity not found.</CardContent>
          </Card>
        )}

        <InteractionLogSheet
          open={quickLogOpen}
          onOpenChange={(nextOpen) => {
            setQuickLogOpen(nextOpen);
            if (!nextOpen) {
              void loadOpportunityData();
            }
          }}
          prefilledCompany={prefilledCompany}
          prefilledOpportunity={opportunity}
        />
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
