"use client";

import CompanySearch from "@/components/CompanySearchCombobox";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import type { QuoteCustomerSectionProps } from "./quote-section-types";

export default function QuoteCustomerSection({
  form,
  contacts,
  isLoadingContacts,
  selectedCustomer,
  selectedCustomerId,
  setSelectedCustomer,
  setSelectedCustomerId,
  getCompletedFieldClass,
}: QuoteCustomerSectionProps) {
  return (
    <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
      <FormField
        control={form.control}
        name="customer_id"
        render={({ field, fieldState }) => (
          <FormItem className="col-span-1 md:col-span-2">
            <FormLabel>Customer</FormLabel>
            <FormControl>
              <CompanySearch
                onSelect={(company) => {
                  field.onChange(company?.id);
                  setSelectedCustomerId(company?.id || null);
                  setSelectedCustomer(company);
                  form.setValue("contact_id", "");
                }}
                value={selectedCustomer}
                placeholder="Search for a customer..."
                inputClassName={getCompletedFieldClass(Boolean(field.value) && (fieldState.isTouched || fieldState.isDirty))}
              />
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      <FormField
        control={form.control}
        name="contact_id"
        render={({ field, fieldState }) => (
          <FormItem>
            <FormLabel>Contact Person</FormLabel>
            <Select
              onValueChange={field.onChange}
              value={field.value}
              disabled={!selectedCustomerId || isLoadingContacts}
            >
              <FormControl>
                <SelectTrigger className={getCompletedFieldClass(Boolean(field.value) && (fieldState.isTouched || fieldState.isDirty))}>
                  <SelectValue
                    placeholder={
                      isLoadingContacts
                        ? "Loading..."
                        : !selectedCustomerId
                          ? "Select customer first"
                          : "Select contact"
                    }
                  />
                </SelectTrigger>
              </FormControl>
              <SelectContent>
                {contacts.length > 0 ? (
                  contacts.map((contact) => (
                    <SelectItem key={contact.id} value={contact.id}>
                      {contact.first_name} {contact.last_name}
                    </SelectItem>
                  ))
                ) : (
                  <SelectItem value="no-contacts" disabled>
                    No contacts found
                  </SelectItem>
                )}
              </SelectContent>
            </Select>
            <FormMessage />
          </FormItem>
        )}
      />
    </div>
  );
}
