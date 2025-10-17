
'use client';

import { useState, useEffect, FormEvent } from "react";
import { useRouter, useParams } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useAuth } from "@/context/auth-context";
import { api } from "@/lib/api";

// Define a clear "manifest" for our data shapes
interface Address {
  address_line_1: string;
  city: string;
  state_province: string;
  postcode: string;
  country: string;
}

interface Customer {
  id: number;
  company_name: string;
  audience_type: string;
  primary_address: Address;
  contact_person_name: string;
  contact_person_email: string;
  contact_person_phone: string;
}

export default function EditCustomerPage() {
  // Use our strong types instead of 'any'
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const params = useParams();
  const { id } = params;
  const { token } = useAuth();

  useEffect(() => {
    if (id && token) {
      const fetchCustomer = async () => {
        try {
          const response = await api.get(`/customers/${id}/`, {
            headers: { Authorization: `Token ${token}` },
          });
          // Ensure primary_address is not null for the form
          if (!response.data.primary_address) {
            response.data.primary_address = {
              address_line_1: "", city: "", state_province: "", postcode: "", country: "",
            };
          }
          setCustomer(response.data);
        } catch (err) {
          setError("Failed to fetch customer data.");
        }
      };
      fetchCustomer();
    }
  }, [id, token]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCustomer((prev) => (prev ? { ...prev, [name]: value } : null));
  };

  const handleAddressChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target;
    setCustomer((prev) => (prev ? {
      ...prev,
      primary_address: { ...prev.primary_address, [name]: value },
    } : null));
  };

  const handleAudienceChange = (value: string) => {
    setCustomer((prev) => (prev ? { ...prev, audience_type: value } : null));
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!token || !customer) {
      setError("Authentication error or missing customer data.");
      return;
    }

    try {
      await api.put(`/customers/${id}/`, customer, {
        headers: { Authorization: `Token ${token}` },
      });
      router.push("/customers");
    } catch (err: any) {
      console.error(err);
      // **SMARTER ERROR HANDLING LOGIC**
      // Check if the error has a detailed response from the backend
      if (err.response && err.response.data) {
        // Format the detailed errors into a single string
        const errorMessages = Object.entries(err.response.data)
          .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
          .join('; ');
        setError(`Failed to update customer: ${errorMessages}`);
      } else {
        // Fallback to the generic message if no details are available
        setError("Failed to update customer. An unknown error occurred.");
      }
    }
  };

  if (!customer) return <div>Loading...</div>;

  const isOverseas = customer.audience_type !== 'LOCAL_PNG_CUSTOMER';

  return (
    <div className="container mx-auto p-4">
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

            {/* Address Details - Conditional */}
            <h3 className="text-lg font-semibold border-t pt-4 mt-4">Primary Address</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
               <div>
                  <Label htmlFor="address_line_1">Street / Road</Label>
                  <Input id="address_line_1" name="address_line_1" value={customer.primary_address.address_line_1} onChange={handleAddressChange} />
                </div>
                <div>
                  <Label htmlFor="city">City / Suburb</Label>
                  <Input id="city" name="city" value={customer.primary_address.city} onChange={handleAddressChange} />
                </div>
                <div>
                  <Label htmlFor="state_province">State / Province</Label>
                  <Input id="state_province" name="state_province" value={customer.primary_address.state_province} onChange={handleAddressChange} />
                </div>
              {isOverseas && (
                <div>
                  <Label htmlFor="postcode">Postcode / ZIP</Label>
                  <Input id="postcode" name="postcode" value={customer.primary_address.postcode} onChange={handleAddressChange} />
                </div>
              )}
               <div>
                  <Label htmlFor="country">Country</Label>
                  <Input id="country" name="country" value={customer.primary_address.country} onChange={handleAddressChange} />
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

            {error && <p className="text-red-500 p-2 bg-red-50 border border-red-200 rounded-md">{error}</p>}
            <div className="flex justify-end space-x-2">
                <Button type="button" variant="outline" onClick={() => router.push('/customers')}>Cancel</Button>
                <Button type="submit">Save Changes</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
