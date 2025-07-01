import { ancillaryCharges } from '../config/config.js';
import { fxRates } from '../config/fxRates.js';

/**
 * Converts a given amount from a source currency to a target currency
 * using USD as the common base.
 * @param {number} amount The amount to convert.
 * @param {string} fromCurrency The starting currency code (e.g., 'PGK').
 * @param {string} toCurrency The target currency code (e.g., 'AUD').
 * @returns {number} The converted amount.
 */
function convertCurrency(amount, fromCurrency, toCurrency) {
  if (!fxRates[fromCurrency] || !fxRates[toCurrency]) {
    throw new Error(`Invalid currency code provided. Conversion from ${fromCurrency} to ${toCurrency} is not possible.`);
  }

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
  // Ensure all piece dimensions are numbers before calculation
  const totalWeight = pieces.reduce((sum, piece) => sum + Number(piece.weight || 0), 0);
  const totalVolume = pieces.reduce((sum, piece) => {
    const length = Number(piece.length || 0);
    const width = Number(piece.width || 0);
    const height = Number(piece.height || 0);
    return sum + (length * width * height) / 1000000; // Convert cm3 to m3
  }, 0);

  const volumetricWeight = totalVolume * 167; // IATA standard for air freight

  if (freightMode === 'lclSea') {
    // For LCL Sea Freight, 1 Revenue Ton (RT) = 1 cubic meter (CBM) or 1,000 kg, whichever is greater.
    // Since totalVolume is already in CBM, and totalWeight is in kg, we need to compare CBM with MT (metric tons).
    // 1 MT = 1000 kg. So, totalWeight / 1000 gives us metric tons.
    const totalMetricTons = totalWeight / 1000;
    return Math.max(totalVolume, totalMetricTons);
  } else {
    // For Domestic Air Freight and other modes, use the IATA standard
    return Math.max(totalWeight, volumetricWeight);
  }
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
export function generateQuote({ origin, destination, pieces, rateCurrency, targetCurrency, freightMode }, ratesData) {
  console.log('QuoteLogicEngine.js - received freightMode:', freightMode);
  const chargeableWeight = calculateChargeableWeight(pieces);
  const routeRateData = ratesData[origin]?.[destination];

  if (!routeRateData) {
    throw new Error(`No rate available for the selected route: ${origin} to ${destination}.`);
  }

  const lineItems = [];
  
  // The main freight cost calculation
  let baseFreightCost;
  let freightName;

  if (freightMode === 'domesticAir') {
    baseFreightCost = chargeableWeight * routeRateData.airRate; // Assuming airRate for domestic air
    freightName = 'Air Freight';
  } else if (freightMode === 'lclSea') {
    baseFreightCost = chargeableWeight * routeRateData.lclRate; // Assuming lclRate for LCL sea
    freightName = 'LCL Sea Freight';
  } else {
    throw new Error(`Unsupported freight mode: ${freightMode}`);
  }

  lineItems.push({
    name: freightName,
    cost: convertCurrency(baseFreightCost, rateCurrency, targetCurrency),
  });

  // Ancillary charges calculation
  // Store calculated ancillary costs temporarily to handle dependencies
  const calculatedAncillaryCosts = {};

  ancillaryCharges.forEach(charge => {
    let chargeCostPGK = 0; // All ancillary rates are in PGK as per current config

    if (charge.type === 'per_kg') {
      chargeCostPGK = chargeableWeight * charge.rate;
    } else if (charge.type === 'per_shipment') {
      chargeCostPGK = charge.rate;
    } else if (charge.type === 'Percentage_Of_PUD' && charge.dependsOn) {
      const dependedOnChargeConfig = ancillaryCharges.find(c => c.name === charge.dependsOn);
      if (dependedOnChargeConfig) {
        let dependedOnCostPGK = 0;
        if (dependedOnChargeConfig.type === 'per_kg') {
          dependedOnCostPGK = chargeableWeight * dependedOnChargeConfig.rate;
        } else if (dependedOnChargeConfig.type === 'per_shipment') {
          dependedOnCostPGK = dependedOnChargeConfig.rate;
        }
        if (!calculatedAncillaryCosts[charge.dependsOn]) {
            calculatedAncillaryCosts[charge.dependsOn] = dependedOnCostPGK;
        }
        chargeCostPGK = dependedOnCostPGK * charge.rate;
      }
    }

    // Apply minimum charge if defined
    if (charge.min && chargeCostPGK < charge.min) {
      chargeCostPGK = charge.min;
    }

    // Store the calculated cost in PGK before conversion for dependency lookup
    calculatedAncillaryCosts[charge.name] = chargeCostPGK;

    lineItems.push({
      name: charge.name,
      cost: convertCurrency(chargeCostPGK, 'PGK', targetCurrency), // Convert final cost to target currency
    });
  });

  const subTotal = lineItems.reduce((sum, item) => sum + item.cost, 0);
  const gst = subTotal * 0.10; // 10% GST
  const grandTotal = subTotal + gst;

  // The final quote object, now with currency details
  return {
    origin,
    destination,
    chargeableWeight: chargeableWeight,
    generatedAt: new Date().toLocaleString('en-AU'),
    lineItems,
    subTotal,
    gst,
    grandTotal,
    currency: targetCurrency,
    fxRateNote: rateCurrency === targetCurrency ? 'All charges in native currency.' : `Rates converted from ${rateCurrency} to ${targetCurrency} using USD as a base.`
  };
}