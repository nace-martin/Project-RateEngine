'use client';

import Link from 'next/link';
import { StandardPageContainer, PageHeader } from '@/components/layout/standard-page';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { RATE_MANAGEMENT_LINKS } from '@/lib/pricing-management';

export default function PricingManageLandingPage() {
  return (
    <StandardPageContainer>
      <PageHeader
        title="V4 Rate Managers"
        description="Manager/admin CRUD surfaces for the live V4 pricing tables."
      />

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {RATE_MANAGEMENT_LINKS.map((link) => (
          <Card key={link.table} className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="text-lg">{link.label}</CardTitle>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-4">
              <div className="text-sm text-muted-foreground">{link.table}</div>
              <Button asChild>
                <Link href={link.href}>Open</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </StandardPageContainer>
  );
}
