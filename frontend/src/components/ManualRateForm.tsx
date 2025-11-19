"use client";

import { useState } from "react";
import { useForm, type Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
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
import type { V3ManualOverride } from "@/lib/types";

type ManualOverride = V3ManualOverride;

const UNIT_OPTIONS = ["Per Shipment", "Per KG"] as const;

const manualRateFormSchema = z.object({
  cost_fcy: z.string().min(1, "Cost is required"),
  currency: z
    .string()
    .min(3, "Currency is required")
    .max(3, "Use the 3-letter code")
    .transform((value) => value.toUpperCase()),
  unit: z.enum(UNIT_OPTIONS),
  min_charge_fcy: z
    .string()
    .optional()
    .transform((value) => (value === "" ? undefined : value)),
});

type ManualRateFormValues = z.infer<typeof manualRateFormSchema>;

interface ManualRateFormProps {
  service_component_id: string;
  service_component_desc: string;
  onSubmit: (override: ManualOverride) => Promise<void> | void;
  triggerLabel?: string;
}

export function ManualRateForm({
  service_component_id,
  service_component_desc,
  onSubmit,
  triggerLabel = "Enter Manual Rate",
}: ManualRateFormProps) {
  const [open, setOpen] = useState(false);
  const form = useForm<ManualRateFormValues>({
    resolver: zodResolver(manualRateFormSchema) as Resolver<ManualRateFormValues>,
    defaultValues: {
      cost_fcy: "",
      currency: "",
      unit: UNIT_OPTIONS[0],
      min_charge_fcy: "",
    },
  });

  const handleClose = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (!nextOpen) {
      form.reset();
    }
  };

  const handleSubmit = async (values: ManualRateFormValues) => {
    const payload: ManualOverride = {
      service_component_id,
      cost_fcy: values.cost_fcy,
      currency: values.currency,
      unit: values.unit,
      ...(values.min_charge_fcy
        ? { min_charge_fcy: values.min_charge_fcy }
        : {}),
    };

    await onSubmit(payload);
    handleClose(false);
  };

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogTrigger asChild>
        <Button variant="destructive" size="sm">
          {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Enter Manual Rate</DialogTitle>
          <DialogDescription>
            Provide the manual buy cost for {service_component_desc}.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="space-y-4"
          >
            <FormField
              control={form.control}
              name="cost_fcy"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Buy Cost</FormLabel>
                  <FormControl>
                    <Input placeholder="0.00" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="currency"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Currency</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="USD"
                      maxLength={3}
                      {...field}
                      onChange={(event) =>
                        field.onChange(event.target.value.toUpperCase())
                      }
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="unit"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Unit</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger>
                        <SelectValue placeholder="Select unit" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {UNIT_OPTIONS.map((option) => (
                        <SelectItem key={option} value={option}>
                          {option}
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
              name="min_charge_fcy"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Minimum Charge (Optional)</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="0.00"
                      {...field}
                      value={field.value ?? ""}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="submit">Save Rate</Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}

export default ManualRateForm;
