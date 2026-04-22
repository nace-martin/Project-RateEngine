'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  createDomesticSellRate,
  getDomesticSellRateHistory,
  listDomesticSellRates,
  reviseDomesticSellRate,
  retireDomesticSellRate,
  updateDomesticSellRate,
} from '@/lib/api';

export default function DomesticSellManagementPage() {
  return (
    <LaneRateManagerPage
      title="Domestic Sell Management"
      description="Manage V4 domestic sell tariffs used by the launch corridors."
      pathLabel="Domestic Sell"
      productDomain="DOMESTIC"
      routeFieldNames={{
        origin: 'origin_zone',
        destination: 'destination_zone',
        originLabel: 'Origin Zone',
        destinationLabel: 'Destination Zone',
      }}
      supportsCounterparty={false}
      supportsPercent={true}
      listRates={listDomesticSellRates}
      createRate={createDomesticSellRate}
      updateRate={updateDomesticSellRate}
      reviseRate={reviseDomesticSellRate}
      retireRate={retireDomesticSellRate}
      loadHistory={getDomesticSellRateHistory}
    />
  );
}
