'use client';

import { useEffect, useState } from "react";

import ProtectedRoute from "@/components/protected-route";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createShipmentAddressBookEntry,
  deleteShipmentAddressBookEntry,
  listShipmentAddressBook,
  updateShipmentAddressBookEntry,
} from "@/lib/api/shipments";
import { ShipmentAddressBookEntry } from "@/lib/shipment-types";

type AddressBookForm = Omit<ShipmentAddressBookEntry, "id" | "created_at" | "updated_at">;
type FormErrors = Partial<Record<keyof AddressBookForm, string>>;

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

const trimForm = (form: AddressBookForm): AddressBookForm => ({
  ...form,
  label: form.label.trim(),
  company_name: form.company_name.trim(),
  contact_name: form.contact_name.trim(),
  email: form.email.trim(),
  phone: form.phone.trim(),
  address_line_1: form.address_line_1.trim(),
  address_line_2: form.address_line_2.trim(),
  city: form.city.trim(),
  state: form.state.trim(),
  postal_code: form.postal_code.trim(),
  country_code: form.country_code.trim().toUpperCase(),
  notes: form.notes.trim(),
});

const validateForm = (form: AddressBookForm): FormErrors => {
  const nextErrors: FormErrors = {};

  if (!form.label) {
    nextErrors.label = "Label is required.";
  }
  if (!form.company_name) {
    nextErrors.company_name = "Company name is required.";
  }
  if (!form.address_line_1) {
    nextErrors.address_line_1 = "Address line 1 is required.";
  }
  if (!form.city) {
    nextErrors.city = "City is required.";
  }
  if (!/^[A-Z]{2}$/.test(form.country_code)) {
    nextErrors.country_code = "Use a 2-letter country code, for example PG.";
  }

  return nextErrors;
};

