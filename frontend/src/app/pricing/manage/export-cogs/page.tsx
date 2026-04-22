'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  createExportCOGS,
  getExportCOGSHistory,
  listExportCOGS,
  reviseExportCOGS,
  retireExportCOGS,
  updateExportCOGS,
} from '@/lib/api';

export default function ExportCOGSManagementPage() {
  return (
    <LaneRateManagerPage
      title="Export COGS Management"
      description="Manage V4 export lane buy-side rows without relying on legacy ratecard CRUD."
      pathLabel="Export COGS"
      productDomain="EXPORT"
      routeFieldNames={{
        origin: 'origin_airport',
        destination: 'destination_airport',
        originLabel: 'Origin Airport',
        destinationLabel: 'Destination Airport',
      }}
      supportsCounterparty={true}
      supportsPercent={false}
      listRates={listExportCOGS}
      createRate={createExportCOGS}
      updateRate={updateExportCOGS}
      reviseRate={reviseExportCOGS}
      retireRate={retireExportCOGS}
      loadHistory={getExportCOGSHistory}
    />
  );
}
