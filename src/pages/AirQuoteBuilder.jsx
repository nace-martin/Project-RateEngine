import React from 'react'; // No longer need useState here
import useQuoteBuilder from '../hooks/useQuoteBuilder';
import ServiceTypeSelector from '../components/ServiceTypeSelector';
import ModeSelector from '../components/ModeSelector';
import ShipmentDetails from '../components/ShipmentDetails';

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
  } = useQuoteBuilder();

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
        displayCBM={0} // Placeholder, will be calculated based on pieces
        displayRT={0}  // Placeholder, will be calculated based on pieces
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
        {/* Placeholder content */}
      </section>
    </main>
  );
};

export default AirQuoteBuilder;
