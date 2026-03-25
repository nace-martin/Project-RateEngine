"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";

import type { ShipmentPartiesStepProps } from "./shipment-wizard-types";

export default function ShipmentPartiesStep({
  form,
  updateField,
  addressBookEntries,
  applyAddressBookEntry,
}: ShipmentPartiesStepProps) {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      {(["shipper", "consignee"] as const).map((role) => (
        <Card key={role} className="border-slate-200 shadow-sm">
          <CardHeader><CardTitle className="capitalize">{role}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            <select className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm" value="" onChange={(event) => applyAddressBookEntry(event.target.value, role)}>
              <option value="">Load from address book</option>
              {addressBookEntries
                .filter((entry) => entry.party_role === "BOTH" || entry.party_role === role.toUpperCase())
                .map((entry) => (
                  <option key={entry.id} value={entry.id}>{entry.label} | {entry.company_name}</option>
                ))}
            </select>
            <div className="grid gap-3 md:grid-cols-2">
              <Input placeholder="Company name" value={form[`${role}_company_name`]} onChange={(event) => updateField(`${role}_company_name`, event.target.value)} />
              <Input placeholder="Contact name" value={form[`${role}_contact_name`]} onChange={(event) => updateField(`${role}_contact_name`, event.target.value)} />
              <Input placeholder="Email" value={form[`${role}_email`]} onChange={(event) => updateField(`${role}_email`, event.target.value)} />
              <Input placeholder="Phone" value={form[`${role}_phone`]} onChange={(event) => updateField(`${role}_phone`, event.target.value)} />
            </div>
            <Input placeholder="Address line 1" value={form[`${role}_address_line_1`]} onChange={(event) => updateField(`${role}_address_line_1`, event.target.value)} />
            <Input placeholder="Address line 2" value={form[`${role}_address_line_2`]} onChange={(event) => updateField(`${role}_address_line_2`, event.target.value)} />
            <div className="grid gap-3 md:grid-cols-4">
              <Input placeholder="City" value={form[`${role}_city`]} onChange={(event) => updateField(`${role}_city`, event.target.value)} />
              <Input placeholder="State" value={form[`${role}_state`]} onChange={(event) => updateField(`${role}_state`, event.target.value)} />
              <Input placeholder="Postcode" value={form[`${role}_postal_code`]} onChange={(event) => updateField(`${role}_postal_code`, event.target.value)} />
              <Input placeholder="Country" value={form[`${role}_country_code`]} onChange={(event) => updateField(`${role}_country_code`, event.target.value.toUpperCase())} />
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
