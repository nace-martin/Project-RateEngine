// frontend/src/app/quotes/new/page.tsx

"use client";

import { useState, useCallback, useEffect } from 'react';
import { useForm, useFieldArray, Controller } from 'react-hook-form'; // Import hooks
import { zodResolver } from '@hookform/resolvers/zod'; // Import resolver
import { z } from 'zod'; // Import zod

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { createQuoteV2, searchCompanies, getCompanyContacts } from '@/lib/api';
import { Combobox } from '@/components/ui/combobox';
import { useDebouncedCallback } from 'use-debounce';
import { QuoteFormSchema, QuoteFormData } from '@/lib/schemas/quoteSchema'; // Import schema and type
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"; // Import Form components

// Define a type for company search options
type CompanyOption = { value: string; label: string };
type ContactOption = { value: string; label: string };

const currencies = ["PGK", "AUD", "USD", "CNY", "EUR", "GBP"]; // Example list

export default function NewQuotePage() {
  // --- react-hook-form setup ---
  const form = useForm<QuoteFormData>({
    resolver: zodResolver(QuoteFormSchema),
    defaultValues: {
      mode: "AIR", 
      scenario: "IMPORT_A2D_AGENT_AUD",
      origin_code: "BNE",
      destination_code: "POM",
      pieces: [{ pieces: 1, length: 100, width: 80, height: 50, weight: 120 }],
      bill_to_id: "", 
      shipper_id: "",
      consignee_id: "",
      contact_id: undefined,
      buy_lines: [
        { description: "Air Freight", currency: "AUD", amount: 1250.00 },
      ],
      agent_dest_lines_aud: [],
    },
  });

  // Access form state and methods
  const { control, handleSubmit, watch, setValue, getValues, formState: { errors } } = form;

  // useFieldArray for dynamic pieces
  const { fields: pieceFields, append: appendPiece, remove: removePiece } = useFieldArray({
    control, name: "pieces",
  });

  const { fields: buyLineFields, append: appendBuyLine, remove: removeBuyLine } = useFieldArray({
    control, name: "buy_lines",
  });
  const { fields: agentLineFields, append: appendAgentLine, remove: removeAgentLine } = useFieldArray({
    control, name: "agent_dest_lines_aud",
  });

  // Watch relevant fields to update calculations or apply rules
  const watchedPieces = watch("pieces");
  const watchedScenario = watch("scenario");
  const watchedMode = watch("mode");
  const watchedBillToId = watch("bill_to_id");

  // --- State for Comboboxes ---
  const [billToOptions, setBillToOptions] = useState<CompanyOption[]>([]);
  const [shipperOptions, setShipperOptions] = useState<CompanyOption[]>([]);
  const [consigneeOptions, setConsigneeOptions] = useState<CompanyOption[]>([]);
  const [contactOptions, setContactOptions] = useState<ContactOption[]>([]);
  const [isLoadingContacts, setIsLoadingContacts] = useState(false);

  // Debounced search handler
  const handleSearch = useDebouncedCallback(async (query: string, setter: React.Dispatch<React.SetStateAction<CompanyOption[]>>) => {
    const companies = await searchCompanies(query);
    setter(companies.map(c => ({ value: c.id, label: c.name })));
  }, 300);

  // --- State for API interaction ---
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [quoteResult, setQuoteResult] = useState<any>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  // --- Calculation Logic (using watched values) ---
  const calculateVolume = (piece: any) => (piece.length * piece.width * piece.height) / 1000000;
  const calculateVolumetricWeight = (piece: any) => calculateVolume(piece) * 167;
  const totalGrossWeight = watchedPieces.reduce((total, p) => total + ((p.pieces || 0) * (p.weight || 0)), 0);
  const totalVolumetricWeight = watchedPieces.reduce((total, p) => total + ((p.pieces || 0) * calculateVolumetricWeight(p)), 0);
  const chargeableWeight = Math.max(totalGrossWeight, totalVolumetricWeight).toFixed(2);

  // --- Business Rule: Lock Bill To for Collect ---
  const isCollect = watchedScenario === 'IMPORT_D2D_COLLECT';
  const isBillToLocked = isCollect;
  useEffect(() => {
    if (isCollect) {
      const consigneeId = form.getValues('consignee_id');
      if (consigneeId && form.getValues('bill_to_id') !== consigneeId) {
        setValue('bill_to_id', consigneeId, { shouldValidate: true });
        handleSearch(consigneeId, setBillToOptions);
      }
    }
  }, [isCollect, form, setValue, handleSearch]);

  // --- NEW EFFECT: Fetch Contacts when Bill To changes ---
  useEffect(() => {
    const fetchContacts = async () => {
      if (!watchedBillToId) {
        setContactOptions([]); // Clear options if no company selected
        setValue('contact_id', undefined); // Clear selected contact
        return;
      }
      setIsLoadingContacts(true);
      try {
        const contacts = await getCompanyContacts(watchedBillToId);
        setContactOptions(contacts.map(c => ({
          value: c.id,
          label: `${c.first_name} ${c.last_name} (${c.email})`
        })));
        // Optionally reset contact if the previously selected one isn't in the new list
        const currentContactId = getValues('contact_id');
        if (currentContactId && !contacts.some(c => c.id === currentContactId)) {
           setValue('contact_id', undefined);
        }
      } catch (e) {
         console.error("Failed to load contacts", e);
         setContactOptions([]); // Clear on error
      } finally {
        setIsLoadingContacts(false);
      }
    };
    fetchContacts();
  }, [watchedBillToId, setValue, getValues]); // Depend on watchedBillToId

  // --- API Submission ---
  const onSubmit = async (data: QuoteFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);
    setQuoteResult(null);

    // Prepare payload 
    const payload = {
      ...data,
      chargeable_kg: chargeableWeight,
      contact_id: data.contact_id || null,
    };

    try {
      const result = await createQuoteV2(payload);
      setQuoteResult(result);
    } catch (err: any) {
      setSubmitError(err.message || 'An unknown error occurred.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="container mx-auto p-4 space-y-6">
      <h1 className="text-2xl font-bold">New Quote (Smart Form)</h1>
      <Form {...form}> 
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              
              {/* Mode Selection Card (no change) */}
              <Card>
                  <CardHeader><CardTitle>Mode & Scenario</CardTitle></CardHeader>
                  <CardContent className="grid grid-cols-2 gap-4">
                     <FormField
                        control={control}
                        name="mode"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Mode</FormLabel>
                             <Select onValueChange={field.onChange} defaultValue={field.value} disabled> {/* Disabled for now as only AIR exists */}
                              <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                              <SelectContent>
                                <SelectItem value="AIR">Air Freight</SelectItem>
                                {/* <SelectItem value="SEA">Sea Freight</SelectItem> */}
                                {/* <SelectItem value="CUSTOMS">Customs Only</SelectItem> */}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                     <FormField
                        control={control}
                        name="scenario"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Quote Type / Scenario</FormLabel>
                             <Select onValueChange={field.onChange} defaultValue={field.value}>
                              <FormControl><SelectTrigger><SelectValue /></SelectTrigger></FormControl>
                              <SelectContent>
                                <SelectItem value="IMPORT_D2D_COLLECT">Import D2D Collect</SelectItem>
                                <SelectItem value="EXPORT_D2D_PREPAID">Export D2D Prepaid</SelectItem>
                                <SelectItem value="IMPORT_A2D_AGENT_AUD">Import A2D Agent (AUD)</SelectItem>
                                {/* Add other scenarios */}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                  </CardContent>
              </Card>

              {/* Conditional Rendering: Only show if mode is AIR */}
              {watchedMode === 'AIR' && (
                <>
                  {/* Shipment Details Card (no change) */}
                  <Card>
                    <CardHeader><CardTitle>Shipment Details</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                      <div className="grid grid-cols-2 gap-4">
                        <FormField control={control} name="origin_code" render={({ field }) => (
                          <FormItem>
                            <FormLabel>Origin</FormLabel>
                            <FormControl><Input {...field} onChange={e => field.onChange(e.target.value.toUpperCase())} /></FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                        <FormField control={control} name="destination_code" render={({ field }) => (
                          <FormItem>
                            <FormLabel>Destination</FormLabel>
                            <FormControl><Input {...field} onChange={e => field.onChange(e.target.value.toUpperCase())} /></FormControl>
                            <FormMessage />
                          </FormItem>
                        )} />
                      </div>

                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Pcs</TableHead><TableHead>Length (cm)</TableHead><TableHead>Width (cm)</TableHead>
                            <TableHead>Height (cm)</TableHead><TableHead>Weight (kg)</TableHead><TableHead></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {pieceFields.map((item, index) => (
                            <TableRow key={item.id}>
                              <TableCell><FormField control={control} name={`pieces.${index}.pieces`} render={({ field }) => <FormItem><FormControl><Input type="number" {...field} /></FormControl></FormItem>} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.length`} render={({ field }) => <FormItem><FormControl><Input type="number" {...field} /></FormControl></FormItem>} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.width`} render={({ field }) => <FormItem><FormControl><Input type="number" {...field} /></FormControl></FormItem>} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.height`} render={({ field }) => <FormItem><FormControl><Input type="number" {...field} /></FormControl></FormItem>} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.weight`} render={({ field }) => <FormItem><FormControl><Input type="number" {...field} /></FormControl></FormItem>} /></TableCell>
                              <TableCell><Button type="button" variant="destructive" size="sm" onClick={() => removePiece(index)}>X</Button></TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      {/* Display validation errors for the pieces array */}
                      {errors.pieces?.root?.message && <p className="text-sm font-medium text-destructive">{errors.pieces.root.message}</p>}
                      {/* Display individual piece errors (optional) */}
                      {errors.pieces?.map((pieceError, index) => (
                        Object.values(pieceError || {}).map((fieldError: any) => (
                          fieldError?.message && <p key={`${index}-${fieldError.message}`} className="text-sm font-medium text-destructive">Piece {index + 1}: {fieldError.message}</p>
                        ))
                      ))}
                      <Button type="button" variant="outline" onClick={() => appendPiece({ pieces: 1, length: 0, width: 0, height: 0, weight: 0 })}>Add Piece</Button>
                    </CardContent>
                  </Card>

                  {/* --- UPDATED: Parties Card --- */}
                  <Card>
                    <CardHeader><CardTitle>Parties</CardTitle><CardDescription>Select the companies involved.</CardDescription></CardHeader>
                    <CardContent className="space-y-4">
                      <FormField control={control} name="consignee_id" render={({ field }) => (
                          <FormItem className="flex flex-col">
                            <FormLabel>Consignee</FormLabel>
                            <Combobox
                              options={consigneeOptions}
                              value={field.value}
                              onChange={field.onChange} // RHF handles value update
                              onSearch={(query) => handleSearch(query, setConsigneeOptions)}
                              placeholder="Select Consignee..." searchPlaceholder="Search companies..."
                            />
                            <FormMessage />
                          </FormItem>
                        )} />
                      <FormField control={control} name="bill_to_id" render={({ field }) => (
                          <FormItem className="flex flex-col">
                            <FormLabel>Bill To Account {isBillToLocked && "(Locked to Consignee)"}</FormLabel>
                            <Combobox
                              options={billToOptions}
                              value={field.value}
                              onChange={field.onChange}
                              onSearch={(query) => handleSearch(query, setBillToOptions)}
                              placeholder="Select Bill To..." searchPlaceholder="Search companies..."
                              // Disable the combobox if the rule applies
                              disabled={isBillToLocked} 
                            />
                             <FormDescription>For Collect shipments, Bill To is automatically set to Consignee.</FormDescription>
                            <FormMessage />
                          </FormItem>
                        )} />

                      {/* --- NEW: Contact Dropdown --- */}
                      <FormField
                        control={control}
                        name="contact_id"
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Primary Contact (for Bill To)</FormLabel>
                            <Select
                              onValueChange={field.onChange}
                              value={field.value ?? ""} // Handle undefined value
                              disabled={!watchedBillToId || isLoadingContacts} // Disable if no Bill To or loading
                            >
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder={
                                    isLoadingContacts
                                      ? "Loading..."
                                      : !watchedBillToId
                                      ? "Select a Bill To account first"
                                      : contactOptions.length === 0
                                      ? "No contacts found"
                                      : "Select a contact..."
                                  } />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {contactOptions.map(option => (
                                  <SelectItem key={option.value} value={option.value}>
                                    {option.label}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      {/* --- */}

                      <FormField control={control} name="shipper_id" render={({ field }) => (
                          <FormItem className="flex flex-col">
                            <FormLabel>Shipper</FormLabel>
                            <Combobox
                              options={shipperOptions}
                              value={field.value}
                              onChange={field.onChange}
                              onSearch={(query) => handleSearch(query, setShipperOptions)}
                              placeholder="Select Shipper..." searchPlaceholder="Search companies..."
                            />
                            <FormMessage />
                          </FormItem>
                        )} />
                    </CardContent>
                  </Card>
                  {/* --- End Parties Card --- */}

                  {/* --- NEW: Buy Lines (Origin/Freight Charges) Card --- */}
                   <Card>
                    <CardHeader><CardTitle>Origin & Freight Charges</CardTitle></CardHeader>
                    <CardContent className="space-y-4">
                      <Table>
                        <TableHeader>
                          <TableRow>
                            <TableHead>Description</TableHead>
                            <TableHead>Currency</TableHead>
                            <TableHead className="text-right">Amount</TableHead>
                            <TableHead></TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {buyLineFields.map((item, index) => (
                            <TableRow key={item.id}>
                              <TableCell>
                                <FormField
                                  control={control}
                                  name={`buy_lines.${index}.description`}
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormControl>
                                        <Input {...field} />
                                      </FormControl>
                                    </FormItem>
                                  )}
                                />
                              </TableCell>
                              <TableCell>
                                <FormField
                                  control={control}
                                  name={`buy_lines.${index}.currency`}
                                  render={({ field }) => (
                                    <FormItem>
                                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                                        <FormControl>
                                          <SelectTrigger>
                                            <SelectValue />
                                          </SelectTrigger>
                                        </FormControl>
                                        <SelectContent>
                                          {currencies.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                                        </SelectContent>
                                      </Select>
                                    </FormItem>
                                  )} />
                              </TableCell>
                              <TableCell>
                                <FormField
                                  control={control}
                                  name={`buy_lines.${index}.amount`}
                                  render={({ field }) => (
                                    <FormItem>
                                      <FormControl>
                                        <Input type="number" step="0.01" className="text-right" {...field} />
                                      </FormControl>
                                    </FormItem>
                                  )} />
                              </TableCell>
                              <TableCell><Button type="button" variant="destructive" size="sm" onClick={() => removeBuyLine(index)}>X</Button></TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                      {/* Add validation messages if needed */}
                      <Button type="button" variant="outline" onClick={() => appendBuyLine({ description: "", currency: "AUD", amount: 0 })}>Add Origin/Freight Charge</Button>
                    </CardContent>
                  </Card>

                  {/* --- NEW: Agent Destination Lines (Conditional) --- */}
                  {/* Only show this section for relevant export scenarios */}
                  {(watchedScenario === 'EXPORT_D2D_PREPAID' || watchedScenario === 'EXPORT_D2D_COLLECT') && (
                    <Card>
                      <CardHeader><CardTitle>Agent Destination Charges (AUD)</CardTitle></CardHeader>
                      <CardContent className="space-y-4">
                        <Table>
                          <TableHeader>
                            <TableRow>
                              <TableHead>Description</TableHead>
                              <TableHead className="text-right">Amount (AUD)</TableHead>
                              <TableHead></TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {agentLineFields.map((item, index) => (
                              <TableRow key={item.id}>
                                <TableCell>
                                  <FormField
                                    control={control}
                                    name={`agent_dest_lines_aud.${index}.description`}
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormControl>
                                          <Input {...field} />
                                        </FormControl>
                                      </FormItem>
                                    )}
                                  />
                                </TableCell>
                                <TableCell>
                                  <FormField
                                    control={control}
                                    name={`agent_dest_lines_aud.${index}.amount`}
                                    render={({ field }) => (
                                      <FormItem>
                                        <FormControl>
                                          <Input type="number" step="0.01" className="text-right" {...field} />
                                        </FormControl>
                                      </FormItem>
                                    )}
                                  />
                                </TableCell>
                                <TableCell><Button type="button" variant="destructive" size="sm" onClick={() => removeAgentLine(index)}>X</Button></TableCell>
                                {/* Hidden currency field as it's always AUD */}
                                <Controller
                                  name={`agent_dest_lines_aud.${index}.currency`}
                                  control={control}
                                  defaultValue="AUD"
                                  render={({ field }) => <input type="hidden" {...field} />}
                                />
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                        {/* Add validation messages if needed */}
                        <Button type="button" variant="outline" onClick={() => appendAgentLine({ description: "", currency: "AUD", amount: 0 })}>Add Agent Charge</Button>
                      </CardContent>
                    </Card>
                  )}
                  {/* --- */}
                </>
              )} 
                 
            </div>

            {/* Summary and Actions Card (no change) */}
            <div className="space-y-6">
              <Card>
                <CardHeader><CardTitle>Quote Summary</CardTitle></CardHeader>
                <CardContent className="space-y-4">
                    {/* Mode specific summary */}
                    {watchedMode === 'AIR' && (
                        <div className="space-y-2">
                            <div className="flex justify-between"><span>Gross Wt:</span> <strong>{totalGrossWeight.toFixed(2)} kg</strong></div>
                            <div className="flex justify-between"><span>Volume Wt:</span> <strong>{totalVolumetricWeight.toFixed(2)} kg</strong></div>
                            <div className="flex justify-between text-lg font-bold"><span>Chargeable Wt:</span> <strong>{chargeableWeight} kg</strong></div>
                        </div>
                    )}
                    <Button type="submit" className="w-full" disabled={isSubmitting}>
                      {isSubmitting ? 'Calculating...' : 'Calculate Quote'}
                    </Button>
                </CardContent>
              </Card>
              
              {submitError && (
                  <Card className="bg-red-50 border-red-200"><CardContent className="p-4"><p className="text-red-700 font-semibold">Error: {submitError}</p></CardContent></Card>
              )}
      
              {quoteResult && (
                <Card>
                  <CardHeader><CardTitle>Calculation Result</CardTitle></CardHeader>
                  <CardContent>
                      <div className="space-y-2">
                          <div className="flex justify-between"><span>Quote Number:</span> <strong>{quoteResult.quote_number}</strong></div>
                          <div className="flex justify-between text-xl font-bold"><span>Grand Total:</span> <strong>{quoteResult.totals?.grand_total_pgk} PGK</strong></div>
                      </div>
                      <a href={`http://127.0.0.1:8000/api/v2/quotes/${quoteResult.id}/pdf/`} target="_blank" rel="noopener noreferrer">
                          <Button className="w-full mt-4" variant="outline">Download PDF</Button>
                      </a>
                  </CardContent>
                </Card>
              )}
            </div>
          </div>
        </form>
      </Form>
    </div>
  );
}