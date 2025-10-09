'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

export default function NewCustomerPage() {
  const router = useRouter();
  const [formData, setFormData] = useState({
    company_name: '',
    address_line_1: '',
    address_line_2: '',
    city: '',
    country: '',
    state_province: '',
    postcode: '',
    contact_person_name: '',
    contact_person_email: '',
    contact_person_phone: '',
    audience_type: 'LOCAL_PNG_CUSTOMER',
    address_description: '',
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setFormData({ ...formData, [e.target.id]: e.target.value });
  };

  const handleSelectChange = (value: string) => {
    setFormData({ ...formData, audience_type: value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem('authToken');
    const res = await fetch('http://127.0.0.1:8000/api/customers/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token ${token}`,
      },
      body: JSON.stringify(formData),
    });

    if (res.ok) {
      router.push('/customers');
    } else {
      // Handle error
      console.error('Failed to create customer');
    }
  };

  const isLocalPngCustomer = formData.audience_type === 'LOCAL_PNG_CUSTOMER';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Add New Customer</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label htmlFor="company_name">Company Name</Label>
            <Input id="company_name" value={formData.company_name} onChange={handleChange} required />
          </div>

          <div>
            <Label htmlFor="audience_type">Audience Type</Label>
            <Select onValueChange={handleSelectChange} defaultValue={formData.audience_type}>
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

          {isLocalPngCustomer ? (
            <div>
              <Label htmlFor="address_description">Address Description</Label>
              <Input id="address_description" value={formData.address_description} onChange={handleChange} />
            </div>
          ) : (
            <>
              <div>
                <Label htmlFor="address_line_1">Address Line 1</Label>
                <Input id="address_line_1" value={formData.address_line_1} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="address_line_2">Address Line 2</Label>
                <Input id="address_line_2" value={formData.address_line_2} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="city">City</Label>
                <Input id="city" value={formData.city} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="state_province">State / Province</Label>
                <Input id="state_province" value={formData.state_province} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="postcode">Postcode</Label>
                <Input id="postcode" value={formData.postcode} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="country">Country</Label>
                <Input id="country" value={formData.country} onChange={handleChange} />
              </div>
            </>
          )}

          <div>
            <Label htmlFor="contact_person_name">Contact Person Name</Label>
            <Input id="contact_person_name" value={formData.contact_person_name} onChange={handleChange} required />
          </div>
          <div>
            <Label htmlFor="contact_person_email">Contact Person Email</Label>
            <Input id="contact_person_email" type="email" value={formData.contact_person_email} onChange={handleChange} required />
          </div>
          <div>
            <Label htmlFor="contact_person_phone">Contact Person Phone</Label>
            <Input id="contact_person_phone" value={formData.contact_person_phone} onChange={handleChange} required />
          </div>
          <Button type="submit">Save Customer</Button>
        </form>
      </CardContent>
    </Card>
  );
}
