'use client';

import Link from 'next/link';

import { OpportunityForm } from '@/components/crm/OpportunityForm';
import ProtectedRoute from '@/components/protected-route';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Button } from '@/components/ui/button';

export default function NewOpportunityPage() {
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
        <OpportunityForm mode="create" />
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
