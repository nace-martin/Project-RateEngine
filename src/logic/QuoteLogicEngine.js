import { ancillaryCharges } from '../config/config.js';

// Updated to accept freightMode
function calculateChargeableWeight(pieces, freightMode) {
  // Ensure all piece dimensions are numbers before calculation
  const totalWeight = pieces.reduce((sum, piece) => sum + Number(piece.weight || 0), 0);
  const totalVolume = pieces.reduce((sum, piece) => {
    const length = Number(piece.length || 0);
    const width = Number(piece.width || 0);
    const height = Number(piece.height || 0);
    return sum + (length * width * height) / 1000000; // Convert cm3 to m3
  }, 0);

  // For LCL Sea Freight, 1 Revenue Ton (RT) = 1 cubic meter (CBM) or 1,000 kg, whichever is greater.
  // This logic is specific to LCL and will be used when freightMode is 'sea-lcl'.
  if (freightMode === 'sea-lcl') {
    const totalMetricTons = totalWeight / 1000; // Convert kg to metric tons
    // RT = max(CBM, MT)
    return Math.max(totalVolume, totalMetricTons);
  }
  
  // For Air Freight (Domestic and International), use IATA volumetric weight.
  // Other modes might have different calculations in the future.
  if (freightMode === 'air-domestic' || freightMode === 'air-international') {
    const volumetricWeight = totalVolume * 167; // IATA standard volumetric factor for air freight (kg per CBM)
    return Math.max(totalWeight, volumetricWeight);
  }

  // Default or other modes (e.g., 'sea-fcl', 'inland-domestic') might not use this function
  // or have their specific chargeable quantity calculated differently.
  // For now, return total weight if mode is not explicitly handled for volumetric calculation.
  // This part may need refinement as other modes are implemented.
  // console.warn(`Chargeable weight calculation not fully defined for mode: ${freightMode}. Defaulting to actual weight.`);
  return totalWeight; // Fallback for modes not explicitly handled by volumetric calculations here.
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
export function generateQuote({ origin, destination, pieces, freightMode }, ratesData) {
  console.log('QuoteLogicEngine.js - received freightMode:', freightMode);
  // Pass freightMode to calculateChargeableWeight
  const chargeableWeight = calculateChargeableWeight(pieces, freightMode);
  const routeRateData = ratesData[origin]?.[destination];

  if (!routeRateData) {
    throw new Error(`No rate available for the selected route: ${origin} to ${destination}.`);
  }

  const lineItems = [];
  
  // The main freight cost calculation
  let baseFreightCost;
  let freightName;

  // Updated conditions for new freight modes
  if (freightMode === 'air-domestic') {
    if (!routeRateData.airRate) throw new Error(`Air rate not available for ${origin}-${destination}.`);
    baseFreightCost = chargeableWeight * routeRateData.airRate;
    freightName = 'Domestic Air Freight';
  } else if (freightMode === 'sea-lcl') {
    // LCL rating logic will be fully fleshed out in its own step.
    // For now, ensure it doesn't crash if lclRate isn't present or if chargeableWeight is RT.
    // This part will need careful review when implementing LCL rating.
    if (!routeRateData.lclRate) throw new Error(`LCL rate not available for ${origin}-${destination}.`);
    // Assuming lclRate is per RT. Chargeable weight for LCL is already RT.
    baseFreightCost = chargeableWeight * routeRateData.lclRate; 
    freightName = 'LCL Sea Freight';
  } else if (freightMode === 'air-international' || freightMode === 'sea-fcl' || freightMode === 'inland-domestic') {
    // Placeholder: Rating logic for these modes is not yet implemented.
    // In a real scenario, these would have their own rate lookups and calculations.
    // For now, to prevent crashes and indicate WIP:
    // Option 1: Throw error (as it was)
    // throw new Error(`Rating for freight mode '${freightMode}' is not yet implemented.`);
    // Option 2: Return a zero-cost item or specific message (less disruptive for UI testing)
    baseFreightCost = 0; // Or some indicator value
    freightName = `${freightMode.replace('-', ' ')} (Rating Not Implemented)`;
    // To avoid breaking ancillary calculations, we push a zero item.
    // Consider if ancillary charges should apply if base freight isn't rated.
  } else {
    throw new Error(`Unsupported freight mode: ${freightMode}`);
  }

  lineItems.push({
    name: freightName,
    cost: baseFreightCost,
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
      cost: chargeCostPGK, // Cost is already in PGK, no conversion needed for MVP
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
  };
}