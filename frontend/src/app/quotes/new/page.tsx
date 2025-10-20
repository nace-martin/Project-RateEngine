// frontend/src/app/quotes/new/page.tsx

"use client";

import { useState, useCallback, useEffect } from 'react';
import { useForm, useFieldArray, Controller } from 'react-hook-form'; // Import hooks
import { zodResolver } from '@hookform/resolvers/zod'; // Import resolver
import { z } from 'zod'; // Import zod

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { createQuoteV2, searchCompanies } from '@/lib/api';
import { Combobox } from '@/components/ui/combobox';
import { useDebouncedCallback } from 'use-debounce';
import { QuoteFormSchema, QuoteFormData } from '@/lib/schemas/quoteSchema'; // Import schema and type
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from "@/components/ui/form"; // Import Form components

// Define a type for company search options
type CompanyOption = { value: string; label: string };

export default function NewQuotePage() {
  // --- react-hook-form setup ---
  const form = useForm<QuoteFormData>({
    resolver: zodResolver(QuoteFormSchema),
    defaultValues: {
      mode: "AIR", // Default mode
      scenario: "IMPORT_D2D_COLLECT",
      origin_code: "BNE",
      destination_code: "POM",
      pieces: [{ pieces: 1, length: 100, width: 80, height: 50, weight: 120 }],
      // Need default values for party IDs to avoid uncontrolled component errors
      bill_to_id: "", 
      shipper_id: "",
      consignee_id: "",
    },
  });

  // Access form state and methods
  const { control, handleSubmit, watch, setValue, formState: { errors } } = form;

  // useFieldArray for dynamic pieces
  const { fields: pieceFields, append: appendPiece, remove: removePiece } = useFieldArray({
    control,
    name: "pieces",
  });

  // Watch relevant fields to update calculations or apply rules
  const watchedPieces = watch("pieces");
  const watchedScenario = watch("scenario");
  const watchedMode = watch("mode"); 

  // --- State for Comboboxes ---
  const [billToOptions, setBillToOptions] = useState<CompanyOption[]>([]);
  const [shipperOptions, setShipperOptions] = useState<CompanyOption[]>([]);
  const [consigneeOptions, setConsigneeOptions] = useState<CompanyOption[]>([]);

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
  // Determine if Bill To should be locked to Consignee
  const isCollect = watchedScenario?.includes('COLLECT');
  const isBillToLocked = isCollect; // Simple rule for now

  // Effect to enforce the rule: If collect, set Bill To = Consignee
  useEffect(() => {
    if (isCollect) {
      const consigneeId = form.getValues('consignee_id');
      if (consigneeId && form.getValues('bill_to_id') !== consigneeId) {
        setValue('bill_to_id', consigneeId, { shouldValidate: true });
        // Also update options if needed, assuming consignee is searchable
         handleSearch(consigneeId, setBillToOptions); // Trigger search to populate options if needed
      }
    }
  }, [isCollect, form, setValue, handleSearch]);


  // --- API Submission ---
  const onSubmit = async (data: QuoteFormData) => {
    setIsSubmitting(true);
    setSubmitError(null);
    setQuoteResult(null);

    // Prepare payload (add chargeable weight, map data if needed)
    const payload = {
      ...data,
      chargeable_kg: chargeableWeight,
      // Example buy/agent lines - make these dynamic later
      buy_lines: [
        { currency: 'AUD', amount: '1250.00', description: 'Air Freight Charges' },
        { currency: 'AUD', amount: '75.00', description: 'Origin Handling' },
      ],
      agent_dest_lines_aud: [
        { "amount": "250.00", "description": "Agent Handling and Delivery" }
      ]
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
      {/* Use the Form provider from react-hook-form */}
      <Form {...form}> 
        <form onSubmit={handleSubmit(onSubmit)}>
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            <div className="lg:col-span-2 space-y-6">
              
              {/* Mode Selection Card - Simple for now */}
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
                  {/* Shipment Details Card */}
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

                      <Label>Dimensions & Weight</Label>
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
                              <TableCell><FormField control={control} name={`pieces.${index}.pieces`} render={({ field }) => <Input type="number" {...field} />} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.length`} render={({ field }) => <Input type="number" {...field} />} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.width`} render={({ field }) => <Input type="number" {...field} />} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.height`} render={({ field }) => <Input type="number" {...field} />} /></TableCell>
                              <TableCell><FormField control={control} name={`pieces.${index}.weight`} render={({ field }) => <Input type="number" {...field} />} /></TableCell>
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

                  {/* Parties Card */}
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
                </>
              )} 
              {/* Add placeholders or forms for SEA/CUSTOMS modes later */}
              {/* {watchedMode === 'SEA' && <Card><CardContent>Sea Freight Details...</CardContent></Card>} */}
                 
            </div>

            {/* Summary and Actions Card */}
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