"use client";

import { useState, useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
// We must import useFieldArray
import { useForm, useFieldArray } from "react-hook-form";
import { Trash2, Loader2 } from "lucide-react"; // Import spinner and trash icon

// --- ADD TYPE IMPORT ---
// Assuming you have a Contact type defined, maybe in src/lib/types.ts
import type { Contact, CompanySearchResult } from "@/lib/types";
// --- END ADD ---

// --- Import api client (assuming you have one like in src/lib/api.ts) ---
import { getCompanyContacts, computeQuote } from "@/lib/api"; // Import updated API helpers
// --- END ADD ---

// --- ADD IMPORTS ---
import { V3QuoteComputeRequest, V3QuoteComputeResponse } from "@/lib/types"; // Import request/response types
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"; // For showing errors/success
import Link from "next/link"; // To link to the created quote
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

import { useAuth } from "@/context/auth-context";

export default function NewQuotePage() {
  const { token } = useAuth(); // Retrieve token
  // --- ADD THIS STATE ---
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]); // To store fetched contacts
  const [isLoadingContacts, setIsLoadingContacts] = useState(false); // Loading indicator
  // --- END ADD ---
  const [isSubmitting, setIsSubmitting] = useState(false); // For main form submission
  const [apiError, setApiError] = useState<string | null>(null); // To store API errors
  const [quoteResult, setQuoteResult] = useState<V3QuoteComputeResponse | null>(null); // Successful result


  const form = useForm<QuoteFormSchemaV3>({
    resolver: zodResolver(quoteFormSchemaV3),
    defaultValues: {
      customer_id: "",
      contact_id: "",
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
    const fetchContacts = async (customerId: string) => {
      if (!token) return; // Don't fetch if no token
      setIsLoadingContacts(true);
      setContacts([]); // Clear previous contacts
      try {
        const fetchedContacts = await getCompanyContacts(customerId, token); // Use the updated function
        setContacts(fetchedContacts); // Update state with fetched contacts
      } catch (error: unknown) {
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
  }, [selectedCustomerId, token]); // Dependency array: run effect when selectedCustomerId or token changes
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

  // --- REPLACE onSubmit FUNCTION ---
  async function onSubmit(data: QuoteFormSchemaV3) {
    setIsSubmitting(true);
    setApiError(null);
    setQuoteResult(null); // Clear previous results
    console.log("Submitting V3 Form data:", data);

    if (!token) {
      setApiError("Authentication token not available. Please log in.");
      setIsSubmitting(false);
      return;
    }

    try {
      const toDecimalString = (value: number) =>
        Number.isFinite(value) ? value.toString() : "0";
      const payload: V3QuoteComputeRequest = {
        customer_id: data.customer_id,
        contact_id: data.contact_id,
        mode: data.mode.toUpperCase(),
        shipment_type: data.shipment_type.toUpperCase(),
        incoterm: data.incoterm.toUpperCase(),
        origin_airport_code: data.origin_airport_code.trim().toUpperCase(),
        destination_airport_code: data.destination_airport_code.trim().toUpperCase(),
        payment_term: data.payment_term,
        is_dangerous_goods: data.is_dangerous_goods,
        dimensions: data.dimensions.map((dimension) => ({
          pieces: dimension.pieces,
          length_cm: toDecimalString(dimension.length_cm),
          width_cm: toDecimalString(dimension.width_cm),
          height_cm: toDecimalString(dimension.height_cm),
          gross_weight_kg: toDecimalString(dimension.gross_weight_kg),
        })),
      };

      if (data.overrides?.length) {
        payload.overrides = data.overrides.map((override) => ({
          service_component_id: String(override.service_component_id),
          cost_fcy: toDecimalString(override.cost_fcy),
          currency: override.currency.trim().toUpperCase(),
          unit: override.unit,
          ...(override.min_charge_fcy !== undefined && {
            min_charge_fcy: toDecimalString(override.min_charge_fcy),
          }),
        }));
      }

      // Compute the quote using the V3 endpoint
      const response = await computeQuote(payload, token);

      console.log("API Success Response:", response);
      setQuoteResult(response); // Store the successful result
      // Optional: Reset form after successful submission
      // form.reset();
      // setSelectedCustomerId(null); // Reset customer selection
      // TODO: Maybe redirect to the new quote's page: router.push(`/quotes/${response.id}`)

    } catch (error: unknown) {
      console.error("API Error:", error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : "An unexpected error occurred.";
      setApiError(message);
      // TODO: Show error in a Toast notification for better UX
    } finally {
      setIsSubmitting(false); // Ensure loading state is turned off
    }
  }
  // --- END REPLACE ---

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">New V3 Quote</h1>
            <Button type="submit" className="text-lg" disabled={isSubmitting}>
              {isSubmitting ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Calculating...
                </>
              ) : (
                "Calculate Quote"
              )}
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
                              const companyId = company ? company.id : null;
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
                            onValueChange={field.onChange}
                            value={field.value || undefined}
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
                  {form.formState.errors.dimensions?.message && (
                    <p className="pt-2 text-sm font-medium text-destructive">
                      {form.formState.errors.dimensions.message}
                    </p>
                  )}
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

          {/* --- ADD RESULT/ERROR DISPLAY --- */}
          <div className="mt-6">
            {apiError && (
              <Alert variant="destructive">
                <AlertTitle>Error</AlertTitle>
                <AlertDescription>{apiError}</AlertDescription>
              </Alert>
            )}
            {quoteResult && (
              <Alert variant="success">
                <AlertTitle>Quote Calculated Successfully!</AlertTitle>
                <AlertDescription>
                  Quote Number:{" "}
                  <Button variant="link" asChild>
                    <Link href={`/quotes/${quoteResult.id}`}>
                      {quoteResult.quote_number}
                    </Link>
                  </Button>
                  <br />
                  Total (incl. GST): {quoteResult.latest_version.totals.total_sell_fcy_incl_gst}{" "}
                  {quoteResult.latest_version.totals.total_sell_fcy_currency}
                  {quoteResult.latest_version.totals.has_missing_rates && (
                    <span className="ml-2 font-bold text-orange-600">(Incomplete - Missing Rates)</span>
                  )}
                </AlertDescription>
              </Alert>
            )}
          </div>
          {/* --- END ADD --- */}

        </form>
      </Form>
    </div>
  );
}
