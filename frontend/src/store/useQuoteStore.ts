import { create } from "zustand";

import {
  DEFAULT_QUOTE_VALIDATION_STATE,
  type QuoteValidationState,
} from "../components/forms/quote-sections/quote-section-types.ts";
import type {
  CompanySearchResult,
  Contact,
  LocationSearchResult,
} from "../lib/types.ts";

const MAX_QUOTE_STEP = 4;

interface QuoteStoreData {
  validationState: QuoteValidationState;
  currentStep: number;
  isSpotMode: boolean;
  contacts: Contact[];
  isLoadingContacts: boolean;
  selectedCustomer: CompanySearchResult | null;
  originLocation: LocationSearchResult | null;
  destinationLocation: LocationSearchResult | null;
}

interface QuoteState extends QuoteStoreData {
  setValidationState: (validationState: QuoteValidationState) => void;
  nextStep: () => void;
  prevStep: () => void;
  resetQuote: () => void;
  setSpotMode: (enabled: boolean) => void;
  setCurrentStep: (step: number) => void;
  setContacts: (contacts: Contact[]) => void;
  setIsLoadingContacts: (loading: boolean) => void;
  setSelectedCustomer: (customer: CompanySearchResult | null) => void;
  setOriginLocation: (location: LocationSearchResult | null) => void;
  setDestinationLocation: (location: LocationSearchResult | null) => void;
}

export const initialQuoteState: QuoteStoreData = {
  validationState: { ...DEFAULT_QUOTE_VALIDATION_STATE },
  currentStep: 0,
  isSpotMode: false,
  contacts: [],
  isLoadingContacts: false,
  selectedCustomer: null,
  originLocation: null,
  destinationLocation: null,
};

const createInitialQuoteState = (): QuoteStoreData => ({
  ...initialQuoteState,
  validationState: { ...DEFAULT_QUOTE_VALIDATION_STATE },
  contacts: [],
});

export const useQuoteStore = create<QuoteState>((set) => ({
  ...createInitialQuoteState(),

  setValidationState: (validationState) =>
    set((state) => {
      const hasChanged = (Object.keys(validationState) as Array<keyof QuoteValidationState>)
        .some((key) => state.validationState[key] !== validationState[key]);

      return hasChanged
        ? { validationState: { ...validationState } }
        : state;
    }),

  nextStep: () =>
    set((state) => ({
      currentStep: Math.min(MAX_QUOTE_STEP, state.currentStep + 1),
    })),
  prevStep: () => set((state) => ({ currentStep: Math.max(0, state.currentStep - 1) })),

  resetQuote: () =>
    set({
      ...createInitialQuoteState(),
    }),

  setSpotMode: (enabled) => set((state) => (state.isSpotMode === enabled ? state : { isSpotMode: enabled })),
  setCurrentStep: (step) =>
    set((state) => {
      const nextStep = Math.min(MAX_QUOTE_STEP, Math.max(0, step));
      return state.currentStep === nextStep ? state : { currentStep: nextStep };
    }),
  setContacts: (contacts) => set((state) => (state.contacts === contacts ? state : { contacts })),
  setIsLoadingContacts: (isLoadingContacts) =>
    set((state) => (state.isLoadingContacts === isLoadingContacts ? state : { isLoadingContacts })),
  setSelectedCustomer: (selectedCustomer) =>
    set((state) => (state.selectedCustomer === selectedCustomer ? state : { selectedCustomer })),
  setOriginLocation: (originLocation) =>
    set((state) => (state.originLocation === originLocation ? state : { originLocation })),
  setDestinationLocation: (destinationLocation) =>
    set((state) => (state.destinationLocation === destinationLocation ? state : { destinationLocation })),
}));
