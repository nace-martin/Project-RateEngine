'use client';

import LocalRateManagerPage from '@/components/pricing/rate-manager/LocalRateManagerPage';
import {
  createLocalCOGSRate,
  getLocalCOGSRateHistory,
  listLocalCOGSRates,
  reviseLocalCOGSRate,
  retireLocalCOGSRate,
  updateLocalCOGSRate,
} from '@/lib/api';

export default function LocalCOGSManagementPage() {
  return (
    <LocalRateManagerPage
      title="Local COGS Management"
      description="Manage V4 origin and destination local buy-side charges."
      pathLabel="Local COGS"
      productDomains={['EXPORT', 'IMPORT']}
      supportsPaymentTerm={false}
      supportsCounterparty={true}
      listRates={listLocalCOGSRates}
      createRate={createLocalCOGSRate}
      updateRate={updateLocalCOGSRate}
      reviseRate={reviseLocalCOGSRate}
      retireRate={retireLocalCOGSRate}
      loadHistory={getLocalCOGSRateHistory}
    />
  );
}
