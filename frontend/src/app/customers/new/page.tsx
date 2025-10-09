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
    primary_address: {
      address_line_1: '',
      address_line_2: '',
      city: '',
      state_province: '',
      postcode: '',
      country: '',
    },
    contact_person_name: '',
    contact_person_email: '',
    contact_person_phone: '',
    audience_type: 'LOCAL_PNG_CUSTOMER',
    address_description: '',
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

  const handleSelectChange = (value: string) => {
    setFormData({ ...formData, audience_type: value });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const token = localStorage.getItem('authToken');

    const submissionData: any = { ...formData };
    if (submissionData.audience_type === 'LOCAL_PNG_CUSTOMER') {
      submissionData.primary_address = null;
    }

    const res = await fetch('http://127.0.0.1:8000/api/customers/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Token ${token}`,
      },
      body: JSON.stringify(submissionData),
    });

    if (res.ok) {
      router.push('/customers');
    } else {
      // Handle error
      const errorData = await res.json();
      console.error('Failed to create customer:', errorData);
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
                <Label htmlFor="primary_address.address_line_1">Address Line 1</Label>
                <Input id="primary_address.address_line_1" value={formData.primary_address.address_line_1} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="primary_address.address_line_2">Address Line 2</Label>
                <Input id="primary_address.address_line_2" value={formData.primary_address.address_line_2} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="primary_address.city">City</Label>
                <Input id="primary_address.city" value={formData.primary_address.city} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="primary_address.state_province">State / Province</Label>
                <Input id="primary_address.state_province" value={formData.primary_address.state_province} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="primary_address.postcode">Postcode</Label>
                <Input id="primary_address.postcode" value={formData.primary_address.postcode} onChange={handleChange} />
              </div>
              <div>
                <Label htmlFor="primary_address.country">Country</Label>
                <Input id="primary_address.country" value={formData.primary_address.country} onChange={handleChange} />
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