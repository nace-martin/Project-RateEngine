import { useQuoteLogic } from "@/hooks/useQuoteLogic";
import { type QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import {
    V3_SERVICE_SCOPES,
    V3_LOCATION_TYPES,
    V3_CARGO_TYPES,
    V3_PACKAGE_TYPES,
    V3_INCOTERMS,
    V3_PAYMENT_TERMS
} from "@/lib/schemas/quoteSchema";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
    Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Plus, Trash2, AlertTriangle, Plane, Ship, Package } from "lucide-react";
import CompanySearch from "@/components/CompanySearchCombobox";
import LocationSearch from "@/components/LocationSearchCombobox";
import { Contact, CompanySearchResult, LocationSearchResult, User } from "@/lib/types";
import { useEffect } from "react";

interface QuoteFormProps {
    defaultValues?: Partial<QuoteFormSchemaV3>;
    initialCustomer?: CompanySearchResult;
    initialContacts?: Contact[];
    initialOrigin?: LocationSearchResult;
    initialDestination?: LocationSearchResult;
    user?: User | null;
    onSubmit: (data: QuoteFormSchemaV3) => Promise<void>;
    isSubmitting?: boolean;
    serverError?: string | null;
    isEditMode?: boolean;
    onDirtyChange?: (isDirty: boolean) => void;
}

