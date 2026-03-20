'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Combobox } from "@/components/ui/combobox";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { apiClient, listCities, listCountries, updateCustomer } from "@/lib/api";
import { useAuth } from "@/context/auth-context";
import { CityOption, CountryOption } from "@/lib/types";
import WorkspaceContextCard from "@/components/WorkspaceContextCard";

type CustomerFormData = {
  company_name: string;
  primary_address: {
    address_line_1: string;
    address_line_2: string;
    city_id: string;
    city: string;
    state_province: string;
    postcode: string;
    country: string;
    country_name: string;
  };
  contact_person_name: string;
  contact_person_email: string;
  contact_person_phone: string;
  audience_type: string;
  address_description: string;
  commercial_profile: {
    preferred_quote_currency: string;
    default_margin_percent: string;
    min_margin_percent: string;
    payment_term_default: string;
  };
};

type CustomerSubmissionData = Omit<CustomerFormData, 'primary_address'> & {
  primary_address: CustomerFormData['primary_address'] | null;
};

export default function NewCustomerPage() {
  const router = useRouter();
  const { token } = useAuth();
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [cities, setCities] = useState<CityOption[]>([]);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [formData, setFormData] = useState({
    company_name: '',
    primary_address: {
      address_line_1: '',
      address_line_2: '',
      city_id: '',
      city: '',
      state_province: '',
      postcode: '',
      country: '',
      country_name: '',
    },
    contact_person_name: '',
    contact_person_email: '',
    contact_person_phone: '',
    audience_type: 'LOCAL_PNG_CUSTOMER',
    address_description: '',
    commercial_profile: {
      preferred_quote_currency: '',
      default_margin_percent: '',
      min_margin_percent: '',
      payment_term_default: '',
    },
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { id, value } = e.target;
    if (id.startsWith('primary_address.')) {
      const field = id.split('.')[1];
      setFormData(prev => ({ 
        ...prev, 
        primary_address: { ...prev.primary_address, [field]: value } 
      }));
    } else {
      setFormData({ ...formData, [id]: value });
    }
  };

  useEffect(() => {
    if (!token) return;
    const loadCountries = async () => {
      try {
        const data = await listCountries();
        setCountries(data);
      } catch (err) {
        console.error(err);
      }
    };
    loadCountries();
  }, [token]);

  useEffect(() => {
    if (!token || !formData.primary_address.country) {
      setCities([]);
      return;
    }

    let cancelled = false;
    const loadCities = async () => {
      try {
        const data = await listCities({
          country_code: formData.primary_address.country,
        });
        if (!cancelled) {
          setCities(data);
        }
      } catch (err) {
        console.error(err);
      }
    };
    loadCities();
    return () => {
      cancelled = true;
    };
  }, [token, formData.primary_address.country]);

  const handleSelectChange = (value: string) => {
    setFormData({ ...formData, audience_type: value });
  };

  const handleCountryChange = (countryCode: string) => {
    const selectedCountry = countries.find((country) => country.code === countryCode);
    setFormData((prev) => ({
      ...prev,
      primary_address: {
        ...prev.primary_address,
        country: countryCode,
        country_name: selectedCountry?.name || '',
        city_id: '',
        city: '',
      },
    }));
  };

  const handleCityChange = (cityId: string) => {
    const selectedCity = cities.find((city) => city.id === cityId);
    if (!selectedCity) return;
    setFormData((prev) => ({
      ...prev,
      primary_address: {
        ...prev.primary_address,
        city_id: selectedCity.id,
        city: selectedCity.name,
        country: selectedCity.country_code,
        country_name: selectedCity.country_name,
      },
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) {
      setError('Authentication token not available.');
      return;
    }
    setError(null);
    setIsSaving(true);

    const submissionData: CustomerSubmissionData = {
      ...formData,
      primary_address:
        formData.audience_type === 'LOCAL_PNG_CUSTOMER' ? null : formData.primary_address,
    };

    try {
      // Step 1: create base customer row
      const createPayload = {
        company_name: submissionData.company_name,
        audience_type: submissionData.audience_type,
        address_description: submissionData.address_description,
      };
      const createRes = await apiClient.post('/api/v3/customers/', createPayload);
      const customerId = createRes?.data?.id as string | undefined;
      if (!customerId) {
        throw new Error('Customer created but no ID returned.');
      }

      // Step 2: persist contact + address through customer-details endpoint
      await updateCustomer(token, customerId, submissionData);
      router.push('/customers');
    } catch (submitError) {
      console.error('Failed to create customer:', submitError);
      if (submitError instanceof Error) {
        setError(submitError.message || 'Failed to create customer.');
      } else {
        setError('Failed to create customer.');
      }
    } finally {
      setIsSaving(false);
    }
  };

  const isLocalPngCustomer = formData.audience_type === 'LOCAL_PNG_CUSTOMER';
  const cityOptions = cities.map((city) => ({
    value: city.id,
    label: city.display_name,
  }));

  return (
    <div className="space-y-6">
      <WorkspaceContextCard
        title="Customer Workspace"
        description="You are managing customer records from your current organization workspace."
        note="Customer master data is still shared in this beta, but quotes and outbound branding resolve from the signed-in organization."
      />

      <form onSubmit={handleSubmit} className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle>Customer Profile</CardTitle>
            <CardDescription>
              Capture the customer’s core identity, address details, and primary contact.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="company_name">Company Name</Label>
                <Input id="company_name" value={formData.company_name} onChange={handleChange} required />
              </div>

              <div>
                <Label htmlFor="audience_type">Audience Type</Label>
                <Select onValueChange={handleSelectChange} value={formData.audience_type}>
                  <SelectTrigger id="audience_type">
                    <SelectValue placeholder="Select audience type" />
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
                  Use a simple local description for PNG customers, or full address details for overseas partners.
                </p>
              </div>

              {isLocalPngCustomer ? (
                <div>
                  <Label htmlFor="address_description">Address Description</Label>
                  <Input id="address_description" value={formData.address_description} onChange={handleChange} />
                </div>
              ) : (
                <div className="grid gap-4 md:grid-cols-2">
                  <div>
                    <Label htmlFor="primary_address.address_line_1">Address Line 1</Label>
                    <Input id="primary_address.address_line_1" value={formData.primary_address.address_line_1} onChange={handleChange} />
                  </div>
                  <div>
                    <Label htmlFor="primary_address.address_line_2">Address Line 2</Label>
                    <Input id="primary_address.address_line_2" value={formData.primary_address.address_line_2} onChange={handleChange} />
                  </div>
                  <div>
                    <Label htmlFor="primary_address.country">Country</Label>
                    <Select value={formData.primary_address.country} onValueChange={handleCountryChange}>
                      <SelectTrigger id="primary_address.country">
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
                  <div>
                    <Label htmlFor="primary_address.city">City</Label>
                    <Combobox
                      value={formData.primary_address.city_id}
                      onChange={handleCityChange}
                      options={cityOptions}
                      placeholder="Search city..."
                      emptyMessage={formData.primary_address.country ? "No city found." : "Select country first."}
                      disabled={!formData.primary_address.country}
                    />
                  </div>
                  <div>
                    <Label htmlFor="primary_address.state_province">State / Province</Label>
                    <Input id="primary_address.state_province" value={formData.primary_address.state_province} onChange={handleChange} />
                  </div>
                  <div>
                    <Label htmlFor="primary_address.postcode">Postcode</Label>
                    <Input id="primary_address.postcode" value={formData.primary_address.postcode} onChange={handleChange} />
                  </div>
                </div>
              )}
            </div>

            <div className="space-y-4 border-t pt-5">
              <div>
                <h3 className="text-base font-semibold text-slate-900">Contact Person</h3>
                <p className="text-sm text-muted-foreground">
                  Set the primary contact details used for quote correspondence.
                </p>
              </div>
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <Label htmlFor="contact_person_name">Contact Person</Label>
                  <Input id="contact_person_name" value={formData.contact_person_name} onChange={handleChange} required />
                </div>
                <div>
                  <Label htmlFor="contact_person_email">Email</Label>
                  <Input id="contact_person_email" type="email" value={formData.contact_person_email} onChange={handleChange} required />
                </div>
                <div>
                  <Label htmlFor="contact_person_phone">Phone</Label>
                  <Input id="contact_person_phone" value={formData.contact_person_phone} onChange={handleChange} required />
                </div>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Commercial Terms</CardTitle>
            <CardDescription>
              Define the default commercial settings the quote engine should use for this customer.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div>
              <Label htmlFor="preferred_quote_currency">Preferred Currency</Label>
              <Select
                value={formData.commercial_profile.preferred_quote_currency || ''}
                onValueChange={(value) =>
                  setFormData((prev) => ({
                    ...prev,
                    commercial_profile: {
                      ...prev.commercial_profile,
                      preferred_quote_currency: value,
                    },
                  }))
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
                value={formData.commercial_profile.default_margin_percent}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    commercial_profile: {
                      ...prev.commercial_profile,
                      default_margin_percent: e.target.value,
                    },
                  }))
                }
              />
            </div>
            <div>
              <Label htmlFor="min_margin_percent">Minimum Margin %</Label>
              <Input
                id="min_margin_percent"
                value={formData.commercial_profile.min_margin_percent}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    commercial_profile: {
                      ...prev.commercial_profile,
                      min_margin_percent: e.target.value,
                    },
                  }))
                }
              />
            </div>
            <div>
              <Label htmlFor="payment_term_default">Payment Terms</Label>
              <Select
                value={formData.commercial_profile.payment_term_default || ''}
                onValueChange={(value) =>
                  setFormData((prev) => ({
                    ...prev,
                    commercial_profile: {
                      ...prev.commercial_profile,
                      payment_term_default: value,
                    },
                  }))
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

        {error && <p className="text-sm text-red-600">{error}</p>}

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.push('/customers')} disabled={isSaving}>
            Cancel
          </Button>
          <Button type="submit" disabled={isSaving}>{isSaving ? 'Saving...' : 'Save Customer'}</Button>
        </div>
      </form>
    </div>
  );
}
