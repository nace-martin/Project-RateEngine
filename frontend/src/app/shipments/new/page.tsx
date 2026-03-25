'use client';

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import ProtectedRoute from "@/components/protected-route";
import ShipmentWizard from "@/components/shipments/ShipmentWizard";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Card, CardContent } from "@/components/ui/card";
import { getShipment, listShipmentAddressBook, listShipmentTemplates } from "@/lib/api/shipments";
import { ShipmentAddressBookEntry, ShipmentRecord, ShipmentTemplate } from "@/lib/shipment-types";

function NewShipmentPageContent() {
  const searchParams = useSearchParams();
  const shipmentId = searchParams.get("shipmentId") || undefined;
  const [addressBookEntries, setAddressBookEntries] = useState<ShipmentAddressBookEntry[]>([]);
  const [templates, setTemplates] = useState<ShipmentTemplate[]>([]);
  const [initialShipment, setInitialShipment] = useState<ShipmentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const [entryData, templateData, shipmentData] = await Promise.all([
          listShipmentAddressBook().catch(() => []),
          listShipmentTemplates().catch(() => []),
          shipmentId ? getShipment(shipmentId) : Promise.resolve(null),
        ]);
        setAddressBookEntries(entryData);
        setTemplates(templateData);
        setInitialShipment(shipmentData);
        setError(null);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unable to load shipment setup.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [shipmentId]);

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title={shipmentId ? "Edit Shipment Draft" : "New Shipment"}
          description="Create a domestic or export air freight shipment record and generate the connote as the output."
        />
        {loading ? (
          <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading shipment workspace...</CardContent></Card>
        ) : error ? (
          <Card><CardContent className="p-6 text-sm text-red-600">{error}</CardContent></Card>
        ) : (
          <ShipmentWizard
            shipmentId={shipmentId}
            initialShipment={initialShipment}
            templates={templates}
            addressBookEntries={addressBookEntries}
          />
        )}
      </StandardPageContainer>
    </ProtectedRoute>
  );
}

export default function NewShipmentPage() {
  return (
    <Suspense fallback={
      <ProtectedRoute>
        <StandardPageContainer>
          <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading shipment workspace...</CardContent></Card>
        </StandardPageContainer>
      </ProtectedRoute>
    }>
      <NewShipmentPageContent />
    </Suspense>
  );
}