export function QuoteForm({
    defaultValues,
    initialCustomer,
    initialContacts,
    initialOrigin,
    initialDestination,
    user,
    onSubmit,
    isSubmitting = false,
    serverError,
    isEditMode = false,
    onDirtyChange,
}: QuoteFormProps) {
    const {
        form,
        fields,
        append,
        remove,
        cargoMetrics,
        internalError,
        contacts,
        isLoadingContacts,
        selectedCustomer,
        setSelectedCustomer,
        selectedCustomerId,
        setSelectedCustomerId,
        originLocation,
        setOriginLocation,
        destinationLocation,
        setDestinationLocation,
        handleFormSubmit,
        setLocationFields,
        validIncoterms,
    } = useQuoteLogic({
        defaultValues,
        initialCustomer,
        initialContacts,
        initialOrigin,
        initialDestination,
        user,
        onSubmit,
        isEditMode,
    });

    const isImport = destinationLocation?.country_code === 'PG';
    const submitBusy = isSubmitting || form.formState.isSubmitting;

    useEffect(() => {
        onDirtyChange?.(form.formState.isDirty);
    }, [form.formState.isDirty, onDirtyChange]);

    // Log validation errors for debugging
    const onFormError = (errors: Record<string, unknown>) => {
        if (Object.keys(errors).length > 0) {
            console.warn("Form Validation Errors:", errors);
        }
    };

    return (
        <Form {...form}>
            <form onSubmit={form.handleSubmit(handleFormSubmit, onFormError)} className="space-y-8">

                {(internalError || serverError) && (
                    <div className="bg-destructive/15 text-destructive px-4 py-3 rounded-md flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5" />
                        <p className="text-sm font-medium">{internalError || serverError}</p>
                    </div>
                )}

                {/* --- 1. Customer Section --- */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Package className="h-5 w-5 text-primary" />
                            Customer Details
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-6">
                        <FormField
                            control={form.control}
                            name="customer_id"
                            render={({ field }) => (
                                <FormItem className="col-span-1 md:col-span-2">
                                    <FormLabel>Customer</FormLabel>
                                    <FormControl>
                                        <CompanySearch
                                            onSelect={(company) => {
                                                field.onChange(company?.id);
                                                setSelectedCustomerId(company?.id || null);
                                                setSelectedCustomer(company);
                                                // Reset contact when customer changes
                                                form.setValue('contact_id', '');
                                            }}
                                            value={selectedCustomer}
                                            placeholder="Search for a customer..."
                                        />
                                    </FormControl>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <FormField
                            control={form.control}
                            name="contact_id"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Contact Person</FormLabel>
                                    <Select
                                        onValueChange={field.onChange}
                                        value={field.value}
                                        disabled={!selectedCustomerId || isLoadingContacts}
                                    >
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue placeholder={
                                                    isLoadingContacts ? "Loading..." :
                                                        (!selectedCustomerId ? "Select customer first" : "Select contact")
                                                } />
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
                    </CardContent>
                </Card>

                {/* --- 2. Routing & Scope --- */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex items-center gap-2">
                            <Plane className="h-5 w-5 text-primary" />
                            Route & Service
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-6">
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <FormField
                                control={form.control}
                                name="mode"
                                render={({ field }) => (
                                    <FormItem>
                                        <FormLabel>Mode</FormLabel>
                                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                                            <FormControl>
                                                <SelectTrigger>
                                                    <SelectValue placeholder="Select mode" />
                                                </SelectTrigger>
                                            </FormControl>
                                            <SelectContent>
                                                <SelectItem value="AIR">
                                                    <div className="flex items-center gap-2">
                                                        <Plane className="h-4 w-4" /> Air Freight
                                                    </div>
                                                </SelectItem>
                                                <SelectItem value="SEA" disabled>
                                                    <div className="flex items-center gap-2">
                                                        <Ship className="h-4 w-4" /> Sea Freight (Coming Soon)
                                                    </div>
                                                </SelectItem>
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
                                        <Select onValueChange={field.onChange} defaultValue={field.value}>
                                            <FormControl>
                                                <SelectTrigger>
                                                    <SelectValue placeholder="Select scope" />
                                                </SelectTrigger>
                                            </FormControl>
                                            <SelectContent>
                                                {Object.entries(V3_SERVICE_SCOPES).map(([key, value]) => (
                                                    <SelectItem key={key} value={value}>{key}</SelectItem>
                                                ))}
                                            </SelectContent>
                                        </Select>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 relative">
                            {/* Connector Line (Visual) */}
                            <div className="hidden md:block absolute top-10 left-1/2 -translate-x-1/2 w-8 h-0.5 bg-border z-0" />

                            <FormField
                                control={form.control}
                                name="origin_location_id"
                                render={({ field }) => (
                                    <FormItem className="z-10">
                                        <FormLabel>Origin ({V3_LOCATION_TYPES.AIRPORT})</FormLabel>
                                        <FormControl>
                                            <LocationSearch
                                                onSelect={(loc) => {
                                                    setOriginLocation(loc);
                                                    setLocationFields("origin", loc, field.onChange);
                                                }}
                                                value={field.value}
                                                selectedLabel={originLocation ? `${originLocation.display_name} (${originLocation.code})` : undefined}
                                                placeholder="Search airport..."
                                            />
                                        </FormControl>
                                        <FormDescription>
                                            {originLocation ? `${originLocation.display_name} [${originLocation.country_code}]` : "Search by code or city"}
                                        </FormDescription>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />

                            <FormField
                                control={form.control}
                                name="destination_location_id"
                                render={({ field }) => (
                                    <FormItem className="z-10">
                                        <FormLabel>Destination ({V3_LOCATION_TYPES.AIRPORT})</FormLabel>
                                        <FormControl>
                                            <LocationSearch
                                                onSelect={(loc) => {
                                                    setDestinationLocation(loc);
                                                    setLocationFields("destination", loc, field.onChange);
                                                }}
                                                value={field.value}
                                                selectedLabel={destinationLocation ? `${destinationLocation.display_name} (${destinationLocation.code})` : undefined}
                                                placeholder="Search airport..."
                                            />
                                        </FormControl>
                                        <FormDescription>
                                            {destinationLocation ? `${destinationLocation.display_name} [${destinationLocation.country_code}]` : "Search by code or city"}
                                        </FormDescription>
                                        <FormMessage />
                                    </FormItem>
                                )}
                            />
                        </div>
                    </CardContent>
                </Card>

                {/* --- 3. Shipment Terms --- */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg">Shipment Terms</CardTitle>
                    </CardHeader>
                    <CardContent className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <FormField
                            control={form.control}
                            name="payment_term"
                            render={({ field }) => (
                                <FormItem>
                                    <FormLabel>Payment Term</FormLabel>
                                    <Select onValueChange={field.onChange} value={field.value}>
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            {Object.entries(V3_PAYMENT_TERMS).map(([key, value]) => (
                                                <SelectItem key={key} value={value}>{key}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
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
                                                <SelectValue />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            {Object.entries(V3_INCOTERMS).map(([key, value]) => (
                                                <SelectItem
                                                    key={key}
                                                    value={value}
                                                    disabled={!validIncoterms.includes(value)}
                                                >
                                                    {key} {(!validIncoterms.includes(value)) && "(N/A)"}
                                                </SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <FormDescription>
                                        {isImport ? "Import shipment" : "Export/Domestic shipment"}
                                    </FormDescription>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                    </CardContent>
                </Card>

                {/* --- 4. Cargo Details --- */}
                <Card>
                    <CardHeader>
                        <CardTitle className="text-lg flex justify-between items-center">
                            <span>Cargo Details</span>
                            <div className="text-sm font-normal text-muted-foreground flex gap-4">
                                <span>Act: <span className="font-medium text-foreground">{cargoMetrics.actualWeight} kg</span></span>
                                <span>Vol: <span className="font-medium text-foreground">{cargoMetrics.volumetricWeight} kg</span></span>
                                <span>Chg: <span className="font-bold text-primary">{cargoMetrics.chargeableWeight} kg</span></span>
                            </div>
                        </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                        <FormField
                            control={form.control}
                            name="cargo_type"
                            render={({ field }) => (
                                <FormItem className="max-w-md">
                                    <FormLabel>Cargo Type</FormLabel>
                                    <Select onValueChange={field.onChange} value={field.value}>
                                        <FormControl>
                                            <SelectTrigger>
                                                <SelectValue />
                                            </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                            {Object.entries(V3_CARGO_TYPES).map(([key, value]) => (
                                                <SelectItem key={key} value={value}>{value}</SelectItem>
                                            ))}
                                        </SelectContent>
                                    </Select>
                                    <FormDescription>
                                        Use cargo type to identify DG, live animals, perishables, valuables, and other special handling.
                                    </FormDescription>
                                    <FormMessage />
                                </FormItem>
                            )}
                        />

                        <div className="space-y-4">
                            {fields.map((fieldItem, index) => (
                                <div key={fieldItem.id} className="grid grid-cols-12 gap-3 items-end rounded-lg border p-4">
                                    <div className="col-span-12 md:col-span-2">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.pieces`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Pieces</FormLabel>
                                                    <FormControl>
                                                        <Input type="number" {...field} min={1} />
                                                    </FormControl>
                                                </FormItem>
                                                )}
                                            />
                                    </div>
                                    <div className="col-span-12 md:col-span-3">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.package_type`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Package Type</FormLabel>
                                                    <Select onValueChange={field.onChange} value={field.value}>
                                                        <FormControl>
                                                            <SelectTrigger className="w-full">
                                                                <SelectValue placeholder="Select type" />
                                                            </SelectTrigger>
                                                        </FormControl>
                                                        <SelectContent>
                                                            {Object.values(V3_PACKAGE_TYPES).map((packageType) => (
                                                                <SelectItem key={packageType} value={packageType}>
                                                                    {packageType}
                                                                </SelectItem>
                                                            ))}
                                                        </SelectContent>
                                                    </Select>
                                                </FormItem>
                                            )}
                                        />
                                    </div>
                                    <div className="col-span-6 md:col-span-1">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.length_cm`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Length (cm)</FormLabel>
                                                    <FormControl>
                                                        <Input type="number" {...field} />
                                                    </FormControl>
                                                </FormItem>
                                                )}
                                            />
                                    </div>
                                    <div className="col-span-6 md:col-span-1">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.width_cm`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Width (cm)</FormLabel>
                                                    <FormControl>
                                                        <Input type="number" {...field} />
                                                    </FormControl>
                                                </FormItem>
                                                )}
                                            />
                                    </div>
                                    <div className="col-span-6 md:col-span-1">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.height_cm`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Height (cm)</FormLabel>
                                                    <FormControl>
                                                        <Input type="number" {...field} />
                                                    </FormControl>
                                                </FormItem>
                                                )}
                                            />
                                    </div>
                                    <div className="col-span-6 md:col-span-1">
                                        <FormField
                                            control={form.control}
                                            name={`dimensions.${index}.gross_weight_kg`}
                                            render={({ field }) => (
                                                <FormItem>
                                                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Weight (kg)</FormLabel>
                                                    <FormControl>
                                                        <Input type="number" {...field} />
                                                    </FormControl>
                                                </FormItem>
                                                )}
                                            />
                                    </div>
                                    <div className="col-span-12 md:col-span-1">
                                        <Button
                                            type="button"
                                            variant="ghost"
                                            size="icon"
                                            className="text-destructive md:ml-auto"
                                            onClick={() => remove(index)}
                                            disabled={fields.length === 1}
                                        >
                                            <Trash2 className="h-4 w-4" />
                                        </Button>
                                    </div>
                                </div>
                            ))}
                            <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => append({ pieces: 1, length_cm: "", width_cm: "", height_cm: "", gross_weight_kg: "", package_type: "Box" })}
                            >
                                <Plus className="h-4 w-4 mr-2" /> Add Line
                            </Button>
                        </div>
                    </CardContent>
                </Card>

                <div className="flex justify-end gap-4">
                    <Button type="submit" size="lg" disabled={submitBusy}>
                        {submitBusy ? (
                            <>
                                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                                Calculating...
                            </>
                        ) : (
                            "Generate Quote"
                        )}
                    </Button>
                </div>
            </form>
        </Form>
    );
}

// Deprecated: default export
export default QuoteForm;
