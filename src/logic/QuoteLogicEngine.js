import { ancillaryCharges } from '../config/config.js';
import { baseCurrency, fxRates } from '../config/fxRates.js';

/**
 * Converts a given amount from a source currency to a target currency
 * using USD as the common base.
 * @param {number} amount The amount to convert.
 * @param {string} fromCurrency The starting currency code (e.g., 'PGK').
 * @param {string} toCurrency The target currency code (e.g., 'AUD').
 * @returns {number} The converted amount.
 */
function convertCurrency(amount, fromCurrency, toCurrency) {
  // If currencies are the same, no conversion needed
  if (fromCurrency === toCurrency) {
    return amount;
  }

  // Step 1: Convert the initial amount to the base currency (USD)
  const amountInBase = amount / fxRates[fromCurrency];

  // Step 2: Convert the USD amount to the target currency
  const finalAmount = amountInBase * fxRates[toCurrency];

  return finalAmount;
}


function calculateChargeableWeight(pieces) {
  // ... this function remains unchanged ...
  const totalWeight = pieces.reduce((sum, piece) => sum + piece.weight, 0);
  const totalVolume = pieces.reduce((sum, piece) => sum + (piece.length * piece.width * piece.height) / 1000000, 0);
  const volumetricWeight = totalVolume * 167;
  return Math.max(totalWeight, volumetricWeight);
}

/**
 * Main function to generate a freight quote.
 * @param {object} quoteInputs - The user's input from the form.
 * @param {string} quoteInputs.origin - The origin code.
 * @param {string} quoteInputs.destination - The destination code.
 * @param {Array} quoteInputs.pieces - Array of shipment pieces.
 * @param {string} quoteInputs.rateCurrency - The currency of the stored freight rate (e.g., 'PGK' for domestic).
 * @param {string} quoteInputs.targetCurrency - The final currency for the quote display (e.g., 'AUD').
 * @param {object} ratesData - The rate data object.
 * @returns {object} A quote object with all calculated details.
 */
export function generateQuote({ origin, destination, pieces, rateCurrency, targetCurrency }, ratesData) {
  const chargeableWeight = calculateChargeableWeight(pieces);
  const routeRateData = ratesData[origin]?.[destination];

  if (!routeRateData) {
    throw new Error(`No rate available for the selected route: ${origin} to ${destination}.`);
  }

  const lineItems = [];
  
  // The main freight cost calculation
  const baseFreightCost = chargeableWeight * routeRateData.rate; // This cost is in the 'rateCurrency' (e.g., PGK)

  lineItems.push({
    name: 'Air Freight',
    // Convert the base freight cost from its native currency to the final target currency
    cost: convertCurrency(baseFreightCost, rateCurrency, targetCurrency),
  });

  // Ancillary charges calculation
  ancillaryCharges.forEach(charge => {
    let chargeCost = 0;
    if (charge.type === 'per_kg') {
      chargeCost = chargeableWeight * charge.rate;
    } else if (charge.type === 'per_shipment') {
      chargeCost = charge.rate;
    }

    // Ancillary charges are usually in the local currency (PGK), so we convert from PGK
    lineItems.push({
      name: charge.name,
      cost: convertCurrency(chargeCost, 'PGK', targetCurrency),
    });
  });

  const subtotal = lineItems.reduce((sum, item) => sum + item.cost, 0);
  const gst = subtotal * 0.10; // 10% GST
  const grandTotal = subtotal + gst;

  // The final quote object, now with currency details
  return {
    origin,
    destination,
    chargeableWeight: chargeableWeight,
    generatedAt: new Date().toLocaleString('en-AU'),
    lineItems,
    subtotal: subtotal,
    gst: gst,
    grandTotal: grandTotal,
    currency: targetCurrency, // Add the final currency to the quote object
    fxRateNote: `Rates converted to ${targetCurrency} using USD as a base.`
  };
}