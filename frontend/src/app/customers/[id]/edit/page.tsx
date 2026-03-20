
'use client';

import { useState, useEffect, FormEvent } from "react";
import { useRouter, useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Combobox } from "@/components/ui/combobox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { usePermissions } from "@/hooks/usePermissions";
import * as api from "@/lib/api";
import DiscountFormModal from "@/components/pricing/DiscountFormModal";
import { CityOption, CountryOption, Customer } from "@/lib/types";
import WorkspaceContextCard from "@/components/WorkspaceContextCard";

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
  const [editingDiscount, setEditingDiscount] = useState<api.CustomerDiscount | null>(null);
  const [isDeletingDiscount, setIsDeletingDiscount] = useState<string | null>(null);
  const router = useRouter();
  const params = useParams();
  const { id } = params;
  const { token } = useAuth();
  const { isAdmin, isManager } = usePermissions();
  const canEditCustomerMaster = isAdmin;
  const canManageCommercialTerms = isAdmin || isManager;

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
    const confirmed = window.confirm(
      `Delete negotiated pricing for ${discount.product_code_code || discount.product_code_display || "this line item"}?`,
    );
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

    const shouldDelete = window.confirm(
      "Delete this customer? This action cannot be undone.",
    );
    if (!shouldDelete) return;

    setError(null);
    setIsDeleting(true);
    try {
      await api.deleteCustomer(token, id as string);
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
    const confirmed = window.confirm(prompt);
    if (!confirmed) return;

    setError(null);
    setIsArchiving(true);
    try {
      const updated = await api.setCustomerArchived(token, id as string, archive);
      setCustomer(updated);
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

  if (!customer) return <div>Loading...</div>;

  const isOverseas = customer.audience_type !== 'LOCAL_PNG_CUSTOMER';
  const cityOptions = cities.map((city) => ({
    value: city.id,
    label: city.display_name,
  }));
  const commercialProfile = normalizeCommercialProfile(customer.commercial_profile);

  return (
    <div className="container mx-auto p-4">
      <WorkspaceContextCard
        title="Customer Workspace"
        description="You are editing this customer from your current organization workspace."
        note="Customer master data is still shared in this beta, but all quote outputs and branding follow the quote organization."
      />

      <Card>
        <CardHeader>
          <CardTitle>Edit Customer: {customer.company_name}</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Customer Details */}
             <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <Label htmlFor="company_name">Company Name</Label>
                <Input id="company_name" name="company_name" value={customer.company_name} onChange={handleChange} required />
              </div>
              <div>
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
            {!isOverseas && (
              <div>
                <Label htmlFor="address_description">Address Description</Label>
                <Input
                  id="address_description"
                  name="address_description"
                  value={customer.address_description ?? ''}
                  onChange={handleChange}
                />
              </div>
            )}

            {/* Address Details - Conditional */}
            <h3 className="text-lg font-semibold border-t pt-4 mt-4">Primary Address</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               <div>
                  <Label htmlFor="address_line_1">Street / Road</Label>
                  <Input id="address_line_1" name="address_line_1" value={customer.primary_address?.address_line_1 ?? ''} onChange={handleAddressChange} />
                </div>
                <div>
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
                <div>
                  <Label htmlFor="state_province">State / Province</Label>
                  <Input id="state_province" name="state_province" value={customer.primary_address?.state_province ?? ''} onChange={handleAddressChange} />
                </div>
              {isOverseas && (
                <div>
                  <Label htmlFor="postcode">Postcode / ZIP</Label>
                  <Input id="postcode" name="postcode" value={customer.primary_address?.postcode ?? ''} onChange={handleAddressChange} />
                </div>
              )}
               <div>
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
            </div>


            {/* Contact Person Details */}
            <h3 className="text-lg font-semibold border-t pt-4 mt-4">Contact Person</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="contact_person_name">Name</Label>
                <Input id="contact_person_name" name="contact_person_name" value={customer.contact_person_name} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="contact_person_email">Email</Label>
                <Input id="contact_person_email" name="contact_person_email" type="email" value={customer.contact_person_email} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="contact_person_phone">Phone</Label>
                <Input id="contact_person_phone" name="contact_person_phone" value={customer.contact_person_phone} onChange={handleChange} />
              </div>
            </div>

            <h3 className="text-lg font-semibold border-t pt-4 mt-4">Commercial Setup</h3>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <Label htmlFor="preferred_quote_currency">Preferred Quote Currency</Label>
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
              <div>
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
              <div>
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
              <div>
                <Label htmlFor="payment_term_default">Default Payment Term</Label>
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
            </div>

            {error && <p className="text-red-500 p-2 bg-red-50 border border-red-200 rounded-md">{error}</p>}
            {!canEditCustomerMaster && (
              <p className="text-amber-700 p-2 bg-amber-50 border border-amber-200 rounded-md">
                Customer master data is admin-only. You can still manage negotiated pricing below.
              </p>
            )}
            <div className="flex items-center justify-between space-x-2">
                <div>
                  {isAdmin && (
                    <div className="flex gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        onClick={() => handleArchiveToggle(customer.is_active !== false)}
                        disabled={isSaving || isDeleting || isArchiving}
                      >
                        {isArchiving
                          ? (customer.is_active !== false ? "Archiving..." : "Restoring...")
                          : (customer.is_active !== false ? "Archive Customer" : "Restore Customer")}
                      </Button>
                      <Button
                        type="button"
                        variant="destructive"
                        onClick={handleDelete}
                        disabled={isSaving || isDeleting || isArchiving}
                      >
                        {isDeleting ? "Deleting..." : "Delete Customer"}
                      </Button>
                    </div>
                  )}
                </div>
                <div className="flex space-x-2">
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => router.push('/customers')}
                    disabled={isSaving || isDeleting || isArchiving}
                  >
                    Cancel
                  </Button>
                  <Button type="submit" disabled={!canEditCustomerMaster || isSaving || isDeleting || isArchiving}>
                    {isSaving ? "Saving..." : "Save Changes"}
                  </Button>
                </div>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Negotiated Pricing</CardTitle>
            <p className="text-sm text-muted-foreground mt-1">
              Manage this customer&apos;s negotiated line-item discounts in one place.
            </p>
          </div>
          {canManageCommercialTerms && customer && (
            <Button type="button" onClick={handleAddDiscount}>
              Add Negotiated Line
            </Button>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {discountError && (
            <p className="text-red-500 p-2 bg-red-50 border border-red-200 rounded-md">{discountError}</p>
          )}
          {isLoadingDiscounts ? (
            <p className="text-sm text-muted-foreground">Loading negotiated pricing...</p>
          ) : discounts.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No customer-specific negotiated line items are configured yet.
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
    </div>
  );
}
