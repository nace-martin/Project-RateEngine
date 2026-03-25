'use client';

import { useEffect, useState } from "react";

import CompanySearchCombobox from "@/components/CompanySearchCombobox";
import PageActionBar from "@/components/navigation/PageActionBar";
import PageBackButton from "@/components/navigation/PageBackButton";
import PageCancelButton from "@/components/navigation/PageCancelButton";
import ProtectedRoute from "@/components/protected-route";
import { PageHeader, StandardPageContainer } from "@/components/layout/standard-page";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useToast } from "@/context/toast-context";
import { useConfirm } from "@/hooks/useConfirm";
import { useReturnTo } from "@/hooks/useReturnTo";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import {
  createShipmentAddressBookEntry,
  deleteShipmentAddressBookEntry,
  listShipmentAddressBook,
  updateShipmentAddressBookEntry,
} from "@/lib/api/shipments";
import { getContactsForCompany, getCustomerDetail } from "@/lib/api/parties";
import { ShipmentAddressBookEntry } from "@/lib/shipment-types";
import { CompanySearchResult, Contact, Customer } from "@/lib/types";

type AddressBookForm = Omit<ShipmentAddressBookEntry, "id" | "created_at" | "updated_at">;
type FormErrors = Partial<Record<keyof AddressBookForm, string>>;

