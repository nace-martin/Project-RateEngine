import RateCardUploader from '@/components/rate-card-uploader';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

export default function SettingsPage() {
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <div className="grid gap-4">
        <RateCardUploader />
        {/* You can add more settings cards here in the future */}
      </div>
    </div>
  );
}