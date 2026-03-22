'use client';

import OrganizationBrandingSettings from '@/components/OrganizationBrandingSettings';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { usePermissions } from '@/hooks/usePermissions';
import { Card, CardContent } from '@/components/ui/card';

export default function CompanyBrandingPage() {
  const { isAdmin } = usePermissions();

  return (
    <StandardPageContainer>
      <PageHeader
        title="Company Branding"
        description="Manage your logo, colors, and company details used across customer-facing quote documents."
      />

      {!isAdmin ? (
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="px-6 py-5 text-sm text-muted-foreground">
            You do not have access to company branding settings.
          </CardContent>
        </Card>
      ) : (
        <OrganizationBrandingSettings />
      )}
    </StandardPageContainer>
  );
}
