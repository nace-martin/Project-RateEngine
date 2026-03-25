"use client";

import type { FieldArrayWithId, UseFormReturn } from "react-hook-form";

import type { QuoteFormSchemaV3 } from "@/lib/schemas/quoteSchema";
import type { CompanySearchResult, Contact, LocationSearchResult } from "@/lib/types";

export type QuoteFormInstance = UseFormReturn<QuoteFormSchemaV3>;
export type QuoteDimensionField = FieldArrayWithId<QuoteFormSchemaV3, "dimensions", "id">;

export type QuoteCustomerSectionProps = {
  form: QuoteFormInstance;
  contacts: Contact[];
  isLoadingContacts: boolean;
  selectedCustomer: CompanySearchResult | null;
  selectedCustomerId: string | null;
  setSelectedCustomer: (customer: CompanySearchResult | null) => void;
  setSelectedCustomerId: (customerId: string | null) => void;
  getCompletedFieldClass: (isComplete: boolean) => string;
};

export type QuoteRouteSectionProps = {
  form: QuoteFormInstance;
  originLocation: LocationSearchResult | null;
  destinationLocation: LocationSearchResult | null;
  setOriginLocation: (location: LocationSearchResult | null) => void;
  setDestinationLocation: (location: LocationSearchResult | null) => void;
  setLocationFields: (
    direction: "origin" | "destination",
    location: LocationSearchResult | null,
    onChange: (value: string) => void,
  ) => void;
  getCompletedFieldClass: (isComplete: boolean) => string;
};

export type QuoteTermsSectionProps = {
  form: QuoteFormInstance;
  isImport: boolean;
  validIncoterms: string[];
};

export type QuoteCargoSectionProps = {
  form: QuoteFormInstance;
  fields: QuoteDimensionField[];
  append: (value: QuoteFormSchemaV3["dimensions"][number]) => void;
  remove: (index: number) => void;
  cargoMetrics: {
    actualWeight: number;
    volumetricWeight: number;
    chargeableWeight: number;
  };
};
