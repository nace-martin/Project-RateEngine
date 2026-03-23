'use client';

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { ShipmentStatusBadge } from "@/components/shipments/ShipmentStatusBadge";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cancelShipment, duplicateShipment, getShipment, openShipmentPdf, reissueShipment } from "@/lib/api/shipments";
import { ShipmentRecord } from "@/lib/shipment-types";

export default function ShipmentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [shipment, setShipment] = useState<ShipmentRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      setLoading(true);
      try {
        const data = await getShipment(params.id);
        setShipment(data);
        setError(null);
      } catch (fetchError) {
        setError(fetchError instanceof Error ? fetchError.message : "Unable to load shipment.");
      } finally {
        setLoading(false);
      }
    };
    run();
  }, [params.id]);

  const handleDuplicate = async () => {
    if (!shipment) return;
    const duplicated = await duplicateShipment(shipment.id);
    router.push(`/shipments/new?shipmentId=${duplicated.id}`);
  };

  const handleReissue = async () => {
    if (!shipment) return;
    const reissued = await reissueShipment(shipment.id);
    router.push(`/shipments/new?shipmentId=${reissued.id}`);
  };

  const handleCancel = async () => {
    if (!shipment) return;
    const reason = window.prompt("Cancellation reason", shipment.cancelled_reason || "");
    if (reason === null) return;
    const cancelled = await cancelShipment(shipment.id, reason);
    setShipment(cancelled);
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title={shipment?.connote_number || "Shipment Detail"}
          description="Review shipment data, audit trail, print outputs, and operational status history."
          actions={
            shipment ? (
              <>
                {shipment.status === "DRAFT" && <Link href={`/shipments/new?shipmentId=${shipment.id}`}><Button variant="outline">Edit Draft</Button></Link>}
                {shipment.status === "FINALIZED" && <Button variant="outline" onClick={() => openShipmentPdf(shipment.id)}>Open PDF</Button>}
                <Button variant="outline" onClick={handleDuplicate}>Duplicate</Button>
                <Button variant="outline" onClick={handleReissue}>Reissue</Button>
                {shipment.status !== "CANCELLED" && <Button variant="outline" onClick={handleCancel}>Cancel</Button>}
              </>
            ) : null
          }
        />

        {loading ? (
          <Card><CardContent className="p-6 text-sm text-muted-foreground">Loading shipment detail...</CardContent></Card>
        ) : error || !shipment ? (
          <Card><CardContent className="p-6 text-sm text-red-600">{error || "Shipment not found."}</CardContent></Card>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-4">
              {[
                { label: "Status", value: <ShipmentStatusBadge status={shipment.status} /> },
                { label: "Route", value: `${shipment.origin_code} → ${shipment.destination_code}` },
                { label: "Chargeable", value: `${shipment.total_chargeable_weight_kg} kg` },
                { label: "Charges", value: `${shipment.currency} ${shipment.total_charges_amount}` },
              ].map((metric) => (
                <Card key={metric.label} className="border-slate-200 shadow-sm">
                  <CardContent className="p-5">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">{metric.label}</p>
                    <div className="mt-2 font-semibold text-slate-900">{metric.value}</div>
                  </CardContent>
                </Card>
              ))}
            </div>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="text-lg">Parties</CardTitle></CardHeader>
                <CardContent className="grid gap-4 md:grid-cols-2 text-sm">
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Shipper</p>
                    <p className="mt-2 font-semibold text-slate-900">{shipment.shipper_company_name}</p>
                    <p className="text-muted-foreground">{shipment.shipper_contact_name}</p>
                    <p className="mt-2 text-muted-foreground">{shipment.shipper_address_line_1}</p>
                    <p className="text-muted-foreground">{shipment.shipper_city} {shipment.shipper_state} {shipment.shipper_postal_code}</p>
                    <p className="text-muted-foreground">{shipment.shipper_country_code}</p>
                  </div>
                  <div className="rounded-xl border border-slate-200 p-4">
                    <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Consignee</p>
                    <p className="mt-2 font-semibold text-slate-900">{shipment.consignee_company_name}</p>
                    <p className="text-muted-foreground">{shipment.consignee_contact_name}</p>
                    <p className="mt-2 text-muted-foreground">{shipment.consignee_address_line_1}</p>
                    <p className="text-muted-foreground">{shipment.consignee_city} {shipment.consignee_state} {shipment.consignee_postal_code}</p>
                    <p className="text-muted-foreground">{shipment.consignee_country_code}</p>
                  </div>
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="text-lg">Shipment Facts</CardTitle></CardHeader>
                <CardContent className="space-y-3 text-sm">
                  <div>Shipment date: <span className="font-semibold text-slate-900">{shipment.shipment_date}</span></div>
                  <div>Reference: <span className="font-semibold text-slate-900">{shipment.reference_number || "-"}</span></div>
                  <div>Service: <span className="font-semibold text-slate-900">{shipment.service_level}</span></div>
                  <div>Payment: <span className="font-semibold text-slate-900">{shipment.payment_term.replace("_", " ")}</span></div>
                  <div>Cargo: <span className="font-semibold text-slate-900">{shipment.cargo_description || "General Cargo"}</span></div>
                  <div>Handling notes: <span className="font-semibold text-slate-900">{shipment.handling_notes || "-"}</span></div>
                  <div>Declaration notes: <span className="font-semibold text-slate-900">{shipment.declaration_notes || "-"}</span></div>
                </CardContent>
              </Card>
            </div>

            <Card className="border-slate-200 shadow-sm">
              <CardHeader><CardTitle className="text-lg">Cargo and Charges</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  {shipment.pieces.map((piece) => (
                    <div key={piece.id || `${piece.line_number}`} className="rounded-xl border border-slate-200 p-4 text-sm">
                      <p className="font-semibold text-slate-900">{piece.piece_count} x {piece.package_type}</p>
                      <p className="text-muted-foreground">{piece.description || "No description"}</p>
                      <p className="mt-2 text-muted-foreground">{piece.length_cm} x {piece.width_cm} x {piece.height_cm} cm</p>
                      <p className="text-muted-foreground">Gross {piece.gross_weight_kg} kg • Chargeable {piece.chargeable_weight_kg} kg</p>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {shipment.charges.map((charge) => (
                    <div key={charge.id || `${charge.line_number}`} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                      <span>{charge.description} • {charge.payment_by.replace("_", " ")}</span>
                      <span className="font-semibold text-slate-900">{charge.currency} {charge.amount}</span>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>

            <div className="grid gap-6 lg:grid-cols-2">
              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="text-lg">Documents</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {shipment.documents.length === 0 ? (
                    <div className="text-muted-foreground">No documents generated yet.</div>
                  ) : shipment.documents.map((document) => (
                    <div key={document.id} className="rounded-xl border border-slate-200 px-4 py-3">
                      <p className="font-semibold text-slate-900">{document.file_name}</p>
                      <p className="text-muted-foreground">{document.document_type} • {new Date(document.created_at).toLocaleString()}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="text-lg">Audit Trail</CardTitle></CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {shipment.events.map((event) => (
                    <div key={event.id} className="rounded-xl border border-slate-200 px-4 py-3">
                      <p className="font-semibold text-slate-900">{event.event_type.replace("_", " ")}</p>
                      <p className="text-muted-foreground">{event.description || "No detail provided."}</p>
                      <p className="text-xs text-slate-400">{new Date(event.created_at).toLocaleString()} {event.created_by_username ? `• ${event.created_by_username}` : ""}</p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </div>
        )}
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
