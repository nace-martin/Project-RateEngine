
'use client';

import { useState, useEffect, FormEvent } from "react";
import { useRouter, useParams } from "next/navigation";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Combobox } from "@/components/ui/combobox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { useToast } from "@/context/toast-context";
import { useConfirm } from "@/hooks/useConfirm";
import { usePermissions } from "@/hooks/usePermissions";
import * as api from "@/lib/api";
import BulkDiscountFormModal from "@/components/pricing/BulkDiscountFormModal";
import BulkDiscountCsvImportModal from "@/components/pricing/BulkDiscountCsvImportModal";
import { downloadDiscountCsvTemplate } from "@/components/pricing/discount-csv-template";
import DiscountFormModal from "@/components/pricing/DiscountFormModal";
import { StandardPageContainer } from "@/components/layout/standard-page";
import { CityOption, CountryOption, Customer } from "@/lib/types";
import WorkspaceContextCard from "@/components/WorkspaceContextCard";
import PageActionBar from "@/components/navigation/PageActionBar";
import PageBackButton from "@/components/navigation/PageBackButton";
import PageCancelButton from "@/components/navigation/PageCancelButton";
import { useUnsavedChangesGuard } from "@/hooks/useUnsavedChangesGuard";
import { useReturnTo } from "@/hooks/useReturnTo";
import { getEditCustomerCopy } from "@/lib/page-copy";

type ErrorWithResponse = {
  response?: {
    data?: Record<string, unknown>;
  };
  message?: string;
};

const isErrorWithResponse = (error: unknown): error is ErrorWithResponse => {
  if (typeof error !== "object" || error === null) {
    return false;
  }

  return "response" in error;
};

const normalizeCommercialProfile = (profile?: Customer["commercial_profile"] | null) => ({
  preferred_quote_currency: profile?.preferred_quote_currency || "",
  default_margin_percent: profile?.default_margin_percent || "",
  min_margin_percent: profile?.min_margin_percent || "",
  payment_term_default: profile?.payment_term_default || "",
});

