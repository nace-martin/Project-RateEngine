"use client";

import { Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormDescription,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  V3_CARGO_TYPES,
  V3_PACKAGE_TYPES,
} from "@/lib/schemas/quoteSchema";

import type { QuoteCargoSectionProps } from "./quote-section-types";

export default function QuoteCargoSection({
  form,
  fields,
  append,
  remove,
  cargoMetrics,
}: QuoteCargoSectionProps) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-muted-foreground md:flex-row md:items-center md:justify-between">
        <span>Enter at least one cargo line with valid pieces, dimensions, and weight.</span>
        <div className="flex flex-wrap gap-4">
          <span>Act: <span className="font-medium text-foreground">{cargoMetrics.actualWeight} kg</span></span>
          <span>Vol: <span className="font-medium text-foreground">{cargoMetrics.volumetricWeight} kg</span></span>
          <span>Chg: <span className="font-bold text-primary">{cargoMetrics.chargeableWeight} kg</span></span>
        </div>
      </div>

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
                  <SelectItem key={key} value={value}>
                    {value}
                  </SelectItem>
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
          <div
            key={fieldItem.id}
            className="grid grid-cols-12 items-start gap-3 rounded-lg border p-4 md:flex md:flex-wrap md:items-start"
          >
            <div className="col-span-6 md:min-w-[120px] md:flex-[0.9]">
              <FormField
                control={form.control}
                name={`dimensions.${index}.pieces`}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Pieces</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} min={1} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-6 md:min-w-[160px] md:flex-[1.15]">
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
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-6 md:min-w-[110px] md:flex-1">
              <FormField
                control={form.control}
                name={`dimensions.${index}.length_cm`}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Length (cm)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-6 md:min-w-[110px] md:flex-1">
              <FormField
                control={form.control}
                name={`dimensions.${index}.width_cm`}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Width (cm)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-6 md:min-w-[110px] md:flex-1">
              <FormField
                control={form.control}
                name={`dimensions.${index}.height_cm`}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Height (cm)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-6 md:min-w-[110px] md:flex-1">
              <FormField
                control={form.control}
                name={`dimensions.${index}.gross_weight_kg`}
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className={index !== 0 ? "sr-only" : ""}>Weight (kg)</FormLabel>
                    <FormControl>
                      <Input type="number" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <div className="col-span-12 md:flex-none md:self-end">
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="text-destructive md:ml-1"
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
          onClick={() =>
            append({
              pieces: 1,
              length_cm: "",
              width_cm: "",
              height_cm: "",
              gross_weight_kg: "",
              package_type: "Box",
            })
          }
        >
          <Plus className="mr-2 h-4 w-4" />
          Add Line
        </Button>
      </div>
    </div>
  );
}
