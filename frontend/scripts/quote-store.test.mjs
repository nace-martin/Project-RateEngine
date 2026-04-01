import assert from "node:assert/strict";

import { initialQuoteState, useQuoteStore } from "../src/store/useQuoteStore.ts";

const readStoreData = () => {
  const state = useQuoteStore.getState();
  return {
    validationState: { ...state.validationState },
    currentStep: state.currentStep,
    isSpotMode: state.isSpotMode,
    contacts: [...state.contacts],
    isLoadingContacts: state.isLoadingContacts,
    selectedCustomer: state.selectedCustomer,
    originLocation: state.originLocation,
    destinationLocation: state.destinationLocation,
  };
};

const expectedInitialState = () => ({
  validationState: { ...initialQuoteState.validationState },
  currentStep: initialQuoteState.currentStep,
  isSpotMode: initialQuoteState.isSpotMode,
  contacts: [],
  isLoadingContacts: initialQuoteState.isLoadingContacts,
  selectedCustomer: initialQuoteState.selectedCustomer,
  originLocation: initialQuoteState.originLocation,
  destinationLocation: initialQuoteState.destinationLocation,
});

const resetStore = () => {
  useQuoteStore.getState().resetQuote();
};

const run = (name, fn) => {
  resetStore();
  fn();
  console.log(`PASS ${name}`);
};

run("resetQuote restores the full initial quote state", () => {
  const state = useQuoteStore.getState();

  state.setValidationState({
    customer: true,
    route: true,
    terms: true,
    cargo: true,
  });
  state.setCurrentStep(3);
  state.setSpotMode(true);
  state.setContacts([
    { id: "contact-1", first_name: "Ada", last_name: "Lovelace", email: "ada@example.com", phone: "123" },
  ]);
  state.setIsLoadingContacts(true);
  state.setSelectedCustomer({ id: "customer-1", name: "ACME" });
  state.setOriginLocation({ id: "origin-1", code: "POM", display_name: "Port Moresby", country_code: "PG" });
  state.setDestinationLocation({ id: "destination-1", code: "BNE", display_name: "Brisbane", country_code: "AU" });

  state.resetQuote();

  assert.deepStrictEqual(readStoreData(), expectedInitialState());
});

run("wizard navigation only changes currentStep and keeps workflow context intact", () => {
  const state = useQuoteStore.getState();
  const customer = { id: "customer-1", name: "ACME" };
  const origin = { id: "origin-1", code: "POM", display_name: "Port Moresby", country_code: "PG" };
  const destination = { id: "destination-1", code: "BNE", display_name: "Brisbane", country_code: "AU" };

  state.setSelectedCustomer(customer);
  state.setOriginLocation(origin);
  state.setDestinationLocation(destination);
  state.setSpotMode(true);
  state.nextStep();
  state.nextStep();
  state.prevStep();

  const snapshot = readStoreData();

  assert.equal(snapshot.currentStep, 1);
  assert.equal(snapshot.isSpotMode, true);
  assert.deepStrictEqual(snapshot.selectedCustomer, customer);
  assert.deepStrictEqual(snapshot.originLocation, origin);
  assert.deepStrictEqual(snapshot.destinationLocation, destination);
});

run("SPOT mode is cleared by resetQuote", () => {
  const state = useQuoteStore.getState();

  state.setSpotMode(true);
  state.setCurrentStep(4);
  state.resetQuote();

  const snapshot = readStoreData();

  assert.equal(snapshot.isSpotMode, false);
  assert.equal(snapshot.currentStep, 0);
});