export default function EditCustomerPage() {
  // Use our strong types instead of 'any'
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isArchiving, setIsArchiving] = useState(false);
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [cities, setCities] = useState<CityOption[]>([]);
  const [isLoadingCities, setIsLoadingCities] = useState(false);
  const [discounts, setDiscounts] = useState<api.CustomerDiscount[]>([]);
  const [isLoadingDiscounts, setIsLoadingDiscounts] = useState(false);
  const [discountError, setDiscountError] = useState<string | null>(null);
  const [isDiscountModalOpen, setIsDiscountModalOpen] = useState(false);
  const [isBulkDiscountModalOpen, setIsBulkDiscountModalOpen] = useState(false);
  const [isCsvImportModalOpen, setIsCsvImportModalOpen] = useState(false);
  const [editingDiscount, setEditingDiscount] = useState<api.CustomerDiscount | null>(null);
  const [isDeletingDiscount, setIsDeletingDiscount] = useState<string | null>(null);
  const [initialCustomerSnapshot, setInitialCustomerSnapshot] = useState<string>("");
  const router = useRouter();
  const params = useParams();
  const { id } = params;
  const { token } = useAuth();
  const { toast } = useToast();
  const confirm = useConfirm();
  const { isAdmin } = usePermissions();
  const canEditCustomerMaster = isAdmin;
  const canManageCommercialTerms = isAdmin;

  useEffect(() => {
    if (id && token) {
      const fetchCustomer = async () => {
        try {
          const customerData = await api.getCustomer(token, id as string);
          // Ensure primary_address is not null for the form
          if (!customerData.primary_address) {
            customerData.primary_address = {
              address_line_1: "", city_id: "", city: "", state_province: "", postcode: "", country: "", country_name: "",
            };
          }
          setCustomer(customerData);
        } catch (fetchError) {
          console.error(fetchError);
          setError("Failed to fetch customer data.");
        }
      };
      fetchCustomer();
    }
  }, [id, token]);

  useEffect(() => {
    if (customer && !initialCustomerSnapshot) {
      setInitialCustomerSnapshot(JSON.stringify(customer));
    }
  }, [customer, initialCustomerSnapshot]);

  useEffect(() => {
    if (!token) return;
    const loadCountries = async () => {
      try {
        const data = await api.listCountries();
        setCountries(data);
      } catch (err) {
        console.error(err);
      }
    };
    loadCountries();
  }, [token]);

  const selectedCountryCode = customer?.primary_address?.country?.toUpperCase() || '';

  useEffect(() => {
    if (!token || !selectedCountryCode) {
      setCities([]);
      return;
    }
    let cancelled = false;
    const loadCities = async () => {
      try {
        setIsLoadingCities(true);
        const data = await api.listCities({
          country_code: selectedCountryCode,
        });
        if (!cancelled) {
          setCities(data);
        }
      } catch (err) {
        console.error(err);
      } finally {
        if (!cancelled) {
          setIsLoadingCities(false);
        }
      }
    };
    loadCities();
    return () => {
      cancelled = true;
    };
  }, [token, selectedCountryCode]);

  useEffect(() => {
    if (!token || !id) return;
    let cancelled = false;

    const loadDiscounts = async () => {
      try {
        setIsLoadingDiscounts(true);
        setDiscountError(null);
        const data = await api.getCustomerDiscounts({ customer: id as string });
        if (!cancelled) {
          setDiscounts(data);
        }
      } catch (err) {
        console.error(err);
        if (!cancelled) {
          setDiscountError("Failed to load negotiated pricing.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingDiscounts(false);
        }
      }
    };

    loadDiscounts();
    return () => {
      cancelled = true;
    };
  }, [token, id]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCustomer((prev) => (prev ? { ...prev, [name]: value } : null));
  };

  const handleAddressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCustomer((prev) => {
      if (!prev) return null;

      const currentAddress = prev.primary_address || {
        address_line_1: "",
        city_id: "",
        city: "",
        state_province: "",
        postcode: "",
        country: "",
        country_name: "",
      };

      return {
        ...prev,
        primary_address: {
          ...currentAddress,
          [name]: value,
        },
      };
    });
  };

  const handleAudienceChange = (value: string) => {
    setCustomer((prev) => (prev ? { ...prev, audience_type: value } : null));
  };

  const handleCountryChange = (countryCode: string) => {
    setCustomer((prev) => {
      if (!prev) return null;
      const currentAddress = prev.primary_address || {
        address_line_1: "",
        city_id: "",
        city: "",
        state_province: "",
        postcode: "",
        country: "",
        country_name: "",
      };
      const selectedCountry = countries.find((country) => country.code === countryCode);
      return {
        ...prev,
        primary_address: {
          ...currentAddress,
          country: countryCode,
          country_name: selectedCountry?.name || "",
          city_id: "",
          city: "",
        },
      };
    });
  };

  const handleCityChange = (cityId: string) => {
    const selectedCity = cities.find((city) => city.id === cityId);
    setCustomer((prev) => {
      if (!prev || !selectedCity) return prev;
      const currentAddress = prev.primary_address || {
        address_line_1: "",
        city_id: "",
        city: "",
        state_province: "",
        postcode: "",
        country: "",
        country_name: "",
      };
      return {
        ...prev,
        primary_address: {
          ...currentAddress,
          city_id: selectedCity.id,
          city: selectedCity.name,
          country: selectedCity.country_code,
          country_name: selectedCity.country_name,
        },
      };
    });
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token || !customer) {
      setError("Authentication error or missing customer data.");
      return;
    }
    if (!canEditCustomerMaster) {
      setError("Only admins can edit customer master data.");
      return;
    }

    setIsSaving(true);
    try {
      await api.updateCustomer(token, id as string, customer);
      toast({ title: "Customer updated", description: "Customer changes were saved successfully.", variant: "success" });
      router.push("/customers");
    } catch (err: unknown) {
      console.error(err);

      if (isErrorWithResponse(err) && err.response?.data) {
        const errorData = err.response.data as Record<string, unknown>;
        const errorMessages = Object.entries(errorData)
          .map(([key, value]) => {
            if (Array.isArray(value)) {
              return `${key}: ${value.join(", ")}`;
            }
            return `${key}: ${String(value)}`;
          })
          .join("; ");
        setError(`Failed to update customer: ${errorMessages}`);
      } else if (err instanceof Error) {
        setError(err.message || "Failed to update customer. An unknown error occurred.");
      } else {
        setError("Failed to update customer. An unknown error occurred.");
      }
    } finally {
      setIsSaving(false);
    }
  };

  const refreshDiscounts = async () => {
    if (!id) return;
    setIsLoadingDiscounts(true);
    setDiscountError(null);
    try {
      const data = await api.getCustomerDiscounts({ customer: id as string });
      setDiscounts(data);
    } catch (err) {
      console.error(err);
      setDiscountError("Failed to load negotiated pricing.");
    } finally {
      setIsLoadingDiscounts(false);
    }
  };

  const handleAddDiscount = () => {
    setEditingDiscount(null);
    setIsDiscountModalOpen(true);
  };

  const handleEditDiscount = (discount: api.CustomerDiscount) => {
    setEditingDiscount(discount);
    setIsDiscountModalOpen(true);
  };

  const handleDeleteDiscount = async (discount: api.CustomerDiscount) => {
    const confirmed = await confirm({
      title: "Delete negotiated pricing?",
      description: `Delete negotiated pricing for ${discount.product_code_code || discount.product_code_display || "this line item"}?`,
      confirmLabel: "Delete line",
      cancelLabel: "Keep line",
      variant: "destructive",
    });
    if (!confirmed) return;

    setIsDeletingDiscount(discount.id);
    setDiscountError(null);
    try {
      await api.deleteCustomerDiscount(discount.id);
      await refreshDiscounts();
    } catch (err) {
      console.error(err);
      setDiscountError(err instanceof Error ? err.message : "Failed to delete negotiated pricing.");
    } finally {
      setIsDeletingDiscount(null);
    }
  };

  const formatDiscountValue = (discount: api.CustomerDiscount) => {
    switch (discount.discount_type) {
      case "PERCENTAGE":
      case "MARGIN_OVERRIDE":
        return `${discount.discount_value}%`;
      case "RATE_REDUCTION":
        return `${discount.currency} ${discount.discount_value}/kg`;
      default:
        return `${discount.currency} ${discount.discount_value}`;
    }
  };

  const handleDelete = async () => {
    if (!token || !id) {
      setError("Authentication error or missing customer ID.");
      return;
    }

    const shouldDelete = await confirm({
      title: "Delete customer?",
      description: "This action cannot be undone.",
      confirmLabel: "Delete customer",
      cancelLabel: "Keep customer",
      variant: "destructive",
    });
    if (!shouldDelete) return;

    setError(null);
    setIsDeleting(true);
    try {
      await api.deleteCustomer(token, id as string);
      toast({ title: "Customer deleted", description: "The customer record was deleted.", variant: "success" });
      router.push("/customers");
    } catch (err: unknown) {
      console.error(err);
      if (err instanceof Error) {
        setError(err.message || "Failed to delete customer.");
      } else {
        setError("Failed to delete customer.");
      }
    } finally {
      setIsDeleting(false);
    }
  };

  const handleArchiveToggle = async (archive: boolean) => {
    if (!token || !id) {
      setError("Authentication error or missing customer ID.");
      return;
    }

    const prompt = archive
      ? "Archive this customer? Historical quotes remain unchanged."
      : "Restore this archived customer?";
    const confirmed = await confirm({
      title: archive ? "Archive customer?" : "Restore customer?",
      description: prompt,
      confirmLabel: archive ? "Archive customer" : "Restore customer",
      cancelLabel: "Cancel",
      variant: archive ? "destructive" : "default",
    });
    if (!confirmed) return;

    setError(null);
    setIsArchiving(true);
    try {
      const updated = await api.setCustomerArchived(token, id as string, archive);
      setCustomer(updated);
      toast({
        title: archive ? "Customer archived" : "Customer restored",
        description: archive ? "The customer was archived successfully." : "The customer was restored successfully.",
        variant: "success",
      });
    } catch (err: unknown) {
      console.error(err);
      if (err instanceof Error) {
        setError(err.message || "Failed to update customer status.");
      } else {
        setError("Failed to update customer status.");
      }
    } finally {
      setIsArchiving(false);
    }
  };

  const isDirty = customer !== null && initialCustomerSnapshot !== "" && JSON.stringify(customer) !== initialCustomerSnapshot;
  useUnsavedChangesGuard(isDirty);
  const returnTo = useReturnTo();
  const confirmLeave = async () => {
    if (!isDirty) {
      return true;
    }
    return confirm({
      title: "Discard customer changes?",
      description: "You have unsaved customer changes. Leaving now will discard them.",
      confirmLabel: "Discard changes",
      cancelLabel: "Stay here",
      variant: "destructive",
    });
  };

  if (!customer) return <div>Loading...</div>;

  const isOverseas = customer.audience_type !== 'LOCAL_PNG_CUSTOMER';
  const cityOptions = cities.map((city) => ({
    value: city.id,
    label: city.display_name,
  }));
  const commercialProfile = normalizeCommercialProfile(customer.commercial_profile);
  const pageCopy = getEditCustomerCopy();
  const canSaveCustomer = Boolean(customer.company_name.trim());

  return (
    <StandardPageContainer>
      <PageBackButton
        fallbackHref="/customers"
        returnTo={returnTo}
        isDirty={isDirty}
        confirmLeave={confirmLeave}
        disabled={isSaving || isDeleting || isArchiving}
      />
      <WorkspaceContextCard
        title={pageCopy.title}
        description={pageCopy.description}
        note={pageCopy.note}
      />

      <form onSubmit={handleSubmit} className="space-y-6">
        <div className={isSaving || isDeleting || isArchiving ? "space-y-6 pointer-events-none opacity-70" : "space-y-6"}>
        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Customer Profile</CardTitle>
            <CardDescription>
              Maintain the customer’s company information, address, and primary contact details.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6 px-6 pb-6 pt-2">
            <div className="grid grid-cols-12 gap-4">
              <div className="col-span-12 md:col-span-6">
                <Label htmlFor="company_name">Company Name</Label>
                <Input id="company_name" name="company_name" value={customer.company_name} onChange={handleChange} required />
              </div>
              <div className="col-span-12 md:col-span-6">
                <Label htmlFor="audience_type">Audience Type</Label>
                <Select value={customer.audience_type} onValueChange={handleAudienceChange}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select an audience type" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="LOCAL_PNG_CUSTOMER">Local PNG Customer</SelectItem>
                    <SelectItem value="OVERSEAS_PARTNER_AU">Overseas Partner (AU)</SelectItem>
                    <SelectItem value="OVERSEAS_PARTNER_NON_AU">Overseas Partner (Non-AU)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-4 border-t pt-5">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Address</h3>
                <p className="text-sm text-muted-foreground">
                  Keep local PNG customers simple, and capture full overseas address details when needed.
                </p>
              </div>
              {!isOverseas ? (
                <div>
                  <Label htmlFor="address_description">Address</Label>
                  <Input
                    id="address_description"
                    name="address_description"
                    value={customer.address_description ?? ''}
                    onChange={handleChange}
                  />
                </div>
              ) : (
                <div className="grid grid-cols-12 gap-4">
                  <div className="col-span-12 md:col-span-6">
                    <Label htmlFor="address_line_1">Street / Road</Label>
                    <Input id="address_line_1" name="address_line_1" value={customer.primary_address?.address_line_1 ?? ''} onChange={handleAddressChange} />
                  </div>
                  <div className="col-span-12 md:col-span-6">
                    <Label htmlFor="country">Country</Label>
                    <Select
                      value={customer.primary_address?.country ?? ''}
                      onValueChange={handleCountryChange}
                    >
                      <SelectTrigger id="country">
                        <SelectValue placeholder="Select country" />
                      </SelectTrigger>
                      <SelectContent>
                        {countries.map((country) => (
                          <SelectItem key={country.code} value={country.code}>
                            {country.code} - {country.name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="col-span-12 md:col-span-6">
                    <Label htmlFor="city">City / Suburb</Label>
                    <Combobox
                      value={customer.primary_address?.city_id ?? ''}
                      onChange={handleCityChange}
                      options={cityOptions}
                      placeholder="Search city..."
                      emptyMessage={selectedCountryCode ? "No city found." : "Select country first."}
                      disabled={!selectedCountryCode || isLoadingCities}
                    />
                  </div>
                  <div className="col-span-12 md:col-span-6">
                    <Label htmlFor="state_province">State / Province</Label>
                    <Input id="state_province" name="state_province" value={customer.primary_address?.state_province ?? ''} onChange={handleAddressChange} />
                  </div>
                  <div className="col-span-12 md:col-span-6">
                    <Label htmlFor="postcode">Postcode / ZIP</Label>
                    <Input id="postcode" name="postcode" value={customer.primary_address?.postcode ?? ''} onChange={handleAddressChange} />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4 border-t pt-5">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Contact Person</h3>
                <p className="text-sm text-muted-foreground">
                  Set the primary contact used when quotes and updates are sent to this customer.
                </p>
              </div>
              <div className="grid grid-cols-12 gap-4">
                <div className="col-span-12 md:col-span-4">
                  <Label htmlFor="contact_person_name">Contact Person</Label>
                  <Input id="contact_person_name" name="contact_person_name" value={customer.contact_person_name} onChange={handleChange} />
                </div>
                <div className="col-span-12 md:col-span-4">
                  <Label htmlFor="contact_person_email">Email</Label>
                  <Input id="contact_person_email" name="contact_person_email" type="email" value={customer.contact_person_email} onChange={handleChange} />
                </div>
                <div className="col-span-12 md:col-span-4">
                  <Label htmlFor="contact_person_phone">Phone</Label>
                  <Input id="contact_person_phone" name="contact_person_phone" value={customer.contact_person_phone} onChange={handleChange} />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card className="border-slate-200 shadow-sm">
          <CardHeader>
            <CardTitle>Commercial Terms</CardTitle>
            <CardDescription>
              Define the default currency, margin, and payment-term settings that should guide quoting for this customer.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid grid-cols-12 gap-4 px-6 pb-6 pt-2">
            <div className="col-span-12 md:col-span-6 xl:col-span-3">
              <Label htmlFor="preferred_quote_currency">Preferred Currency</Label>
              <Select
                value={commercialProfile.preferred_quote_currency || ''}
                onValueChange={(value) =>
                  setCustomer((prev) =>
                    prev
                      ? {
                          ...prev,
                          commercial_profile: {
                            ...normalizeCommercialProfile(prev.commercial_profile),
                            preferred_quote_currency: value,
                          },
                        }
                      : null,
                  )
                }
              >
                <SelectTrigger id="preferred_quote_currency">
                  <SelectValue placeholder="Select currency" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PGK">PGK</SelectItem>
                  <SelectItem value="AUD">AUD</SelectItem>
                  <SelectItem value="USD">USD</SelectItem>
                  <SelectItem value="SGD">SGD</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="col-span-12 md:col-span-6 xl:col-span-3">
              <Label htmlFor="default_margin_percent">Default Margin %</Label>
              <Input
                id="default_margin_percent"
                value={commercialProfile.default_margin_percent || ''}
                onChange={(e) =>
                  setCustomer((prev) =>
                    prev
                      ? {
                          ...prev,
                          commercial_profile: {
                            ...normalizeCommercialProfile(prev.commercial_profile),
                            default_margin_percent: e.target.value,
                          },
                        }
                      : null,
                  )
                }
              />
            </div>
            <div className="col-span-12 md:col-span-6 xl:col-span-3">
              <Label htmlFor="min_margin_percent">Minimum Margin %</Label>
              <Input
                id="min_margin_percent"
                value={commercialProfile.min_margin_percent || ''}
                onChange={(e) =>
                  setCustomer((prev) =>
                    prev
                      ? {
                          ...prev,
                          commercial_profile: {
                            ...normalizeCommercialProfile(prev.commercial_profile),
                            min_margin_percent: e.target.value,
                          },
                        }
                      : null,
                  )
                }
              />
            </div>
            <div className="col-span-12 md:col-span-6 xl:col-span-3">
              <Label htmlFor="payment_term_default">Payment Terms</Label>
              <Select
                value={commercialProfile.payment_term_default || ''}
                onValueChange={(value) =>
                  setCustomer((prev) =>
                    prev
                      ? {
                          ...prev,
                          commercial_profile: {
                            ...normalizeCommercialProfile(prev.commercial_profile),
                            payment_term_default: value,
                          },
                        }
                      : null,
                  )
                }
              >
                <SelectTrigger id="payment_term_default">
                  <SelectValue placeholder="Select payment term" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="PREPAID">Prepaid</SelectItem>
                  <SelectItem value="COLLECT">Collect</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        </div>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        {!canEditCustomerMaster && (
          <p className="text-amber-700 p-2 bg-amber-50 border border-amber-200 rounded-md">
            Customer profile and commercial terms are admin-only. You can still review the pricing overrides below.
          </p>
        )}

        <PageActionBar>
          {isAdmin && (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => handleArchiveToggle(customer.is_active !== false)}
                disabled={isSaving || isDeleting || isArchiving}
                loading={isArchiving}
                loadingText={customer.is_active !== false ? "Archiving..." : "Restoring..."}
                className="min-w-[148px]"
              >
                {customer.is_active !== false ? "Archive Customer" : "Restore Customer"}
              </Button>
              <Button
                type="button"
                variant="destructive"
                onClick={handleDelete}
                disabled={isSaving || isDeleting || isArchiving}
                loading={isDeleting}
                loadingText="Deleting..."
                className="min-w-[148px]"
              >
                Delete Customer
              </Button>
            </>
          )}
          <PageCancelButton
            href={returnTo || "/customers"}
            isDirty={isDirty}
            confirmLeave={confirmLeave}
            confirmMessage="Discard the current customer changes?"
            disabled={isSaving || isDeleting || isArchiving}
            className="min-w-[140px]"
          />
          <Button
            type="submit"
            disabled={!canEditCustomerMaster || !canSaveCustomer || isSaving || isDeleting || isArchiving}
            loading={isSaving}
            loadingText="Saving changes..."
            className="min-w-[148px]"
          >
            Save Changes
          </Button>
        </PageActionBar>
      </form>

      <Card className="border-slate-200 bg-slate-50/60 shadow-sm">
        <CardHeader className="flex flex-col gap-4 border-b border-slate-200 bg-slate-50/80 md:flex-row md:items-start md:justify-between">
          <div>
            <CardTitle>Pricing Overrides</CardTitle>
            <CardDescription className="mt-1">
              Manage line-item discounts and negotiated pricing overrides for this customer account.
            </CardDescription>
          </div>
          {canManageCommercialTerms && customer && (
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={downloadDiscountCsvTemplate}>
                Download Template
              </Button>
              <Button type="button" variant="outline" onClick={() => setIsCsvImportModalOpen(true)}>
                Import CSV
              </Button>
              <Button type="button" variant="outline" onClick={() => setIsBulkDiscountModalOpen(true)}>
                Bulk Add Lines
              </Button>
              <Button type="button" onClick={handleAddDiscount}>
                Add Negotiated Line
              </Button>
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-3 px-6 py-6">
          {discountError && (
            <p className="text-red-500 p-2 bg-red-50 border border-red-200 rounded-md">{discountError}</p>
          )}
          {isLoadingDiscounts ? (
            <p className="text-sm text-muted-foreground">Loading pricing overrides...</p>
          ) : discounts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No pricing overrides are configured for this customer yet.
            </p>
          ) : (
            discounts.map((discount) => (
              <div
                key={discount.id}
                className="rounded-lg border border-slate-200 p-4 flex flex-col gap-3 md:flex-row md:items-start md:justify-between"
              >
                <div className="space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-mono text-sm">{discount.product_code_code}</span>
                    <Badge variant="outline">{discount.discount_type_display || discount.discount_type}</Badge>
                    {discount.is_active === false && <Badge variant="secondary">Inactive</Badge>}
                  </div>
                  <p className="text-sm font-medium">{discount.product_code_description}</p>
                  <p className="text-sm text-muted-foreground">
                    {formatDiscountValue(discount)}
                    {discount.valid_until ? ` · valid until ${new Date(discount.valid_until).toLocaleDateString()}` : ""}
                  </p>
                  {discount.notes && (
                    <p className="text-sm text-muted-foreground">{discount.notes}</p>
                  )}
                </div>
                {canManageCommercialTerms && (
                  <div className="flex gap-2">
                    <Button type="button" variant="outline" onClick={() => handleEditDiscount(discount)}>
                      Edit
                    </Button>
                    <Button
                      type="button"
                      variant="destructive"
                      onClick={() => handleDeleteDiscount(discount)}
                      disabled={isDeletingDiscount === discount.id}
                    >
                      {isDeletingDiscount === discount.id ? "Deleting..." : "Delete"}
                    </Button>
                  </div>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      {customer && (
        <DiscountFormModal
          open={isDiscountModalOpen}
          onOpenChange={setIsDiscountModalOpen}
          discount={editingDiscount}
          onSuccess={async () => {
            setIsDiscountModalOpen(false);
            setEditingDiscount(null);
            await refreshDiscounts();
          }}
          lockedCustomer={{ id: customer.id, name: customer.company_name }}
        />
      )}
      {customer && (
        <BulkDiscountFormModal
          open={isBulkDiscountModalOpen}
          onOpenChange={setIsBulkDiscountModalOpen}
          customer={{ id: customer.id, name: customer.company_name }}
          onSuccess={async () => {
            await refreshDiscounts();
          }}
        />
      )}
      {customer && (
        <BulkDiscountCsvImportModal
          open={isCsvImportModalOpen}
          onOpenChange={setIsCsvImportModalOpen}
          customer={{ id: customer.id, name: customer.company_name }}
          onSuccess={async () => {
            await refreshDiscounts();
          }}
        />
      )}
    </StandardPageContainer>
  );
}
