'use client';

import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import OrganizationBrandingSettings from '@/components/OrganizationBrandingSettings';
import { usePermissions } from '@/hooks/usePermissions';
import FxRateManagement from '@/components/FxRateManagement';

export default function SettingsPage() {
  const { canEditRateCards, canEditFXRates, isFinance, isAdmin } = usePermissions();

  // Check if user should see financial settings (Finance or Admin)
  const showFinancialSettings = isFinance || isAdmin;

  return (
    <div className="container mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-bold mb-4">Settings</h1>

      <div className="grid gap-6">
        {/* Rate Cards - Available to Manager/Admin */}
        {canEditRateCards && (
          <Card>
            <CardHeader>
              <CardTitle>Rate Cards</CardTitle>
              <CardDescription>Manage your rate cards and pricing data.</CardDescription>
            </CardHeader>
            <CardContent>
              <Button asChild>
                <Link href="/pricing/rate-cards">Go to Rate Cards</Link>
              </Button>
            </CardContent>
          </Card>
        )}

        {/* Financial Settings Section - Finance/Admin only */}
        {showFinancialSettings && (
          <>
            <div className="border-t pt-4">
              <h2 className="text-lg font-semibold mb-4 text-muted-foreground">
                Financial Settings
              </h2>
            </div>

            {/* FX Rate Management */}
            <FxRateManagement canEditFxRates={canEditFXRates} />
          </>
        )}

        {isAdmin && (
          <>
            <div className="border-t pt-4">
              <h2 className="text-lg font-semibold mb-4 text-muted-foreground">
                Branding
              </h2>
            </div>
            <OrganizationBrandingSettings />
          </>
        )}
      </div>
    </div>
  );
}
