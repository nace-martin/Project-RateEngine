import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export default function SettingsPage() {
  return (
    <div className="container mx-auto p-4">
      <h1 className="text-2xl font-bold mb-4">Settings</h1>
      <div className="grid gap-4">
        <Card>
          <CardHeader>
            <CardTitle>Rate Cards</CardTitle>
            <CardDescription>Manage your rate cards and pricing data.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link href="/pricing/rate-cards">Go to Rate Cards</Link>
            </Button>
          </CardContent>
        </Card>
        {/* You can add more settings cards here in the future */}
      </div>
    </div>
  );
}