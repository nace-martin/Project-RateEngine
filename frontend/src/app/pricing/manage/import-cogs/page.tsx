'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  createImportCOGS,
  getImportCOGSHistory,
  listImportCOGS,
  reviseImportCOGS,
  retireImportCOGS,
  updateImportCOGS,
} from '@/lib/api';

export default function ImportCOGSManagementPage() {
  return (
    <LaneRateManagerPage
      title="Import COGS Management"
      description="Manage V4 import lane buy-side rows without touching the legacy rate-card stack."
      pathLabel="Import COGS"
      productDomain="IMPORT"
      routeFieldNames={{
        origin: 'origin_airport',
        destination: 'destination_airport',
        originLabel: 'Origin Airport',
        destinationLabel: 'Destination Airport',
      }}
      supportsCounterparty={true}
      supportsPercent={true}
      listRates={listImportCOGS}
      createRate={createImportCOGS}
      updateRate={updateImportCOGS}
      reviseRate={reviseImportCOGS}
      retireRate={retireImportCOGS}
      loadHistory={getImportCOGSHistory}
    />
  );
}
