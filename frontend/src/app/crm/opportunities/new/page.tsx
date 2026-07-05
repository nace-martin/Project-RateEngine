'use client';

import Link from 'next/link';

import { OpportunityForm } from '@/components/crm/OpportunityForm';
import ProtectedRoute from '@/components/protected-route';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { usePermissions } from '@/hooks/usePermissions';

export default function NewOpportunityPage() {
  const { canEditCRM } = usePermissions();

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="New Opportunity"
          description="Create a CRM opportunity for a customer lane or service need."
          actions={
            <Button variant="outline" asChild>
              <Link href="/crm/opportunities">Back to Opportunities</Link>
            </Button>
          }
        />
        {canEditCRM ? (
          <OpportunityForm mode="create" />
        ) : (
          <Card className="border-amber-200 bg-amber-50 shadow-sm">
            <CardContent className="p-6 text-sm text-amber-900">
              You do not have permission to create CRM opportunities.
            </CardContent>
          </Card>
        )}
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
