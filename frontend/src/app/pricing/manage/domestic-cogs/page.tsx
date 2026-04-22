'use client';

import LaneRateManagerPage from '@/components/pricing/rate-manager/LaneRateManagerPage';
import {
  createDomesticCOGS,
  getDomesticCOGSHistory,
  listDomesticCOGS,
  reviseDomesticCOGS,
  retireDomesticCOGS,
  updateDomesticCOGS,
} from '@/lib/api';

export default function DomesticCOGSManagementPage() {
  return (
    <LaneRateManagerPage
      title="Domestic COGS Management"
      description="Manage V4 domestic buy-side rows for deterministic domestic pricing."
      pathLabel="Domestic COGS"
      productDomain="DOMESTIC"
      routeFieldNames={{
        origin: 'origin_zone',
        destination: 'destination_zone',
        originLabel: 'Origin Zone',
        destinationLabel: 'Destination Zone',
      }}
      supportsCounterparty={true}
      supportsPercent={false}
      listRates={listDomesticCOGS}
      createRate={createDomesticCOGS}
      updateRate={updateDomesticCOGS}
      reviseRate={reviseDomesticCOGS}
      retireRate={retireDomesticCOGS}
      loadHistory={getDomesticCOGSHistory}
    />
  );
}
