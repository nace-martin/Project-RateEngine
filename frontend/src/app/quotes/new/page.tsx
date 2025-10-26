"use client";

import { useState, useEffect } from "react"; // <-- Add useEffect
import { zodResolver } from "@hookform/resolvers/zod";
// We must import useFieldArray
import { useForm, useFieldArray } from "react-hook-form";
import { Trash2 } from "lucide-react"; // Import a trash icon

// --- ADD TYPE IMPORT ---
// Assuming you have a Contact type defined, maybe in src/lib/types.ts
import type { Contact, CompanySearchResult } from "@/lib/types";
// --- END ADD ---

// --- Import api client (assuming you have one like in src/lib/api.ts) ---
import { apiClient } from "@/lib/api";
// --- END ADD ---


// Import our new V3 schema and enums
import {
  quoteFormSchemaV3,
  type QuoteFormSchemaV3,
  V3_MODES,
  V3_INCOTERMS,
  V3_PAYMENT_TERMS,
} from "@/lib/schemas/quoteSchema";

// Import Shadcn UI Components
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Checkbox } from "@/components/ui/checkbox";
// Import the new Tabs components
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";

// --- ADD THIS IMPORT ---
import CompanySearchCombobox from "@/components/CompanySearchCombobox";
// --- END ADD ---



