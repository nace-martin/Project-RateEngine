'use client';

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { PlusCircle, Search } from "lucide-react";

import ProtectedRoute from "@/components/protected-route";
import { ShipmentStatusBadge } from "@/components/shipments/ShipmentStatusBadge";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { listShipments, openShipmentPdf } from "@/lib/api/shipments";
import { ShipmentRecord } from "@/lib/shipment-types";

export default function ShipmentsPage() {
  const [shipments, setShipments] = useState<ShipmentRecord[]>([]);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const data = await listShipments();
        setShipments(data);
        setError(null);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unable to load shipments.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, []);

  const filtered = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return shipments;
    return shipments.filter((shipment) =>
      [
        shipment.connote_number,
        shipment.reference_number,
        shipment.shipper_company_name,
        shipment.consignee_company_name,
        shipment.origin_code,
        shipment.destination_code,
      ].some((value) => (value || "").toLowerCase().includes(normalized)),
    );
  }, [query, shipments]);

  const metrics = useMemo(() => ({
    drafts: shipments.filter((shipment) => shipment.status === "DRAFT").length,
    finalized: shipments.filter((shipment) => shipment.status === "FINALIZED").length,
    cancelled: shipments.filter((shipment) => shipment.status === "CANCELLED").length,
    reissued: shipments.filter((shipment) => shipment.status === "REISSUED").length,
  }), [shipments]);

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="Shipment Dashboard"
          description="Search, resume, reprint, and manage internal air freight connotes from one operational register."
          actions={
            <>
              <Link href="/shipments/address-book"><Button variant="outline">Address Book</Button></Link>
              <Link href="/shipments/templates"><Button variant="outline">Templates</Button></Link>
              <Link href="/shipments/settings"><Button variant="outline">Admin Settings</Button></Link>
              <Link href="/shipments/new"><Button><PlusCircle className="mr-2 h-4 w-4" />New Shipment</Button></Link>
            </>
          }
        />

        <div className="grid gap-4 md:grid-cols-4">
          {[
            { label: "Drafts", value: metrics.drafts },
            { label: "Finalized", value: metrics.finalized },
            { label: "Cancelled", value: metrics.cancelled },
            { label: "Reissued", value: metrics.reissued },
          ].map((metric) => (
            <Card key={metric.label} className="border-slate-200 shadow-sm">
              <CardContent className="p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{metric.label}</p>
                <p className="mt-2 text-3xl font-bold text-slate-900">{metric.value}</p>
              </CardContent>
            </Card>
          ))}
        </div>

        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle className="text-lg">Shipment Register</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="relative max-w-md">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <Input className="pl-9" placeholder="Search connote, reference, party, or route" value={query} onChange={(event) => setQuery(event.target.value)} />
            </div>

            {loading ? (
              <div className="text-sm text-muted-foreground">Loading shipments...</div>
            ) : error ? (
              <div className="text-sm text-red-600">{error}</div>
            ) : (
              <div className="overflow-x-auto rounded-lg border border-slate-200">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Connote</TableHead>
                      <TableHead>Route</TableHead>
                      <TableHead>Shipper</TableHead>
                      <TableHead>Consignee</TableHead>
                      <TableHead>Chargeable Wt</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Actions</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filtered.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={7} className="h-24 text-center text-muted-foreground">
                          No shipments found.
                        </TableCell>
                      </TableRow>
                    ) : filtered.map((shipment) => (
                      <TableRow key={shipment.id}>
                        <TableCell className="font-medium">{shipment.connote_number || "Draft pending finalization"}</TableCell>
                        <TableCell>{shipment.origin_code || shipment.origin_location_display} → {shipment.destination_code || shipment.destination_location_display}</TableCell>
                        <TableCell>{shipment.shipper_company_name}</TableCell>
                        <TableCell>{shipment.consignee_company_name}</TableCell>
                        <TableCell>{shipment.total_chargeable_weight_kg} kg</TableCell>
                        <TableCell><ShipmentStatusBadge status={shipment.status} /></TableCell>
                        <TableCell className="space-x-2 text-right">
                          <Button variant="ghost" size="sm" asChild>
                            <Link href={`/shipments/${shipment.id}`}>View</Link>
                          </Button>
                          {shipment.status === "FINALIZED" && (
                            <Button variant="ghost" size="sm" onClick={() => openShipmentPdf(shipment.id)}>
                              Reprint
                            </Button>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </CardContent>
        </Card>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
