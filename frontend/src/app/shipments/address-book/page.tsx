'use client';

import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { createShipmentAddressBookEntry, deleteShipmentAddressBookEntry, listShipmentAddressBook, updateShipmentAddressBookEntry } from "@/lib/api/shipments";
import { ShipmentAddressBookEntry } from "@/lib/shipment-types";

type AddressBookForm = Omit<ShipmentAddressBookEntry, "id" | "created_at" | "updated_at">;

const emptyForm: AddressBookForm = {
  label: "",
  party_role: "BOTH",
  company_name: "",
  contact_name: "",
  email: "",
  phone: "",
  address_line_1: "",
  address_line_2: "",
  city: "",
  state: "",
  postal_code: "",
  country_code: "",
  notes: "",
  is_active: true,
};

export default function ShipmentAddressBookPage() {
  const [entries, setEntries] = useState<ShipmentAddressBookEntry[]>([]);
  const [form, setForm] = useState<AddressBookForm>({ ...emptyForm });
  const [editingId, setEditingId] = useState<string | null>(null);

  const load = async () => setEntries(await listShipmentAddressBook());
  useEffect(() => { void load(); }, []);

  const save = async () => {
    if (editingId) {
      await updateShipmentAddressBookEntry(editingId, form);
    } else {
      await createShipmentAddressBookEntry(form);
    }
    setForm({ ...emptyForm });
    setEditingId(null);
    await load();
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader title="Shipment Address Book" description="Save repeat shipper and consignee details to speed up the wizard." />
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.9fr]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle className="text-lg">Saved Parties</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {entries.map((entry) => (
                <div key={entry.id} className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 md:flex-row md:items-center md:justify-between">
                  <div className="text-sm">
                    <p className="font-semibold text-slate-900">{entry.label} · {entry.company_name}</p>
                    <p className="text-muted-foreground">{entry.party_role} · {entry.city}, {entry.country_code}</p>
                  </div>
                  <div className="space-x-2">
                    <Button variant="ghost" size="sm" onClick={() => {
                      setEditingId(entry.id);
                      setForm({
                        label: entry.label,
                        party_role: entry.party_role,
                        company_name: entry.company_name,
                        contact_name: entry.contact_name,
                        email: entry.email,
                        phone: entry.phone,
                        address_line_1: entry.address_line_1,
                        address_line_2: entry.address_line_2,
                        city: entry.city,
                        state: entry.state,
                        postal_code: entry.postal_code,
                        country_code: entry.country_code,
                        notes: entry.notes,
                        is_active: entry.is_active,
                      });
                    }}>Edit</Button>
                    <Button variant="ghost" size="sm" onClick={async () => { await deleteShipmentAddressBookEntry(entry.id); await load(); }}>Delete</Button>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader><CardTitle className="text-lg">{editingId ? "Edit Entry" : "New Entry"}</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              <Input placeholder="Label" value={form.label} onChange={(event) => setForm((current) => ({ ...current, label: event.target.value }))} />
              <select className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm" value={form.party_role} onChange={(event) => setForm((current) => ({ ...current, party_role: event.target.value as ShipmentAddressBookEntry["party_role"] }))}>
                <option value="BOTH">Both</option>
                <option value="SHIPPER">Shipper</option>
                <option value="CONSIGNEE">Consignee</option>
              </select>
              <Input placeholder="Company name" value={form.company_name} onChange={(event) => setForm((current) => ({ ...current, company_name: event.target.value }))} />
              <Input placeholder="Contact name" value={form.contact_name} onChange={(event) => setForm((current) => ({ ...current, contact_name: event.target.value }))} />
              <Input placeholder="Address line 1" value={form.address_line_1} onChange={(event) => setForm((current) => ({ ...current, address_line_1: event.target.value }))} />
              <div className="grid gap-3 md:grid-cols-2">
                <Input placeholder="City" value={form.city} onChange={(event) => setForm((current) => ({ ...current, city: event.target.value }))} />
                <Input placeholder="Country code" value={form.country_code} onChange={(event) => setForm((current) => ({ ...current, country_code: event.target.value.toUpperCase() }))} />
              </div>
              <div className="flex gap-3">
                <Button onClick={save}>{editingId ? "Update" : "Save"} Entry</Button>
                {editingId && <Button variant="outline" onClick={() => { setEditingId(null); setForm({ ...emptyForm }); }}>Cancel</Button>}
              </div>
            </CardContent>
          </Card>
        </div>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
