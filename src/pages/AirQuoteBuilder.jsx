import React, { useState } from 'react';
import useQuoteBuilder from '@/hooks/useQuoteBuilder';
import { saveQuote } from '@/lib/firestore/quotes';
import ServiceTypeSelector from '@/components/quoteBuilder/common/ServiceTypeSelector';
import ModeSelector from '@/components/quoteBuilder/common/ModeSelector';
import ShipmentDetails from '@/components/quoteBuilder/air/ShipmentDetails';
import QuoteSummaryCard from '@/components/quoteBuilder/common/QuoteSummaryCard';
import useFirebaseUser from '@/hooks/useFirebaseUser';
import { calculateForeignQuote } from '@/lib/quoting/fxCalculator';
import { ancillaryCharges as allAncillaryCharges } from '@/config/config';
import { fxParameters } from '@/config/fxConfig'; // Import FX parameters

// Define constants for international air freight rate and margin
// TODO: These should ideally come from a more dynamic config or rate engine
const INTERNATIONAL_AIR_FREIGHT_RATE_PER_RT = 50; // PGK per RT, placeholder
const DANGEROUS_GOODS_SURCHARGE_PER_SHIPMENT = 150; // PGK, placeholder
const MARGIN_PERCENTAGE = 15; // 15% margin

