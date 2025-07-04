// Configuration for Foreign Exchange (FX) calculations

export const fxParameters = {
  DEFAULT_FX_RATE: 0.2499,       // Base FX Rate (e.g., PGK to USD TT Buy)
  DEFAULT_CAF_PERCENTAGE: 3,     // Default Currency Adjustment Factor percentage
  DEFAULT_FX_MARGIN_PERCENTAGE: 10 // Default Margin percentage for FX conversion
};

// In a more advanced setup, these could be fetched from a remote source
// or have different profiles (e.g., per currency pair or client type).
