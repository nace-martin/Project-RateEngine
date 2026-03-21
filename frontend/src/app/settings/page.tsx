'use client';

import Link from 'next/link';
import { Building2, Database, Settings2, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { usePermissions } from '@/hooks/usePermissions';

export default function SettingsPage() {
  const { canEditRateCards, isFinance, isAdmin } = usePermissions();

  const showPricingEngine = isFinance || isAdmin;
  const showUsers = isAdmin;
  const showBranding = isAdmin;

  return (
    <StandardPageContainer>
      <PageHeader
        title="Admin Hub"
        description="Use the functional modules below instead of one catch-all settings page."
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {showPricingEngine && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Settings2 className="h-5 w-5 text-primary" />
                Pricing Engine
              </CardTitle>
              <CardDescription>
                Maintain FX rates and future pricing-engine controls such as policy, margin, and CAF settings.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link href="/pricing/engine">Open Pricing Engine</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {canEditRateCards && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Database className="h-5 w-5 text-primary" />
                Rate Management
              </CardTitle>
              <CardDescription>
                Manage logical rate cards, tariffs, sell rates, and buy-side pricing data.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link href="/pricing/rate-cards">Open Rate Management</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {showBranding && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Building2 className="h-5 w-5 text-primary" />
                Company Branding
              </CardTitle>
              <CardDescription>
                Manage logo upload, colors, contact details, and customer-facing tenant branding.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link href="/company/branding">Open Branding</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {showUsers && (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Users className="h-5 w-5 text-primary" />
                System Admin
              </CardTitle>
              <CardDescription>
                Manage user access and administrative controls without mixing them into pricing modules.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link href="/settings/users">Open User Management</Link>
              </Button>
            </CardContent>
          </Card>
        )}
      </div>

      {!showPricingEngine && !canEditRateCards && !showBranding && !showUsers && (
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="px-6 py-5 text-sm text-muted-foreground">
            No administrative modules are available for your role.
          </CardContent>
        </Card>
      )}
    </StandardPageContainer>
  );
}
