'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  createExportSellRate,
  getExportSellRateHistory,
  listExportSellRates,
  reviseExportSellRate,
  retireExportSellRate,
  updateExportSellRate,
} from '@/lib/api';

export default function ExportSellManagementPage() {
  return (
    <LaneRateManagerPage
      title="Export Sell Management"
      description="Manage V4 export sell rates for live lane pricing."
      pathLabel="Export Sell"
      productDomain="EXPORT"
      routeFieldNames={{
        origin: 'origin_airport',
        destination: 'destination_airport',
        originLabel: 'Origin Airport',
        destinationLabel: 'Destination Airport',
      }}
      supportsCounterparty={false}
      supportsPercent={true}
      listRates={listExportSellRates}
      createRate={createExportSellRate}
      updateRate={updateExportSellRate}
      reviseRate={reviseExportSellRate}
      retireRate={retireExportSellRate}
      loadHistory={getExportSellRateHistory}
    />
  );
}