const AirQuoteBuilder = () => {
  const { user: firebaseUser, loading: userLoading, error: userError } = useFirebaseUser(); // Destructure user, loading, error
  const {
    serviceType,
    handleServiceTypeChange,
    mode,
    handleModeChange,
    pieces,
    setPieces,
    incoterm,
    handleIncotermChange,
    warehouseCutoffDate,
    handleWarehouseCutoffDateChange,
    origin,
    destination,
    displayRT,
    displayCBM,
  } = useQuoteBuilder();

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState(null);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);

  const [isDangerousGoods, setIsDangerousGoods] = useState(false);
  const [notes, setNotes] = useState('');

  // --- Start PGK Total Cost Calculation ---
  let subTotalBeforeMargin = 0;

  if (mode === 'air-international' && displayRT > 0) {
    // 1. Base Freight Cost (Placeholder for international air freight)
    const baseFreightCost = displayRT * INTERNATIONAL_AIR_FREIGHT_RATE_PER_RT;
    subTotalBeforeMargin += baseFreightCost;

    // 2. Ancillary Charges from config.js
    // Filter ancillary charges applicable to air-international or all modes.
    // For now, assume all charges in config.js might apply if not mode-specific.
    // This might need refinement if ancillaryCharges have mode applicability.
    const ancillaryChargesToApply = allAncillaryCharges; // Or filter them: allAncillaryCharges.filter(c => !c.mode || c.mode === 'air-international');

    const calculatedAncillaryCosts = {}; // For dependent charges

    ancillaryChargesToApply.forEach(charge => {
      let chargeCostPGK = 0;
      if (charge.type === 'per_kg') {
        chargeCostPGK = displayRT * charge.rate;
      } else if (charge.type === 'per_shipment') {
        chargeCostPGK = charge.rate;
      } else if (charge.type === 'Percentage_Of_PUD' && charge.dependsOn) {
        // Assuming PUD Fee is the only one with 'Percentage_Of_PUD' type for now
        // This logic is simplified from QuoteLogicEngine.js for direct use here
        const dependedOnChargeConfig = ancillaryChargesToApply.find(c => c.name === charge.dependsOn);
        if (dependedOnChargeConfig) {
          let dependedOnCostPGK = calculatedAncillaryCosts[charge.dependsOn];
          if (dependedOnCostPGK === undefined) { // Calculate if not already done (e.g. PUD Fee)
            if (dependedOnChargeConfig.type === 'per_kg') {
              dependedOnCostPGK = displayRT * dependedOnChargeConfig.rate;
            } else if (dependedOnChargeConfig.type === 'per_shipment') {
              dependedOnCostPGK = dependedOnChargeConfig.rate;
            }
             // Apply min for the depended-on charge before calculating percentage
            if (dependedOnChargeConfig.min && dependedOnCostPGK < dependedOnChargeConfig.min) {
                dependedOnCostPGK = dependedOnChargeConfig.min;
            }
            calculatedAncillaryCosts[charge.dependsOn] = dependedOnCostPGK; // Store it
          }
          chargeCostPGK = dependedOnCostPGK * charge.rate; // Rate is percentage e.g. 0.10 for 10%
        }
      }

      if (charge.min && chargeCostPGK < charge.min && charge.type !== 'Percentage_Of_PUD') { // Min for percentage based is on the parent
        chargeCostPGK = charge.min;
      }

      // Store for potential dependencies and add to subtotal
      if (charge.type !== 'Percentage_Of_PUD' || !calculatedAncillaryCosts[charge.name]) { // Add if not already part of a calculation (like PUD fee for PUD fuel)
         calculatedAncillaryCosts[charge.name] = chargeCostPGK;
      }
      subTotalBeforeMargin += chargeCostPGK;
    });

    // 3. Dangerous Goods Surcharge (if applicable)
    // TODO: Add DG Surcharge to ancillaryCharges in config.js for better management
    if (isDangerousGoods) {
      subTotalBeforeMargin += DANGEROUS_GOODS_SURCHARGE_PER_SHIPMENT;
    }
  }

  // 4. Apply Margin
  const pgkTotal = subTotalBeforeMargin * (1 + MARGIN_PERCENTAGE / 100);
  // --- End PGK Total Cost Calculation ---

  // FX Calculation
  // TODO: Obtain billingLocation to conditionally run this logic. For now, using hardcoded 'AUS'.
  // For now, assuming it should run if pgkTotal is available.
  let fxQuoteData = null;
  // Ensure firebaseUser and clientData are loaded before attempting to access billingLocation
  if (pgkTotal > 0 && firebaseUser && firebaseUser.clientData) {
    const userBillingLocation = firebaseUser.clientData.billingLocation || 'PNG'; // Default to 'PNG' if not set

    if (userBillingLocation !== 'PNG') {
      const { quoteAmount, adjustedRate } = calculateForeignQuote(
        pgkTotal,     // Total PGK after margin
        fxParameters.DEFAULT_FX_RATE,
        fxParameters.DEFAULT_CAF_PERCENTAGE,
        fxParameters.DEFAULT_FX_MARGIN_PERCENTAGE
      );
      fxQuoteData = { quoteAmount, adjustedRate };
    }
  }

  const handleSaveQuote = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError(null);

    const quoteData = {
      origin,
      destination,
      chargeableWeight: displayRT,
      pieces,
      freightMode: mode,
      incoterm,
      warehouseCutoffDate,
      lineItems: [],
      subTotal: 0,
      gst: 0,
      grandTotal: 0,
    };

    try {
      const quoteId = await saveQuote(quoteData);
      setSaveSuccess(true);
      console.log('Quote saved with ID:', quoteId);
    } catch (error) {
      console.error('Error saving quote:', error);
      setSaveError(error.message);
    } finally {
      setSaving(false);
    }
  };

  const handleDownloadPdf = async () => {
    setIsDownloadingPdf(true);

    const quoteDataForPdf = {
      quoteId: `QTE-${Date.now()}`,
      quoteDate: new Date().toISOString().split('T')[0],
      customerName: 'Global Corp Inc.', // Placeholder, replace with actual customer data
      origin: origin || 'N/A',
      destination: destination || 'N/A',
      incoterm: incoterm || 'N/A',
      transportMode: mode || 'N/A',
      isDangerousGoods: isDangerousGoods ? 'Yes' : 'No',
      chargeableWeight: displayRT ? `${displayRT} RT` : 'N/A',
      piecesSummary: pieces.length > 0 ? `${pieces.length} pcs / ...` : 'No pieces', // Needs more detailed summary
      totalAmount: 'USD 0.00', // Placeholder, replace with actual total
      createdBy: firebaseUser?.email || 'N/A',
      notes: notes || ''
    };

    try {
      const response = await fetch('https://australia-southeast1-long-justice-454003-b0.cloudfunctions.net/generateQuotePdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(quoteDataForPdf),
      });

      if (!response.ok) {
        throw new Error('Failed to generate PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `quote-${quoteDataForPdf.quoteId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();

    } catch (err) {
      console.error('Error downloading PDF:', err);
      alert('Failed to download PDF. See console for details.');
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  return (
    <main className="p-4 space-y-6 max-w-4xl mx-auto">
      <ServiceTypeSelector
        selectedServiceType={serviceType}
        onServiceTypeChange={(value) => handleServiceTypeChange({ target: { value } })}
      />
      <ModeSelector
        selectedMode={mode}
        onModeChange={(value) => handleModeChange({ target: { value } })}
      />
      <ShipmentDetails
        pieces={pieces}
        setPieces={setPieces}
        freightMode={mode}
        incoterm={incoterm}
        onIncotermChange={handleIncotermChange}
        warehouseCutoffDate={warehouseCutoffDate}
        onWarehouseCutoffDateChange={handleWarehouseCutoffDateChange}
        displayCBM={displayCBM}
        displayRT={displayRT}
      />

      <section>
        <h2>Quote Summary</h2>
        {origin && destination && pieces && pieces.length > 0 && (
          <QuoteSummaryCard
            quoteData={{
              pieces,
              totalChargeableWeight: displayRT,
              origin,
              destination,
              incoterm,
              isDangerousGoods, 
              notes, 
              createdBy: firebaseUser?.email || 'N/A',
              transportMode: mode,
              fxQuoteData, // Pass FX data to the summary card
            }}
            onSaveQuote={handleSaveQuote}
            saving={saving}
            saveSuccess={saveSuccess}
            saveError={saveError}
            onDownloadPdf={handleDownloadPdf}
            isDownloadingPdf={isDownloadingPdf}
          />
        )}
        {!(origin && destination && pieces && pieces.length > 0) && (
          <p className="text-gray-500 italic">
            Please fill in Origin, Destination, and at least one Piece to see the quote summary.
          </p>
        )}
      </section>
    </main>
  );
};

export default AirQuoteBuilder;
