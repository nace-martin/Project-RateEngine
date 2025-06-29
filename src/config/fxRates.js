// src/config/fxRates.js

/**
 * Foreign Exchange Rates for Project RateEngine, pegged to a single base currency.
 *
 * This new structure allows for conversion between ANY two currencies in the list,
 * not just from a foreign currency to PGK. This is essential for our new,

 * more flexible quoting logic.
 *
 * All rates are relative to 1 unit of the baseCurrency (USD).
 */

export const baseCurrency = 'USD';

export const fxRates = {
  USD: 1.00,
  PGK: 3.85,
  AUD: 1.52,
  NZD: 1.65,
  EUR: 0.92,
};

/**
 * HOW TO USE THIS:
 *
 * To convert an amount FROM a currency TO another currency:
 * * 1. Convert the initial amount to the base currency (USD).
 * amountInUSD = initialAmount / fxRates[fromCurrency];
 *
 * 2. Convert the USD amount to the target currency.
 * finalAmount = amountInUSD * fxRates[toCurrency];
 *
 * Example: Convert 100 PGK to AUD
 * 1. 100 PGK / 3.85 (rate for PGK) = 25.97 USD
 * 2. 25.97 USD * 1.52 (rate for AUD) = 39.47 AUD
 */