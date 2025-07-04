import React, { useState } from 'react';
import useQuoteBuilder from '@/hooks/useQuoteBuilder';
import { saveQuote } from '@/lib/firestore/quotes';
import ServiceTypeSelector from '@/components/quoteBuilder/common/ServiceTypeSelector';
import ModeSelector from '@/components/quoteBuilder/common/ModeSelector';
import ShipmentDetails from '@/components/quoteBuilder/air/ShipmentDetails';
import QuoteSummaryCard from '@/components/quoteBuilder/common/QuoteSummaryCard';
import useFirebaseUser from '@/hooks/useFirebaseUser';
import { calculateForeignQuote } from '@/lib/quoting/fxCalculator';

const AirQuoteBuilder = () => {
  const firebaseUser = useFirebaseUser();
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

  // Placeholder for PGK Total Cost calculation
  // TODO: Replace with actual PGK total cost calculation logic
  const PGK_RATE_PER_RT = 10; // Example rate
  const pgkTotal = displayRT * PGK_RATE_PER_RT; // This is a simplified placeholder

  // FX Calculation
  // TODO: Obtain billingLocation to conditionally run this logic.
  // For now, assuming it should run if pgkTotal is available.
  let fxQuoteData = null;
  if (pgkTotal > 0) { // Basic check, will be replaced/augmented by billingLocation check
    // const userBillingLocation = firebaseUser?.billingLocation || 'PNG'; // Example, once firebaseUser has this
    const userBillingLocation = 'AUS'; // Hardcoded for now, assuming overseas for testing

    if (userBillingLocation !== 'PNG') {
      const { quoteAmount, adjustedRate } = calculateForeignQuote(
        pgkTotal,     // Total PGK after margin (using placeholder pgkTotal for now)
        0.2499,       // FX Rate (TT Buy) - example value
        3,            // CAF % (Currency Adjustment Factor) - example value
        10            // Margin % - example value
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