export default function NewQuotePage() {
  // --- ADD THIS STATE ---
  const [selectedCustomerId, setSelectedCustomerId] = useState<number | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]); // To store fetched contacts
  const [isLoadingContacts, setIsLoadingContacts] = useState(false); // Loading indicator
  // --- END ADD ---


  const form = useForm<QuoteFormSchemaV3>({
    resolver: zodResolver(quoteFormSchemaV3),
    defaultValues: {
      customer_id: 0,
      contact_id: 0,
      mode: "AIR",
      shipment_type: "IMPORT",
      incoterm: "EXW",
      payment_term: "PREPAID",
      origin_airport_code: "",
      destination_airport_code: "",
      is_dangerous_goods: false,
      dimensions: [],
    },
  });

  // Setup useFieldArray to manage the dynamic 'dimensions' list
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "dimensions",
  });

  // This is the function for the "Add Piece" button
  // ... useFieldArray and other functions ...

  // --- ADD useEffect FOR FETCHING CONTACTS ---
  useEffect(() => {
    // Define the async function to fetch contacts
    const fetchContacts = async (customerId: number) => {
      setIsLoadingContacts(true);
      setContacts([]); // Clear previous contacts
      try {
        // Construct the URL with query parameter
        const response = await apiClient.get<Contact[]>(`/api/contacts/?customer_id=${customerId}`);
        setContacts(response.data); // Update state with fetched contacts
      } catch (error) {
        console.error("Error fetching contacts:", error);
        // TODO: Show an error message to the user (e.g., using a Toast)
      } finally {
        setIsLoadingContacts(false);
      }
    };

    // If a customer is selected, call the fetch function
    if (selectedCustomerId) {
      fetchContacts(selectedCustomerId);
    }
  }, [selectedCustomerId]); // Dependency array: run effect when selectedCustomerId changes
  // --- END ADD ---

  function addPieceLine() {
    append({
      pieces: 1,
      length_cm: 0,
      width_cm: 0,
      height_cm: 0,
      gross_weight_kg: 0,
    });
  }

  function onSubmit(data: QuoteFormSchemaV3) {
    console.log("V3 Form data is valid:");
    console.log(data);
    // TODO: Call the /api/v3/quotes/compute/ endpoint here
  }

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">New V3 Quote</h1>
            <Button type="submit" className="text-lg">
              Calculate Quote
            </Button>
          </div>

          <Tabs defaultValue="details" className="w-full">
            {/* These are the Tab "Buttons" */}
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="details">Step 1: Shipment Details</TabsTrigger>
              <TabsTrigger value="cargo">Step 2: Cargo Details</TabsTrigger>
            </TabsList>

            {/* --- TAB 1: ALL SHIPMENT DETAILS --- */}
            <TabsContent value="details" className="mt-4">
              <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                {/* --- Customer Card --- */}
                <Card>
                  <CardHeader>
                    <CardTitle>Customer</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    {/* --- REPLACED Customer ID Input --- */}
                    <FormField
                      control={form.control}
                      name="customer_id"
                      render={({ field }) => (
                        <FormItem className="flex flex-col">
                          <FormLabel>Customer</FormLabel>
                          <CompanySearchCombobox
                            value={selectedCustomer}
                            onSelect={(company) => {
                              setSelectedCustomer(company);
                              const companyId = company ? parseInt(company.id) : null;
                              field.onChange(companyId); // Update RHF state
                              setSelectedCustomerId(companyId); // Update local state
                              form.resetField("contact_id"); // Clear contact when customer changes
                            }}
                          />
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    {/* --- END REPLACEMENT --- */}

                    {/* --- Contact Select Field --- */}
                    <FormField
                      control={form.control}
                      name="contact_id"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Contact</FormLabel>
                          <Select
                            onValueChange={(value) => field.onChange(parseInt(value))}
                            value={field.value?.toString()} // Ensure value is string for Select
                            disabled={!selectedCustomerId || isLoadingContacts} // Disable if no customer OR loading
                          >
                            <FormControl>
                              <SelectTrigger>
                                <SelectValue placeholder={
                                  isLoadingContacts ? "Loading contacts..." :
                                  !selectedCustomerId ? "Select customer first" :
                                  "Select a contact"
                                } />
                              </SelectTrigger>
                            </FormControl>
                            <SelectContent>
                              {isLoadingContacts ? (
                                <SelectItem value="loading" disabled>Loading...</SelectItem>
                              ) : contacts.length > 0 ? (
                                // Map over fetched contacts
                                contacts.map((contact) => (
                                  <SelectItem key={contact.id} value={contact.id.toString()}>
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
                    {/* --- END UPDATE --- */}                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Routing</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-4">
                    <FormField
                      control={form.control}
                      name="origin_airport_code"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Origin (IATA)</FormLabel>
                          <FormControl>
                            <Input placeholder="e.g., BNE" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="destination_airport_code"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Destination (IATA)</FormLabel>
                          <FormControl>
                            <Input placeholder="e.g., POM" {...field} />
                          </FormControl>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>

                <Card className="md:col-span-2">
                  <CardHeader>
                    <CardTitle>Commercials</CardTitle>
                  </CardHeader>
                  <CardContent className="grid grid-cols-2 gap-4 md:grid-cols-4">
                    <FormField
                      control={form.control}
                      name="mode"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Mode</FormLabel>
                          <Select onValueChange={field.onChange} defaultValue={field.value?.toString()}>
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>
                              {Object.values(V3_MODES).map((mode) => (
                                <SelectItem key={mode} value={mode}>{mode}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    
                    <FormField
                      control={form.control}
                      name="incoterm"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Incoterm</FormLabel>
                          <Select onValueChange={field.onChange} defaultValue={field.value?.toString()}>
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>
                              {Object.values(V3_INCOTERMS).map((term) => (
                                <SelectItem key={term} value={term}>{term}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                    <FormField
                      control={form.control}
                      name="payment_term"
                      render={({ field }) => (
                        <FormItem>
                          <FormLabel>Payment Term</FormLabel>
                          <Select onValueChange={field.onChange} defaultValue={field.value?.toString()}>
                            <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                            <SelectContent>
                              {Object.values(V3_PAYMENT_TERMS).map((term) => (
                                <SelectItem key={term} value={term}>{term}</SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <FormMessage />
                        </FormItem>
                      )}
                    />
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* --- TAB 2: CARGO DETAILS (DIMENSIONS) --- */}
            <TabsContent value="cargo" className="mt-4">
              <Card>
                <CardHeader>
                  <CardTitle>Cargo Details</CardTitle>
                  <CardDescription>
                    Add one line for each group of identical pieces.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {/* We map over the 'fields' from useFieldArray */}
                  {fields.map((field, index) => (
                    <Card key={field.id} className="relative p-4">
                      {/* THIS IS THE NEW REMOVE BUTTON */}
                      <Button
                        type="button"
                        variant="destructive"
                        size="icon"
                        className="absolute -right-3 -top-3 h-7 w-7 rounded-full"
                        onClick={() => remove(index)} // Calls remove function
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>

                      <div className="grid grid-cols-5 gap-3">
                        <FormField
                          control={form.control}
                          name={`dimensions.${index}.pieces`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Pieces</FormLabel>
                              <FormControl>
                                <Input type="number" {...field} onChange={(e) => field.onChange(parseInt(e.target.value))}/>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name={`dimensions.${index}.length_cm`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Length (cm)</FormLabel>
                              <FormControl>
                                <Input type="number" {...field} onChange={(e) => field.onChange(parseFloat(e.target.value))}/>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name={`dimensions.${index}.width_cm`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Width (cm)</FormLabel>
                              <FormControl>
                                <Input type="number" {...field} onChange={(e) => field.onChange(parseFloat(e.target.value))}/>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name={`dimensions.${index}.height_cm`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Height (cm)</FormLabel>
                              <FormControl>
                                <Input type="number" {...field} onChange={(e) => field.onChange(parseFloat(e.target.value))}/>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                        <FormField
                          control={form.control}
                          name={`dimensions.${index}.gross_weight_kg`}
                          render={({ field }) => (
                            <FormItem>
                              <FormLabel>Weight (kg)</FormLabel>
                              <FormControl>
                                <Input type="number" {...field} onChange={(e) => field.onChange(parseFloat(e.target.value))}/>
                              </FormControl>
                              <FormMessage />
                            </FormItem>
                          )}
                        />
                      </div>
                    </Card>
                  ))}
                  
                  {/* "Add Piece" button */}
                  <Button
                    type="button"
                    variant="outline"
                    className="w-full"
                    onClick={addPieceLine}
                  >
                    Add Piece Line
                  </Button>

                  {/* Show error if array is empty */}
                  <FormMessage>
                    {form.formState.errors.dimensions?.message}
                  </FormMessage>
                </CardContent>
              </Card>

              {/* Other details like Dangerous Goods */}
              <Card className="mt-6">
                <CardHeader>
                  <CardTitle>Other Details</CardTitle>
                </CardHeader>
                <CardContent>
                  <FormField
                    control={form.control}
                    name="is_dangerous_goods"
                    render={({ field }) => (
                      <FormItem className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4">
                        <FormControl>
                          <Checkbox
                            checked={field.value}
                            onCheckedChange={field.onChange}
                          />
                        </FormControl>
                        <div className="space-y-1 leading-none">
                          <FormLabel>Dangerous Goods</FormLabel>
                        </div>
                      </FormItem>
                    )}
                  />
                </CardContent>
              </Card>

            </TabsContent>
          </Tabs>
        </form>
      </Form>
    </div>
  );
}
