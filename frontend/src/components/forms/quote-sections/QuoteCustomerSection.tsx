"use client";

import { useFormContext, useWatch } from "react-hook-form";

import CompanySearch from "@/components/CompanySearchCombobox";
import {
  getCompletedFieldClass,
  type QuoteFormData,
} from "@/components/forms/quote-sections/quote-section-types";
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
import { useQuoteStore } from "@/store/useQuoteStore";

export default function QuoteCustomerSection() {
  const form = useFormContext<QuoteFormData>();
  const customerId = useWatch({ control: form.control, name: "customer_id" });
  const contacts = useQuoteStore((state) => state.contacts);
  const isLoadingContacts = useQuoteStore((state) => state.isLoadingContacts);
  const selectedCustomer = useQuoteStore((state) => state.selectedCustomer);
  const setSelectedCustomer = useQuoteStore((state) => state.setSelectedCustomer);

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
              disabled={!customerId || isLoadingContacts}
            >
              <FormControl>
                <SelectTrigger className={getCompletedFieldClass(Boolean(field.value) && (fieldState.isTouched || fieldState.isDirty))}>
                  <SelectValue
                    placeholder={
                      isLoadingContacts
                        ? "Loading..."
                        : !customerId
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