const emptyForm: AddressBookForm = {
  company_id: null,
  contact_id: null,
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

const getPrimaryContactLabel = (contact: Contact) => {
  const fullName = `${contact.first_name} ${contact.last_name}`.trim();
  return fullName || contact.email || contact.id;
};

export default function ShipmentAddressBookPage() {
  const { toast } = useToast();
  const confirm = useConfirm();
  const [entries, setEntries] = useState<ShipmentAddressBookEntry[]>([]);
  const [form, setForm] = useState<AddressBookForm>({ ...emptyForm });
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formErrors, setFormErrors] = useState<FormErrors>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [companyLookupError, setCompanyLookupError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [selectedCompany, setSelectedCompany] = useState<CompanySearchResult | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [selectedContactId, setSelectedContactId] = useState("");
  const [isLoadingContacts, setIsLoadingContacts] = useState(false);
  const returnTo = useReturnTo();
  const isDirty = editingId !== null || JSON.stringify(form) !== JSON.stringify(emptyForm);
  const canSaveEntry = Object.keys(validateForm(trimForm(form))).length === 0;
  useUnsavedChangesGuard(isDirty, "You have unsaved address book changes. Leave this page?");
  const confirmLeave = async () => {
    if (!isDirty) {
      return true;
    }
    return confirm({
      title: "Discard address book changes?",
      description: "You have unsaved address book changes. Leaving now will discard them.",
      confirmLabel: "Discard changes",
      cancelLabel: "Stay here",
      variant: "destructive",
    });
  };

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
    setCompanyLookupError(null);
    setSelectedCompany(null);
    setContacts([]);
    setSelectedContactId("");
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

  useEffect(() => {
    if (!selectedCompany) {
      setContacts([]);
      setIsLoadingContacts(false);
      return;
    }

    let isActive = true;
    setCompanyLookupError(null);
    setIsLoadingContacts(true);

    Promise.all([
      getCustomerDetail(selectedCompany.id),
      getContactsForCompany(selectedCompany.id),
    ])
      .then(([customer, companyContacts]) => {
        if (!isActive) {
          return;
        }

        setContacts(companyContacts);
        setForm((current) => hydrateFormFromCustomer(current, customer));
      })
      .catch((error) => {
        if (!isActive) {
          return;
        }
        setCompanyLookupError(error instanceof Error ? error.message : "Failed to load linked company details.");
      })
      .finally(() => {
        if (isActive) {
          setIsLoadingContacts(false);
        }
      });

    return () => {
      isActive = false;
    };
  }, [selectedCompany]);

  useEffect(() => {
    if (!selectedContactId) {
      setForm((current) => ({ ...current, contact_id: null }));
      return;
    }

    const contact = contacts.find((item) => item.id === selectedContactId);
    if (!contact) {
      return;
    }

    setForm((current) => ({
      ...current,
      contact_id: contact.id,
      contact_name: getPrimaryContactLabel(contact),
      email: contact.email || "",
      phone: contact.phone || "",
    }));
  }, [contacts, selectedContactId]);

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
      toast({
        title: editingId ? "Entry updated" : "Entry created",
        description: "Shipment address book details were saved successfully.",
        variant: "success",
      });
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
      company_id: entry.company_id ?? null,
      contact_id: entry.contact_id ?? null,
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
    setSelectedCompany(entry.company_id ? { id: entry.company_id, name: entry.company_name } : null);
    setSelectedContactId(entry.contact_id ?? "");
    setContacts([]);
    setFormErrors({});
    setSubmitError(null);
    setCompanyLookupError(null);
  };

  const removeEntry = async (entryId: string) => {
    const confirmed = await confirm({
      title: "Delete saved address?",
      description: "This saved shipment address book entry will be removed.",
      confirmLabel: "Delete entry",
      cancelLabel: "Keep entry",
      variant: "destructive",
    });
    if (!confirmed) {
      return;
    }
    setDeletingId(entryId);
    setSubmitError(null);
    try {
      await deleteShipmentAddressBookEntry(entryId);
      toast({
        title: "Entry deleted",
        description: "The address book entry was removed.",
        variant: "success",
      });
      await load();
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Failed to delete the address book entry.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleCompanySelect = (company: CompanySearchResult | null) => {
    setSelectedCompany(company);
    setCompanyLookupError(null);
    setSelectedContactId("");
    setContacts([]);
    setForm((current) => ({
      ...current,
      company_id: company?.id ?? null,
      contact_id: null,
      company_name: company ? current.company_name : "",
      contact_name: company ? current.contact_name : "",
      email: company ? current.email : "",
      phone: company ? current.phone : "",
    }));
  };

  return (
    <ProtectedRoute>
      <StandardPageContainer>
        <PageBackButton
          fallbackHref="/shipments"
          returnTo={returnTo}
          isDirty={isDirty}
          confirmLeave={confirmLeave}
          disabled={isSaving}
        />
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
                        <p className="font-semibold text-slate-900">{entry.label} - {entry.company_name}</p>
                        <p className="text-muted-foreground">{entry.party_role} - {entry.city}, {entry.country_code}</p>
                        {entry.contact_name ? (
                          <p className="mt-1 text-xs text-slate-500">Contact: {entry.contact_name}</p>
                        ) : null}
                        {entry.company_id ? (
                          <p className="mt-1 text-xs text-slate-500">Linked to customer master</p>
                        ) : null}
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
            <CardContent className={`space-y-3 ${isSaving ? "pointer-events-none opacity-70" : ""}`}>
              {submitError ? (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-800">
                  {submitError}
                </div>
              ) : null}

              {companyLookupError ? (
                <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
                  {companyLookupError}
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

              <CompanySearchCombobox
                label="Linked customer"
                value={selectedCompany}
                onSelect={handleCompanySelect}
                placeholder="Search customer master"
                helperText="Optional. Link this entry to a customer and choose one of its contacts."
              />

              <div className="space-y-1">
                <select
                  className="h-10 w-full rounded-lg border border-input bg-background px-3 text-sm"
                  value={selectedContactId}
                  disabled={!selectedCompany || isLoadingContacts}
                  onChange={(event) => setSelectedContactId(event.target.value)}
                >
                  <option value="">
                    {!selectedCompany
                      ? "Select linked customer first"
                      : isLoadingContacts
                        ? "Loading contacts..."
                        : "Use company default contact"}
                  </option>
                  {contacts.map((contact) => (
                    <option key={contact.id} value={contact.id}>
                      {getPrimaryContactLabel(contact)}
                    </option>
                  ))}
                </select>
              </div>

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

              <div className="grid gap-3 md:grid-cols-2">
                <Input
                  placeholder="Email"
                  value={form.email}
                  onChange={(event) => setField("email", event.target.value)}
                />
                <Input
                  placeholder="Phone"
                  value={form.phone}
                  onChange={(event) => setField("phone", event.target.value)}
                />
              </div>

              <div className="space-y-1">
                <Input
                  placeholder="Address line 1"
                  value={form.address_line_1}
                  onChange={(event) => setField("address_line_1", event.target.value)}
                />
                {formErrors.address_line_1 ? <p className="text-xs text-rose-600">{formErrors.address_line_1}</p> : null}
              </div>

              <Input
                placeholder="Address line 2"
                value={form.address_line_2}
                onChange={(event) => setField("address_line_2", event.target.value)}
              />

              <div className="grid gap-3 md:grid-cols-3">
                <div className="space-y-1">
                  <Input
                    placeholder="City"
                    value={form.city}
                    onChange={(event) => setField("city", event.target.value)}
                  />
                  {formErrors.city ? <p className="text-xs text-rose-600">{formErrors.city}</p> : null}
                </div>
                <Input
                  placeholder="State"
                  value={form.state}
                  onChange={(event) => setField("state", event.target.value)}
                />
                <Input
                  placeholder="Postcode"
                  value={form.postal_code}
                  onChange={(event) => setField("postal_code", event.target.value)}
                />
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

              <PageActionBar>
                <PageCancelButton
                  href={returnTo || "/shipments"}
                  isDirty={isDirty}
                  confirmLeave={confirmLeave}
                  confirmMessage="Discard the current address book changes?"
                  disabled={isSaving}
                />
                {editingId ? (
                  <Button type="button" variant="outline" onClick={resetForm} disabled={isSaving}>
                    Reset Form
                  </Button>
                ) : null}
                <Button disabled={isSaving || !canSaveEntry} onClick={() => void save()} loading={isSaving} loadingText={editingId ? "Updating entry..." : "Saving entry..."}>
                  {editingId ? "Update Entry" : "Save Entry"}
                </Button>
              </PageActionBar>
            </CardContent>
          </Card>
        </div>
      </StandardPageContainer>
    </ProtectedRoute>
  );
}

function hydrateFormFromCustomer(current: AddressBookForm, customer: Customer): AddressBookForm {
  const primaryAddress = customer.primary_address;
  const shouldUseDefaultContact = !current.contact_id;

  return {
    ...current,
    company_id: customer.id,
    company_name: customer.company_name,
    contact_name: shouldUseDefaultContact ? customer.contact_person_name || "" : current.contact_name,
    email: shouldUseDefaultContact ? customer.contact_person_email || "" : current.email,
    phone: shouldUseDefaultContact ? customer.contact_person_phone || "" : current.phone,
    address_line_1: primaryAddress?.address_line_1 || "",
    address_line_2: primaryAddress?.address_line_2 || "",
    city: primaryAddress?.city || "",
    state: primaryAddress?.state_province || "",
    postal_code: primaryAddress?.postcode || "",
    country_code: (primaryAddress?.country || "").toUpperCase(),
    label: current.label || customer.company_name,
  };
}
