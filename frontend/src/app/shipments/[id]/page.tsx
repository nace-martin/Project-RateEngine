'use client';

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { ShipmentStatusBadge } from "@/components/shipments/ShipmentStatusBadge";
import { usePermissions } from "@/hooks/usePermissions";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cancelShipment, duplicateShipment, getShipment, openShipmentPdf, reissueShipment } from "@/lib/api/shipments";
import { formatRouteCodes, formatRouteName } from "@/lib/display";
import { formatShipmentChoice, ShipmentRecord } from "@/lib/shipment-types";

export default function ShipmentDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const { isAdmin, isManager, canFinalizeQuotes } = usePermissions();
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
    void run();
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

  const canControlFinalizedShipment = isAdmin || isManager;
  const canPrintConnote = canFinalizeQuotes;

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title={shipment?.connote_number || "Shipment Detail"}
          description="Review shipment details, documents, and activity before printing or updating this connote."
          actions={
            shipment ? (
              <>
                {shipment.status === "DRAFT" ? (
                  <Link href={`/shipments/new?shipmentId=${shipment.id}`}>
                    <Button variant="outline">Edit Draft</Button>
                  </Link>
                ) : null}
                {shipment.status === "FINALIZED" && canPrintConnote ? (
                  <Button variant="outline" onClick={() => openShipmentPdf(shipment.id)}>Open PDF</Button>
                ) : null}
                {shipment.status === "DRAFT" ? (
                  <Button variant="outline" onClick={handleDuplicate}>Duplicate Draft</Button>
                ) : null}
                {shipment.status === "FINALIZED" && canControlFinalizedShipment ? (
                  <Button variant="outline" onClick={handleReissue}>Reissue</Button>
                ) : null}
                {shipment.status !== "CANCELLED" && shipment.status !== "REISSUED" && canControlFinalizedShipment ? (
                  <Button variant="outline" onClick={handleCancel}>Cancel</Button>
                ) : null}
              </>
            ) : null
          }
        />

        {loading ? (
          <Card>
            <CardContent className="p-6 text-sm text-muted-foreground">Loading shipment detail...</CardContent>
          </Card>
        ) : error || !shipment ? (
          <Card>
            <CardContent className="p-6 text-sm text-red-600">{error || "Shipment not found."}</CardContent>
          </Card>
        ) : (
          <div className="space-y-6">
            <div className="grid gap-4 md:grid-cols-5">
              {[
                { label: "Status", value: <ShipmentStatusBadge status={shipment.status} /> },
                { label: "Type", value: formatShipmentType(shipment.shipment_type) },
                { label: "Branch", value: shipment.branch || "-" },
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
                <CardContent className="grid gap-4 text-sm md:grid-cols-2">
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
                  <div>
                    Route:{" "}
                    <span className="font-semibold text-slate-900">
                      {formatRouteName(
                        { display_name: shipment.origin_location_display || shipment.origin_code },
                        { display_name: shipment.destination_location_display || shipment.destination_code },
                        shipment.origin_code,
                        shipment.destination_code,
                      ) || formatRouteCodes(shipment.origin_code, shipment.destination_code)}
                    </span>
                  </div>
                  <div>Reference: <span className="font-semibold text-slate-900">{shipment.reference_number || "-"}</span></div>
                  <div>Booking ref: <span className="font-semibold text-slate-900">{shipment.booking_reference || "-"}</span></div>
                  <div>Flight ref: <span className="font-semibold text-slate-900">{shipment.flight_reference || "-"}</span></div>
                  <div>Cargo Type: <span className="font-semibold text-slate-900">{formatShipmentChoice(shipment.cargo_type)}</span></div>
                  <div>Service Type: <span className="font-semibold text-slate-900">{formatShipmentChoice(shipment.service_product)}</span></div>
                  <div>Service Scope: <span className="font-semibold text-slate-900">{formatShipmentChoice(shipment.service_scope)}</span></div>
                  <div>Payment Term: <span className="font-semibold text-slate-900">{formatShipmentChoice(shipment.payment_term)}</span></div>
                  <div>Cargo: <span className="font-semibold text-slate-900">{shipment.cargo_description || "General Cargo"}</span></div>
                </CardContent>
              </Card>
            </div>

            {shipment.shipment_type === "EXPORT" ? (
              <Card className="border-slate-200 shadow-sm">
                <CardHeader><CardTitle className="text-lg">Export Support</CardTitle></CardHeader>
                <CardContent className="grid gap-3 text-sm md:grid-cols-2">
                  <div>Export ref: <span className="font-semibold text-slate-900">{shipment.export_reference || "-"}</span></div>
                  <div>Invoice ref: <span className="font-semibold text-slate-900">{shipment.invoice_reference || "-"}</span></div>
                  <div>Permit ref: <span className="font-semibold text-slate-900">{shipment.permit_reference || "-"}</span></div>
                  <div>Customs notes: <span className="font-semibold text-slate-900">{shipment.customs_notes || "-"}</span></div>
                </CardContent>
              </Card>
            ) : null}

            <Card className="border-slate-200 shadow-sm">
              <CardHeader><CardTitle className="text-lg">Cargo, Charges, and Notes</CardTitle></CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-3 md:grid-cols-2">
                  {shipment.pieces.map((piece) => (
                    <div key={piece.id || `${piece.line_number}`} className="rounded-xl border border-slate-200 p-4 text-sm">
                      <p className="font-semibold text-slate-900">Piece {piece.line_number}: {piece.piece_count} x {piece.package_type}</p>
                      {piece.description ? <p className="mt-2 text-muted-foreground">{piece.description}</p> : null}
                      <p className="text-muted-foreground">{piece.length_cm} x {piece.width_cm} x {piece.height_cm} cm</p>
                      <p className="text-muted-foreground">
                        Gross {piece.gross_weight_kg} kg • Volumetric {piece.volumetric_weight_kg} kg • Chargeable {piece.chargeable_weight_kg} kg
                      </p>
                    </div>
                  ))}
                </div>
                <div className="space-y-2">
                  {shipment.charges.length === 0 ? (
                    <div className="rounded-xl border border-dashed border-slate-200 px-4 py-3 text-sm text-muted-foreground">
                      No charge lines recorded.
                    </div>
                  ) : shipment.charges.map((charge) => (
                    <div key={charge.id || `${charge.line_number}`} className="flex items-center justify-between rounded-xl border border-slate-200 px-4 py-3 text-sm">
                      <span>{charge.description} | {formatShipmentChoice(charge.payment_by)}</span>
                      <span className="font-semibold text-slate-900">{charge.currency} {charge.amount}</span>
                    </div>
                  ))}
                </div>
                <div className="rounded-xl border border-slate-200 p-4 text-sm">
                  <p>Handling notes: <span className="font-semibold text-slate-900">{shipment.handling_notes || "-"}</span></p>
                  <p>Declaration notes: <span className="font-semibold text-slate-900">{shipment.declaration_notes || "-"}</span></p>
                  <p>DG notes: <span className="font-semibold text-slate-900">{shipment.dangerous_goods_details || "-"}</span></p>
                  <p>Perishable notes: <span className="font-semibold text-slate-900">{shipment.perishable_details || "-"}</span></p>
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
                      <p className="font-semibold text-slate-900">{formatShipmentChoice(event.event_type)}</p>
                      <p className="text-muted-foreground">{event.description || "No detail provided."}</p>
                      <p className="text-xs text-slate-400">
                        {new Date(event.created_at).toLocaleString()}
                        {event.created_by_username ? ` • ${event.created_by_username}` : ""}
                      </p>
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

function formatShipmentType(value: ShipmentRecord["shipment_type"]) {
  if (value === "IMPORT") return "Import (Legacy)";
  return value === "DOMESTIC" ? "Domestic" : "Export";
}
