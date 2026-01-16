"use client";

import {
    FormField,
    FormItem,
    FormLabel,
    FormMessage,
    FormControl,
} from "@/components/ui/form";
import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
} from "@/components/ui/card";
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from "@/components/ui/select";
import CompanySearchCombobox from "@/components/CompanySearchCombobox";
import { UseFormReturn } from "react-hook-form";
import { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import { CompanySearchResult, Contact } from "@/lib/types";

interface CustomerSectionProps {
    form: UseFormReturn<QuoteFormSchemaV3>;
    contacts: Contact[];
    isLoadingContacts: boolean;
    selectedCustomerId: string | null;
    selectedCustomer: CompanySearchResult | null;
    onCustomerSelect: (company: CompanySearchResult | null) => void;
}

export function CustomerSection({
    form,
    contacts,
    isLoadingContacts,
    selectedCustomerId,
    selectedCustomer,
    onCustomerSelect,
}: CustomerSectionProps) {
    return (
        <Card>
            <CardHeader>
                <CardTitle>Customer</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
                <FormField
                    control={form.control}
                    name="customer_id"
                    render={({ field }) => (
                        <FormItem className="flex flex-col">
                            <FormLabel>Customer</FormLabel>
                            <CompanySearchCombobox
                                value={selectedCustomer}
                                onSelect={(company) => {
                                    onCustomerSelect(company);
                                }}
                            />
                            <FormMessage />
                        </FormItem>
                    )}
                />
                <FormField
                    control={form.control}
                    name="contact_id"
                    render={({ field }) => (
                        <FormItem>
                            <FormLabel>Contact</FormLabel>
                            <Select
                                onValueChange={field.onChange}
                                value={field.value || ""}
                                disabled={!selectedCustomerId || isLoadingContacts}
                            >
                                <FormControl>
                                    <SelectTrigger>
                                        <SelectValue
                                            placeholder={
                                                isLoadingContacts
                                                    ? "Loading contacts..."
                                                    : !selectedCustomerId
                                                        ? "Select customer first"
                                                        : "Select a contact"
                                            }
                                        />
                                    </SelectTrigger>
                                </FormControl>
                                <SelectContent>
                                    {isLoadingContacts ? (
                                        <SelectItem value="loading" disabled>Loading...</SelectItem>
                                    ) : contacts.length > 0 ? (
                                        contacts.map((contact) => (
                                            <SelectItem key={contact.id} value={contact.id}>
                                                {contact.first_name} {contact.last_name} ({contact.email})
                                            </SelectItem>
                                        ))
                                    ) : (
                                        <SelectItem value="no-contacts" disabled>
                                            {selectedCustomerId ? "No contacts found" : "Select customer first"}
                                        </SelectItem>
                                    )}
                                </SelectContent>
                            </Select>
                            <FormMessage />
                        </FormItem>
                    )}
                />
            </CardContent>
        </Card>
    );
}
