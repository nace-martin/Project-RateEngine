'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useState } from 'react';

import { OpportunityForm } from '@/components/crm/OpportunityForm';
import ProtectedRoute from '@/components/protected-route';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { getOpportunity } from '@/lib/api/crm';
import type { Opportunity } from '@/lib/types';

export default function EditOpportunityPage() {
  const params = useParams<{ id: string }>();
  const [opportunity, setOpportunity] = useState<Opportunity | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    getOpportunity(params.id)
      .then((row) => {
        if (!active) return;
        setOpportunity(row);
      })
      .catch((fetchError: Error) => {
        if (!active) return;
        setError(fetchError.message || 'Failed to load opportunity.');
        setOpportunity(null);
      })
      .finally(() => {
        if (active) {
          setLoading(false);
        }
      });

    return () => {
      active = false;
    };
  }, [params.id]);

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="Edit Opportunity"
          description={opportunity?.company_name ? `Update CRM opportunity for ${opportunity.company_name}.` : 'Update CRM opportunity details.'}
          actions={
            <Button variant="outline" asChild>
              <Link href={`/crm/opportunities/${params.id}`}>Back to Detail</Link>
            </Button>
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
          <OpportunityForm mode="edit" opportunity={opportunity} />
        ) : (
          <Card className="border-slate-200 shadow-sm">
            <CardContent className="p-6 text-sm text-muted-foreground">Opportunity not found.</CardContent>
          </Card>
        )}
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
