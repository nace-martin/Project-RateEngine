'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  getImportSellRateHistory,
  createImportSellRate,
  listImportSellRates,
  reviseImportSellRate,
  retireImportSellRate,
  updateImportSellRate,
} from '@/lib/api';

export default function ImportSellManagementPage() {
  return (
    <LaneRateManagerPage
      title="Import Sell Management"
      description="Manage V4 import sell rates where explicit lane sell rows are active."
      pathLabel="Import Sell"
      productDomain="IMPORT"
      routeFieldNames={{
        origin: 'origin_airport',
        destination: 'destination_airport',
        originLabel: 'Origin Airport',
        destinationLabel: 'Destination Airport',
      }}
      supportsCounterparty={false}
      supportsPercent={true}
      listRates={listImportSellRates}
      createRate={createImportSellRate}
      updateRate={updateImportSellRate}
      reviseRate={reviseImportSellRate}
      retireRate={retireImportSellRate}
      loadHistory={getImportSellRateHistory}
    />
  );
}
