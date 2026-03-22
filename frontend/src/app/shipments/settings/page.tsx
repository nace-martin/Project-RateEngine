'use client';

import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { usePermissions } from "@/hooks/usePermissions";
import { getShipmentSettings, updateShipmentSettings } from "@/lib/api/shipments";
import { ShipmentSettings } from "@/lib/shipment-types";

export default function ShipmentSettingsPage() {
  const { isAdmin } = usePermissions();
  const [settings, setSettings] = useState<ShipmentSettings | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      try {
        setSettings(await getShipmentSettings());
        setError(null);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unable to load shipment settings.");
      }
    };
    if (isAdmin) void run();
  }, [isAdmin]);

  if (!isAdmin) {
    return (
      <ProtectedRoute>
        <StandardPageContainer>
          <PageHeader title="Shipment Settings" description="Admin-only numbering and connote defaults." />
          <Card><CardContent className="p-6 text-sm text-muted-foreground">You do not have access to shipment settings.</CardContent></Card>
        </StandardPageContainer>
      </ProtectedRoute>
    );
  }

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader title="Shipment Settings" description="Control connote numbering prefixes and the default disclaimer printed on generated connotes." />
        {!settings ? (
          <Card><CardContent className="p-6 text-sm text-muted-foreground">{error || "Loading settings..."}</CardContent></Card>
        ) : (
          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle className="text-lg">Connote Defaults</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                <Input placeholder="Station code" value={settings.connote_station_code} onChange={(event) => setSettings((current) => current ? { ...current, connote_station_code: event.target.value.toUpperCase() } : current)} />
                <Input placeholder="Mode code" value={settings.connote_mode_code} onChange={(event) => setSettings((current) => current ? { ...current, connote_mode_code: event.target.value.toUpperCase() } : current)} />
              </div>
              <Textarea placeholder="Default connote disclaimer" value={settings.default_disclaimer} onChange={(event) => setSettings((current) => current ? { ...current, default_disclaimer: event.target.value } : current)} />
              <Button onClick={async () => setSettings(await updateShipmentSettings(settings))}>Save Settings</Button>
            </CardContent>
          </Card>
        )}
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
