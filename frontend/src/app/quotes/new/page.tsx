"use client";

import { useState, useEffect } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm, useFieldArray } from "react-hook-form";
import { Trash2, Loader2 } from "lucide-react";
import type {
  Contact,
  CompanySearchResult,
  LocationSearchResult,
} from "@/lib/types";
import { getContactsForCompany, computeQuoteV3 } from "@/lib/api";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import {
  quoteFormSchemaV3,
  type QuoteFormSchemaV3,
  V3_MODES,
  V3_INCOTERMS,
  V3_PAYMENT_TERMS,
  V3_SERVICE_SCOPES,
  V3_LOCATION_TYPES,
} from "@/lib/schemas/quoteSchema";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormDescription,
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
import LocationSearchCombobox from "@/components/LocationSearchCombobox";
import CompanySearchCombobox from "@/components/CompanySearchCombobox";
import { useAuth } from "@/context/auth-context";
import { useRouter } from "next/navigation";

const SUPPORTED_LOCATION_TYPES = new Set<QuoteFormSchemaV3["origin_location_type"]>(
  Object.values(V3_LOCATION_TYPES),
);

export default function NewQuotePage() {
  const { user } = useAuth();
  const router = useRouter();
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);
  const [selectedCustomer, setSelectedCustomer] = useState<CompanySearchResult | null>(null);
  const [contacts, setContacts] = useState<Contact[]>([]);
  const [isLoadingContacts, setIsLoadingContacts] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [apiError, setApiError] = useState<string | null>(null);
  const [originLocation, setOriginLocation] = useState<LocationSearchResult | null>(null);
  const [destinationLocation, setDestinationLocation] = useState<LocationSearchResult | null>(null);

  const form = useForm<QuoteFormSchemaV3>({
    resolver: zodResolver(quoteFormSchemaV3),
    mode: "onChange",
    reValidateMode: "onChange",
    defaultValues: {
      customer_id: "",
      contact_id: "",
      mode: "AIR",
      incoterm: "EXW",
      payment_term: "PREPAID",
      service_scope: V3_SERVICE_SCOPES.A2A,
      origin_airport: "",
      destination_airport: "",
      origin_location_type: V3_LOCATION_TYPES.AIRPORT,
      origin_location_id: "",
      destination_location_type: V3_LOCATION_TYPES.AIRPORT,
      destination_location_id: "",
      is_dangerous_goods: false,
      dimensions: [],
    },
  });
  const { isValid, isDirty } = form.formState;
  const canCalculateQuote = isDirty && isValid;

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "dimensions",
  });

  const originLocationId = form.watch("origin_location_id");
  const destinationLocationId = form.watch("destination_location_id");

  useEffect(() => {
    if (!originLocationId) {
      setOriginLocation(null);
    }
  }, [originLocationId]);

  useEffect(() => {
    if (!destinationLocationId) {
      setDestinationLocation(null);
    }
  }, [destinationLocationId]);

  const normalizeLocationType = (
    rawType?: string | null,
  ): QuoteFormSchemaV3["origin_location_type"] => {
    if (!rawType) {
      return V3_LOCATION_TYPES.AIRPORT;
    }
    const upper = rawType.toUpperCase() as QuoteFormSchemaV3["origin_location_type"];
    if (SUPPORTED_LOCATION_TYPES.has(upper)) {
      return upper;
    }
    return V3_LOCATION_TYPES.AIRPORT;
  };

  const setLocationFields = (
    kind: "origin" | "destination",
    location: LocationSearchResult | null,
    onLocationIdChange: (value: string) => void,
  ) => {
    const normalizedType = location
      ? normalizeLocationType(location.type)
      : V3_LOCATION_TYPES.AIRPORT;
    const locationId = location?.id ?? "";
    const airportCode =
      normalizedType === V3_LOCATION_TYPES.AIRPORT
        ? (location?.code ?? "").toUpperCase()
        : "";

    onLocationIdChange(locationId);

    if (kind === "origin") {
      form.setValue("origin_location_type", normalizedType, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue("origin_airport", airportCode, {
        shouldDirty: true,
        shouldValidate: true,
      });
    } else {
      form.setValue("destination_location_type", normalizedType, {
        shouldDirty: true,
        shouldValidate: true,
      });
      form.setValue("destination_airport", airportCode, {
        shouldDirty: true,
        shouldValidate: true,
      });
    }
  };

  useEffect(() => {
    const fetchContacts = async (customerId: string) => {
      if (!user || !customerId) return;
      setIsLoadingContacts(true);
      setContacts([]);
      try {
        const fetchedContacts = await getContactsForCompany(customerId);
        setContacts(fetchedContacts);
      } catch (error: unknown) {
        console.error("Error fetching contacts:", error);
        setApiError("Failed to fetch contacts.");
      } finally {
        setIsLoadingContacts(false);
      }
    };

    if (selectedCustomerId) {
      fetchContacts(selectedCustomerId);
    }
  }, [selectedCustomerId, user]);

  function addPieceLine() {
    append({
      pieces: 1,
      length_cm: "0",
      width_cm: "0",
      height_cm: "0",
      gross_weight_kg: "0",
    });
  }

  async function onSubmit(data: QuoteFormSchemaV3) {
    setIsSubmitting(true);
    setApiError(null);

    if (!user) {
      setApiError("Authentication token not available. Please log in.");
      setIsSubmitting(false);
      return;
    }

    try {
      const response = await computeQuoteV3(data);
      router.push(`/quotes/${response.id}`);
    } catch (error: unknown) {
      console.error("API Error:", error);
      const message =
        error instanceof Error && error.message
          ? error.message
          : "An unexpected error occurred.";
      setApiError(message);
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="container mx-auto max-w-5xl p-4">
      <Form {...form}>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
          <div className="flex items-center justify-between">
            <h1 className="text-3xl font-bold">New Quote</h1>
          </div>

          {apiError && (
            <Alert variant="destructive">
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{apiError}</AlertDescription>
            </Alert>
          )}

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
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
                          setSelectedCustomer(company);
                          const companyId = company?.id ?? null;
                          field.onChange(companyId ?? "");
                          setSelectedCustomerId(companyId);
                          setContacts([]);
                          form.resetField("contact_id");
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
                            <SelectItem value="loading" disabled>
                              Loading...
                            </SelectItem>
                          ) : contacts.length > 0 ? (
                            contacts.map((contact) => (
                              <SelectItem key={contact.id} value={contact.id}>
                                {contact.first_name} {contact.last_name} ({contact.email})
                              </SelectItem>
                            ))
                          ) : (
                            <SelectItem value="no-contacts" disabled>
                              {selectedCustomerId
                                ? "No contacts found"
                                : "Select customer first"}
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

            <Card>
              <CardHeader>
                <CardTitle>Routing</CardTitle>
                <CardDescription>
                  Shipment type (import/export/domestic) is detected automatically.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <FormField
                  control={form.control}
                  name="origin_location_id"
                  render={({ field }) => (
                    <FormItem className="flex flex-col">
                      <FormLabel>Origin Location</FormLabel>
                      <LocationSearchCombobox
                        value={field.value || null}
                        selectedLabel={originLocation?.display_name ?? null}
                        onSelect={(selection) => {
                          setOriginLocation(selection);
                          setLocationFields("origin", selection, field.onChange);
                        }}
                      />
                      <FormDescription>Select any supported location (airport, port, city, or address).</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="destination_location_id"
                  render={({ field }) => (
                    <FormItem className="flex flex-col">
                      <FormLabel>Destination Location</FormLabel>
                      <LocationSearchCombobox
                        value={field.value || null}
                        selectedLabel={destinationLocation?.display_name ?? null}
                        onSelect={(selection) => {
                          setDestinationLocation(selection);
                          setLocationFields("destination", selection, field.onChange);
                        }}
                      />
                      <FormDescription>Select any supported location (airport, port, city, or address).</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>

            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle>Shipment & Terms</CardTitle>
              </CardHeader>
              <CardContent className="grid grid-cols-1 gap-4 md:grid-cols-4">
                <FormField
                  control={form.control}
                  name="mode"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Mode</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select mode" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.values(V3_MODES).map((mode) => (
                            <SelectItem key={mode} value={mode}>
                              {mode}
                            </SelectItem>
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
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select incoterm" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.values(V3_INCOTERMS).map((incoterm) => (
                            <SelectItem key={incoterm} value={incoterm}>
                              {incoterm}
                            </SelectItem>
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
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select payment term" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.values(V3_PAYMENT_TERMS).map((term) => (
                            <SelectItem key={term} value={term}>
                              {term}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="service_scope"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Service Scope</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="Select scope" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {Object.values(V3_SERVICE_SCOPES).map((scope) => (
                            <SelectItem key={scope} value={scope}>
                              {scope}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription>Door/Airport selection for pricing logic.</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </CardContent>
            </Card>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Cargo Dimensions</CardTitle>
              <CardDescription>
                Provide at least one piece line with dimensions and weight.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {fields.length === 0 ? (
                <div className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">
                  No cargo lines yet. Add your first piece line below.
                </div>
              ) : null}
              {fields.map((fieldItem, index) => (
                <Card key={fieldItem.id}>
                  <CardHeader className="flex flex-row items-center justify-between space-y-0">
                    <CardTitle className="text-base font-semibold">
                      Piece {index + 1}
                    </CardTitle>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => remove(index)}
                      aria-label={`Remove piece ${index + 1}`}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </CardHeader>
                  <CardContent>
                    <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
                      <FormField
                        control={form.control}
                        name={`dimensions.${index}.pieces`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Pieces</FormLabel>
                            <FormControl>
                              <Input type="number" min={1} {...field} />
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
                              <Input type="number" step="0.01" min="0" {...field} />
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
                              <Input type="number" step="0.01" min="0" {...field} />
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
                              <Input type="number" step="0.01" min="0" {...field} />
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
                              <Input type="number" step="0.01" min="0" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  </CardContent>
                </Card>
              ))}
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={addPieceLine}
              >
                Add Piece Line
              </Button>
              {form.formState.errors.dimensions?.root?.message && (
                <p className="text-sm font-medium text-destructive">
                  {form.formState.errors.dimensions.root.message}
                </p>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Other Details</CardTitle>
            </CardHeader>
            <CardContent>
              <FormField
                control={form.control}
                name="is_dangerous_goods"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center space-x-3 space-y-0 rounded-md border p-4 opacity-50">
                    <FormControl>
                      <Checkbox
                        checked={field.value}
                        onCheckedChange={field.onChange}
                        disabled
                      />
                    </FormControl>
                    <div className="space-y-1 leading-none">
                      <FormLabel>Dangerous Goods</FormLabel>
                      <FormDescription>
                        DG, AVI, and other special cargo are not yet supported.
                      </FormDescription>
                    </div>
                  </FormItem>
                )}
              />
            </CardContent>
          </Card>

          <div className="flex flex-col items-end gap-2 sm:flex-row sm:items-center sm:justify-end">
            {canCalculateQuote ? (
              <Button
                type="submit"
                variant="secondary"
                className="text-lg"
                disabled={isSubmitting}
              >
                {isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Calculating...
                  </>
                ) : (
                  "Calculate Quote"
                )}
              </Button>
            ) : (
              <p className="text-sm text-muted-foreground">
                Complete all required fields to calculate a quote.
              </p>
            )}
          </div>
        </form>
      </Form>
    </div>
  );
}
