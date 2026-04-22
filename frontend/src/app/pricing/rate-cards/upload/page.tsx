import Link from 'next/link';

import PageBackButton from '@/components/navigation/PageBackButton';
import { RateCardUploader } from '@/components/pricing/RateCardUploader';

export default function RateCardBulkUploadPage() {
  return (
    <div className="container mx-auto max-w-6xl space-y-6 py-8">
      <div className="space-y-2">
        <PageBackButton fallbackHref="/pricing/rate-cards" />
        <div className="text-xs font-semibold uppercase tracking-[0.16em] text-blue-700">
          Pricing Command Center
        </div>
        <h1 className="text-3xl font-semibold tracking-tight text-slate-900">
          V4 Rate Card Bulk Upload
        </h1>
        <p className="max-w-3xl text-sm text-slate-600">
          Upload validated CSV rate sheets for V4 sell rates. Preview runs compare planned creates versus updates before commit, and live imports still fully roll back if any row fails validation.
        </p>
        <div className="text-sm">
          <Link href="/pricing/rate-cards" className="text-blue-700 underline underline-offset-2 hover:text-blue-900">
            Back to Rate Cards grid
          </Link>
        </div>
      </div>

      <RateCardUploader />
    </div>
  );
}
