'use client';

import { PageHeader, StandardPageContainer } from '@/components/layout/standard-page';
import FxRateManagement from '@/components/FxRateManagement';
import { usePermissions } from '@/hooks/usePermissions';
import { Card, CardContent } from '@/components/ui/card';

export default function PricingEnginePage() {
  const { canEditFXRates, isFinance, isAdmin } = usePermissions();
  const canView = isFinance || isAdmin;

  return (
    <StandardPageContainer>
      <PageHeader
        title="Pricing Engine"
        description="Core pricing controls for FX and future engine policies."
      />

      {!canView ? (
        <Card className="border-slate-200 shadow-sm">
          <CardContent className="px-6 py-5 text-sm text-muted-foreground">
            You do not have access to pricing engine controls.
          </CardContent>
        </Card>
      ) : (
        <FxRateManagement canEditFxRates={canEditFXRates} />
      )}
    </StandardPageContainer>
  );
}
