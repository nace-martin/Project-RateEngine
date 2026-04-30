'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
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
import { InteractionLogSheet } from '@/components/crm/InteractionLogSheet';
import { listInteractionsByCompany, listOpportunitiesByCompany } from '@/lib/api/crm';
import type { CompanySearchResult, Interaction, Opportunity } from '@/lib/types';

type CustomerCrmActivityCardProps = {
  company: CompanySearchResult;
};

const interactionLabels: Record<string, string> = {
  CALL: 'Call',
  MEETING: 'Meeting',
  EMAIL: 'Email',
  SITE_VISIT: 'Site Visit',
  SYSTEM: 'System',
};

const activeOpportunityStatuses = new Set(['NEW', 'QUALIFIED', 'QUOTED']);

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

function formatDate(value?: string | null): string {
  if (!value) return '-';
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
  });
}

function TimelineItem({
  interaction,
  opportunityById,
}: {
  interaction: Interaction;
  opportunityById: Map<string, Opportunity>;
}) {
  const opportunity = interaction.opportunity ? opportunityById.get(interaction.opportunity) : null;
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
      {opportunity ? (
        <p className="mt-2 text-xs font-medium text-slate-600">Opportunity: {opportunity.title}</p>
      ) : interaction.opportunity ? (
        <p className="mt-2 text-xs font-medium text-slate-600">Opportunity linked</p>
      ) : null}
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

export function CustomerCrmActivityCard({ company }: CustomerCrmActivityCardProps) {
  const [quickLogOpen, setQuickLogOpen] = useState(false);
  const [interactions, setInteractions] = useState<Interaction[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadCrmData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [interactionRows, opportunityRows] = await Promise.all([
        listInteractionsByCompany(company.id),
        listOpportunitiesByCompany(company.id),
      ]);
      setInteractions(interactionRows);
      setOpportunities(opportunityRows);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Failed to load CRM activity.');
    } finally {
      setLoading(false);
    }
  }, [company.id]);

  useEffect(() => {
    void loadCrmData();
  }, [loadCrmData]);

  const opportunityById = useMemo(() => {
    return new Map(opportunities.map((opportunity) => [opportunity.id, opportunity]));
  }, [opportunities]);

  const activeOpportunities = useMemo(() => {
    return opportunities.filter((opportunity) => activeOpportunityStatuses.has(opportunity.status));
  }, [opportunities]);

  const sortedInteractions = useMemo(() => {
    return [...interactions].sort((a, b) => {
      const aTime = a.created_at ? new Date(a.created_at).getTime() : 0;
      const bTime = b.created_at ? new Date(b.created_at).getTime() : 0;
      return bTime - aTime;
    });
  }, [interactions]);

  return (
    <Card className="border-slate-200 shadow-sm">
      <CardHeader className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <CardTitle>CRM Activity</CardTitle>
          <CardDescription className="mt-1">
            Review customer activity and log interactions for this account.
          </CardDescription>
        </div>
        <Button type="button" variant="outline" onClick={() => setQuickLogOpen(true)}>
          Log Activity
        </Button>
      </CardHeader>
      <CardContent className="space-y-6 px-6 pb-6 pt-2">
        {error ? (
          <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700">
            {error}
          </div>
        ) : null}

        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Active Opportunities</h3>
            <p className="text-sm text-muted-foreground">Open CRM opportunities linked to this customer.</p>
          </div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading opportunities...</p>
          ) : activeOpportunities.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No active opportunities.
            </p>
          ) : (
            <div className="overflow-hidden rounded-md border border-slate-200">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Title</TableHead>
                    <TableHead>Service</TableHead>
                    <TableHead>Route</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Priority</TableHead>
                    <TableHead>Next Action</TableHead>
                    <TableHead>Last Activity</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {activeOpportunities.map((opportunity) => (
                    <TableRow key={opportunity.id}>
                      <TableCell className="font-medium">{opportunity.title}</TableCell>
                      <TableCell>{opportunity.service_type}</TableCell>
                      <TableCell>{[opportunity.origin, opportunity.destination].filter(Boolean).join(' - ') || '-'}</TableCell>
                      <TableCell>{opportunity.status}</TableCell>
                      <TableCell>{opportunity.priority}</TableCell>
                      <TableCell>{formatDate(opportunity.next_action_date)}</TableCell>
                      <TableCell>{formatDateTime(opportunity.last_activity_at)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </section>

        <section className="space-y-3">
          <div>
            <h3 className="text-base font-semibold text-slate-900">Timeline</h3>
            <p className="text-sm text-muted-foreground">Newest customer interactions first.</p>
          </div>
          {loading ? (
            <p className="text-sm text-muted-foreground">Loading activity...</p>
          ) : sortedInteractions.length === 0 ? (
            <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
              No activity logged yet.
            </p>
          ) : (
            <div className="space-y-3">
              {sortedInteractions.map((interaction) => (
                <TimelineItem
                  key={interaction.id}
                  interaction={interaction}
                  opportunityById={opportunityById}
                />
              ))}
            </div>
          )}
        </section>
      </CardContent>

      <InteractionLogSheet
        open={quickLogOpen}
        onOpenChange={(nextOpen) => {
          setQuickLogOpen(nextOpen);
          if (!nextOpen) {
            void loadCrmData();
          }
        }}
        prefilledCompany={company}
      />
    </Card>
  );
}