export default function ShipmentAddressBookPage() {
  const [entries, setEntries] = useState<ShipmentAddressBookEntry[]>([]);
  const [form, setForm] = useState<AddressBookForm>({ ...emptyForm });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const load = async () => {
    setIsLoading(true);
    setLoadError(null);
    try {
      setEntries(await listShipmentAddressBook());
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : "Failed to load the shipment address book.");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const resetForm = () => {
    setForm({ ...emptyForm });
    setEditingId(null);
    setFormErrors({});
    setSubmitError(null);
  };

  const setField = <K extends keyof AddressBookForm>(field: K, value: AddressBookForm[K]) => {
    setForm((current) => ({ ...current, [field]: value }));
    setFormErrors((current) => {
      if (!current[field]) {
        return current;
      }
      const next = { ...current };
      delete next[field];
      return next;
    });
    setSubmitError(null);
  };

  const save = async () => {
    const payload = trimForm(form);
    const nextErrors = validateForm(payload);
    if (Object.keys(nextErrors).length > 0) {
      setFormErrors(nextErrors);
      setSubmitError("Fix the highlighted fields before saving.");
      return;
    }

    setIsSaving(true);
    setSubmitError(null);
    try {
      if (editingId) {
        await updateShipmentAddressBookEntry(editingId, payload);
      } else {
        await createShipmentAddressBookEntry(payload);
      }
      resetForm();
      await load();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to save the address book entry.");
    } finally {
      setIsSaving(false);
    }
  };

  const startEdit = (entry: ShipmentAddressBookEntry) => {
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
    setFormErrors({});
    setSubmitError(null);
  };

  const removeEntry = async (entryId: string) => {
    setDeletingId(entryId);
    setSubmitError(null);
    try {
      await deleteShipmentAddressBookEntry(entryId);
      await load();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to delete the address book entry.");
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageHeader
          title="Shipment Address Book"
          description="Save repeat shipper and consignee details to speed up the wizard."
        />
        <div className="grid gap-6 lg:grid-cols-[1.2fr_0.9fr]">
          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="text-lg">Saved Parties</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {loadError ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
                  <p className="font-medium">Could not load the address book.</p>
                  <p className="mt-1">{loadError}</p>
                  <Button className="mt-3" variant="outline" size="sm" onClick={() => void load()}>
                    Retry
                  </Button>
                </div>
              ) : null}

              {!loadError && isLoading ? (
                <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500">
                  Loading saved parties...
                </div>
              ) : null}

              {!loadError && !isLoading && entries.length === 0 ? (
                <div className="rounded-xl border border-dashed border-slate-200 p-4 text-sm text-slate-500">
                  No saved parties yet.
                </div>
              ) : null}

              {!loadError
                ? entries.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 md:flex-row md:items-center md:justify-between"
                    >
                      <div className="text-sm">
                        <p className="font-semibold text-slate-900">{entry.label} · {entry.company_name}</p>
                        <p className="text-muted-foreground">{entry.party_role} · {entry.city}, {entry.country_code}</p>
                      </div>
                      <div className="space-x-2">
                        <Button variant="ghost" size="sm" onClick={() => startEdit(entry)}>
                          Edit
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={deletingId === entry.id}
                          onClick={() => void removeEntry(entry.id)}
                        >
                          {deletingId === entry.id ? "Deleting..." : "Delete"}
                        </Button>
                      </div>
                    </div>
                  ))
                : null}
            </CardContent>
          </Card>

          <Card className="border-slate-200 shadow-sm">
            <CardHeader>
              <CardTitle className="text-lg">{editingId ? "Edit Entry" : "New Entry"}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {submitError ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                  {submitError}
                </div>
              ) : null}

              <div className="space-y-1">
                <Input
                  placeholder="Label"
                  value={form.label}
                  onChange={(event) => setField("label", event.target.value)}
                />
                {formErrors.label ? <p className="text-xs text-rose-600">{formErrors.label}</p> : null}
              </div>

              <select
                className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
                value={form.party_role}
                onChange={(event) => setField("party_role", event.target.value as ShipmentAddressBookEntry["party_role"])}
              >
                <option value="BOTH">Both</option>
                <option value="SHIPPER">Shipper</option>
                <option value="CONSIGNEE">Consignee</option>
              </select>

              <div className="space-y-1">
                <Input
                  placeholder="Company name"
                  value={form.company_name}
                  onChange={(event) => setField("company_name", event.target.value)}
                />
                {formErrors.company_name ? <p className="text-xs text-rose-600">{formErrors.company_name}</p> : null}
              </div>

              <Input
                placeholder="Contact name"
                value={form.contact_name}
                onChange={(event) => setField("contact_name", event.target.value)}
              />

              <div className="space-y-1">
                <Input
                  placeholder="Address line 1"
                  value={form.address_line_1}
                  onChange={(event) => setField("address_line_1", event.target.value)}
                />
                {formErrors.address_line_1 ? <p className="text-xs text-rose-600">{formErrors.address_line_1}</p> : null}
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div className="space-y-1">
                  <Input
                    placeholder="City"
                    value={form.city}
                    onChange={(event) => setField("city", event.target.value)}
                  />
                  {formErrors.city ? <p className="text-xs text-rose-600">{formErrors.city}</p> : null}
                </div>
                <div className="space-y-1">
                  <Input
                    placeholder="Country code"
                    value={form.country_code}
                    maxLength={2}
                    onChange={(event) => setField("country_code", event.target.value.replace(/[^a-z]/gi, "").toUpperCase())}
                  />
                  {formErrors.country_code ? <p className="text-xs text-rose-600">{formErrors.country_code}</p> : null}
                </div>
              </div>

              <div className="flex gap-3">
                <Button disabled={isSaving} onClick={() => void save()}>
                  {isSaving ? "Saving..." : editingId ? "Update Entry" : "Save Entry"}
                </Button>
                {editingId ? (
                  <Button variant="outline" onClick={resetForm}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </CardContent>
          </Card>
        </div>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}
