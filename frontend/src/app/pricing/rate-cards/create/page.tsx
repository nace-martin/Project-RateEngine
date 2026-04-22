import { redirect } from 'next/navigation';

export default function DeprecatedRateCardCreatePage() {
  redirect('/pricing/manage');
}
