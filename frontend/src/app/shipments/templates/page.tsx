'use client';

import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createShipmentTemplate, deleteShipmentTemplate, listShipmentTemplates, updateShipmentTemplate } from "@/lib/api/shipments";
import { ShipmentTemplate } from "@/lib/shipment-types";

type ShipmentTemplateForm = Omit<ShipmentTemplate, "id" | "created_at" | "updated_at">;

const emptyTemplate: ShipmentTemplateForm = {
  name: "",
  description: "",
  is_active: true,
  shipper_defaults: {},
  consignee_defaults: {},
  shipment_defaults: {},
  pieces_defaults: [],
  charges_defaults: [],
};

export default function ShipmentTemplatesPage() {
  const [templates, setTemplates] = useState<ShipmentTemplate[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState<ShipmentTemplateForm>({ ...emptyTemplate });

  const load = async () => setTemplates(await listShipmentTemplates());
  useEffect(() => { void load(); }, []);

  const save = async () => {
    if (editingId) {
      await updateShipmentTemplate(editingId, form);
    } else {
      await createShipmentTemplate(form);
    }
    setEditingId(null);
    setForm({ ...emptyTemplate });
    await load();
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader title="Shipment Templates" description="Store repeat shipment profiles so teams can start from prefilled routing, parties, and charge defaults." />
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.9fr]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle className="text-lg">Saved Templates</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {templates.map((template) => (
                <div key={template.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 md:flex-row md:items-center md:justify-between">
                  <div className="text-sm">
                    <p className="font-semibold text-slate-900">{template.name}</p>
                    <p className="text-muted-foreground">{template.description || "No description"}</p>
                  </div>
                  <div className="space-x-2">
                    <Button variant="ghost" size="sm" onClick={() => {
                      setEditingId(template.id);
                      setForm({
                        name: template.name,
                        description: template.description,
                        is_active: template.is_active,
                        shipper_defaults: template.shipper_defaults,
                        consignee_defaults: template.consignee_defaults,
                        shipment_defaults: template.shipment_defaults,
                        pieces_defaults: template.pieces_defaults,
                        charges_defaults: template.charges_defaults,
                      });
                    }}>Edit</Button>
                    <Button variant="ghost" size="sm" onClick={async () => { await deleteShipmentTemplate(template.id); await load(); }}>Delete</Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle className="text-lg">{editingId ? "Edit Template" : "New Template"}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Input placeholder="Template name" value={form.name} onChange={(event) => setForm((current) => ({ ...current, name: event.target.value }))} />
              <Input placeholder="Description" value={form.description} onChange={(event) => setForm((current) => ({ ...current, description: event.target.value }))} />
              <Input placeholder="Default shipper company" value={(form.shipper_defaults as Record<string, string>).shipper_company_name || ""} onChange={(event) => setForm((current) => ({ ...current, shipper_defaults: { ...current.shipper_defaults, shipper_company_name: event.target.value } }))} />
              <Input placeholder="Default consignee company" value={(form.consignee_defaults as Record<string, string>).consignee_company_name || ""} onChange={(event) => setForm((current) => ({ ...current, consignee_defaults: { ...current.consignee_defaults, consignee_company_name: event.target.value } }))} />
              <div className="grid gap-3 md:grid-cols-2">
              <Input placeholder="Default service level" value={(form.shipment_defaults as Record<string, string>).service_level || ""} onChange={(event) => setForm((current) => ({ ...current, shipment_defaults: { ...current.shipment_defaults, service_level: event.target.value as ShipmentTemplateForm["shipment_defaults"]["service_level"] } }))} />
              <Input placeholder="Default payment term" value={(form.shipment_defaults as Record<string, string>).payment_term || ""} onChange={(event) => setForm((current) => ({ ...current, shipment_defaults: { ...current.shipment_defaults, payment_term: event.target.value as ShipmentTemplateForm["shipment_defaults"]["payment_term"] } }))} />
              </div>
              <div className="flex gap-3">
                <Button onClick={save}>{editingId ? "Update" : "Save"} Template</Button>
                {editingId && <Button variant="outline" onClick={() => { setEditingId(null); setForm({ ...emptyTemplate }); }}>Cancel</Button>}
              </div>
            </CardContent>
          </Card>
        </div>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
