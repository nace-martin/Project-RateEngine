import React, { useState } from 'react';
import useQuoteBuilder from '../hooks/useQuoteBuilder';
import { saveQuote } from '../../lib/firestore/quotes';
import ServiceTypeSelector from '../components/quoteBuilder/common/ServiceTypeSelector';
import ModeSelector from '@/components/quoteBuilder/common/ModeSelector';
import ShipmentDetails from '@/components/quoteBuilder/air/ShipmentDetails';

const AirQuoteBuilder = () => {
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
    origin, // Added origin
    destination, // Added destination
    displayRT, // Added displayRT for chargeableWeight
    displayCBM, // Added displayCBM
  } = useQuoteBuilder();

  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [saveError, setSaveError] = useState(null);

  const handleSaveQuote = async () => {
    setSaving(true);
    setSaveSuccess(false);
    setSaveError(null);

    // Access values from useQuoteBuilder hook
    // const {
    //   origin, // Not directly available in AirQuoteBuilder, need to get from useQuoteBuilder
    //   destination, // Not directly available in AirQuoteBuilder, need to get from useQuoteBuilder
    //   chargeableWeightRT, // Available as displayRT from useQuoteBuilder
    //   pieces,
    //   mode, // Available as mode from useQuoteBuilder (maps to freightMode)
    //   incoterm,
    //   warehouseCutoffDate,
    // } = useQuoteBuilder(); // This is incorrect, need to access them from the hook's return values

    const quoteData = {
      origin,
      destination,
      chargeableWeight: displayRT,
      pieces,
      freightMode: mode,
      incoterm,
      warehouseCutoffDate,
      // Placeholder for fields not yet available
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

  // Note: The onServiceTypeChange and onModeChange props for the selectors
  // expect a direct value, while the hook's handlers expect an event-like object.
  // This adaptation is kept here.
  // ShipmentDetails' onIncotermChange and onWarehouseCutoffDateChange props
  // pass the value directly, which is compatible with the updated hook handlers.

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
        onIncotermChange={handleIncotermChange} // Directly use handler from hook
        warehouseCutoffDate={warehouseCutoffDate}
        onWarehouseCutoffDateChange={handleWarehouseCutoffDateChange} // Directly use handler from hook
        displayCBM={displayCBM}
        displayRT={displayRT}
      />

      {/* Original placeholder sections can be reviewed for removal or integration */}
      <section>
        <h2>Direction & Route Info</h2>
        {/* ServiceTypeSelector and ModeSelector are part of this */}
      </section>
      <section>
        <h2>Cargo Details</h2>
        {/* ShipmentDetails is part of this */}
      </section>
      <section>
        <h2>Dimensions & Chargeable Weight</h2>
        {/* Placeholder content */}
      </section>
      <section>
        <h2>Payer & Currency</h2>
        {/* Placeholder content */}
      </section>
      <section>
        <h2>Rate Lookup</h2>
        {/* Placeholder content */}
      </section>
      <section>
        <h2>Cost Breakdown</h2>
        {/* Placeholder content */}
      </section>
      <section>
        <h2>Quote Summary</h2>
        {/* Placeholder content */}
      </section>
      <section>
        <h2>Action Buttons</h2>
        <button
          onClick={handleSaveQuote}
          disabled={saving}
          className="bg-blue-500 hover:bg-blue-700 text-white font-bold py-2 px-4 rounded focus:outline-none focus:shadow-outline disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Quote'}
        </button>
        {saveSuccess && (
          <p className="text-green-500 mt-2">Quote saved successfully!</p>
        )}
        {saveError && (
          <p className="text-red-500 mt-2">Error: {saveError}</p>
        )}
      </section>
    </main>
  );
};

export default AirQuoteBuilder;
