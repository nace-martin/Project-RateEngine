/**
 * Calculates total gross weight, total volume, and chargeable weight (Revenue Ton).
 *
 * @param {Array<Object>} pieces - An array of piece objects.
 * Each piece object should have:
 *  - weight: Number (in kilograms, kg)
 *  - length: Number (in centimeters, cm)
 *  - width: Number (in centimeters, cm)
 *  - height: Number (in centimeters, cm)
 * @returns {Object} An object containing:
 *  - totalGrossWeight: Number (total weight of all pieces in kg)
 *  - totalVolumeCBM: Number (total volume of all pieces in cubic meters, CBM)
 *  - chargeableWeightRT: Number (Revenue Ton, RT)
 */
export const calculateChargeableWeight = (pieces) => {
  let totalGrossWeight = 0;
  let totalVolumeCBM = 0;

  if (!pieces || pieces.length === 0) {
    return {
      totalGrossWeight: 0,
      totalVolumeCBM: 0,
      chargeableWeightRT: 0,
    };
  }

  pieces.forEach(piece => {
    const weightKg = parseFloat(piece.weight) || 0;
    const lengthCm = parseFloat(piece.length) || 0;
    const widthCm = parseFloat(piece.width) || 0;
    const heightCm = parseFloat(piece.height) || 0;

    totalGrossWeight += weightKg;

    // Calculate volume of one piece in cubic meters (CBM)
    // Formula: (Length cm * Width cm * Height cm) / 1,000,000 = Volume m³
    const pieceVolumeCBM = (lengthCm * widthCm * heightCm) / 1000000;
    totalVolumeCBM += pieceVolumeCBM;
  });

  // Calculate total weight in metric tons (MT)
  // Formula: Total Gross Weight kg / 1000 = Weight MT
  const totalWeightMT = totalGrossWeight / 1000;

  // Determine Chargeable Weight (Revenue Ton - RT)
  // RT is the greater of the total volume in CBM or the total weight in MT.
  // This is a standard freight industry calculation.
  // For air freight, a different volumetric factor (e.g., 1 CBM = 167 kg, or 1:6000) is often used,
  // but the request specifies RT = max(MT, CBM) which is typical for sea freight LCL.
  // This function provides the basic CBM and MT, allowing downstream logic to apply specific air freight rules if needed.
  // For the purpose of this helper, we will stick to the max(MT, CBM) definition.
  const chargeableWeightRT = Math.max(totalWeightMT, totalVolumeCBM);

  return {
    totalGrossWeight, // in kg
    totalVolumeCBM,   // in m³
    chargeableWeightRT, // RT
  };
};
