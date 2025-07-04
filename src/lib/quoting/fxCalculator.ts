/**
 * Calculates the foreign quote amount and adjusted FX rate.
 *
 * @param pgkTotal Total PGK amount after margin.
 * @param fxRate The base FX rate (TT Buy).
 * @param cafPercentage Currency Adjustment Factor percentage.
 * @param marginPercentage Margin percentage for FX.
 * @returns An object containing the quoteAmount and adjustedRate.
 */
export const calculateForeignQuote = (
  pgkTotal: number,
  fxRate: number,
  cafPercentage: number,
  marginPercentage: number
): { quoteAmount: number; adjustedRate: number } => {
  // Calculate the CAF amount
  const cafAmount = fxRate * (cafPercentage / 100);

  // Add CAF to the FX rate
  const rateWithCaf = fxRate + cafAmount;

  // Calculate the margin amount on the rate with CAF
  const marginAmount = rateWithCaf * (marginPercentage / 100);

  // Add margin to the rate with CAF to get the final adjusted rate
  const adjustedRate = rateWithCaf + marginAmount;

  // Calculate the quote amount in the foreign currency
  const quoteAmount = pgkTotal / adjustedRate;

  return {
    quoteAmount: parseFloat(quoteAmount.toFixed(2)),
    adjustedRate: parseFloat(adjustedRate.toFixed(4)),
  };
};
