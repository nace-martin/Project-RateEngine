'use client';

import LocalRateManagerPage from '@/components/pricing/rate-manager/LocalRateManagerPage';
import {
  createLocalSellRate,
  getLocalSellRateHistory,
  listLocalSellRates,
  reviseLocalSellRate,
  retireLocalSellRate,
  updateLocalSellRate,
} from '@/lib/api';

export default function LocalSellManagementPage() {
  return (
    <LocalRateManagerPage
      title="Local Sell Management"
      description="Manage V4 origin and destination local sell charges."
      pathLabel="Local Sell"
      productDomains={['EXPORT', 'IMPORT']}
      supportsPaymentTerm={true}
      supportsCounterparty={false}
      listRates={listLocalSellRates}
      createRate={createLocalSellRate}
      updateRate={updateLocalSellRate}
      reviseRate={reviseLocalSellRate}
      retireRate={retireLocalSellRate}
      loadHistory={getLocalSellRateHistory}
    />
  );
}
