
import { useState, useEffect } from 'react';
import ShipmentDetails from '../components/ShipmentDetails.jsx';
import QuoteOutput from '../components/QuoteOutput.jsx';
import { useQuoteBuilder } from '../hooks/useQuoteBuilder';
import { getCustomersFromDb } from '../services/database.js';
import ModeSelector from '../components/ModeSelector.jsx';
import ServiceTypeSelector from '../components/ServiceTypeSelector.jsx'; // Import new component
import CustomsClearanceBlock from '../components/CustomsClearanceBlock.jsx'; // Import CustomsClearanceBlock

function QuoteBuilder() {
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [freightMode, setFreightMode] = useState('air-domestic'); // Default freight mode
  const [customersLoading, setCustomersLoading] = useState(true);
  const [customsClearanceData, setCustomsClearanceData] = useState({
    direction: 'import',
    mode: 'air',
    originCountry: '',
    destinationPort: '',
    hsCodes: '',
    invoiceLines: '',
    naqiaOrExemption: false,
  });

  // Destructure serviceType from useQuoteBuilder (already done in a previous step, ensuring it's here)
  const {
    origin,
    destination,
    quote,
    error,
    loading,
    locations,
    pieces,
    incoterm,
    warehouseCutoffDate,
    displayCBM,
    displayRT,
    serviceType, // Make sure serviceType is destructured
    setField,
    generateQuote,
    clearError,
    setPieces,
    resetQuote,
  } = useQuoteBuilder(selectedCustomer?.billingCurrency, freightMode);


  useEffect(() => {
    // Effect to handle freightMode changes when serviceType changes
    if (serviceType === 'airFreight') {
      setFreightMode('air-domestic');
    } else if (serviceType === 'seaFreight') {
      setFreightMode('sea-lcl'); // Default for Sea Freight
    } else {
      // For other service types like 'customsClearance', freightMode might be irrelevant for ModeSelector
      // Setting it back to a general default or null.
      // For now, let's reset to air-domestic to ensure a valid state if user switches back.
      setFreightMode('air-domestic');
    }
  }, [serviceType]); // Re-run when serviceType changes

  useEffect(() => {
    const fetchCustomers = async () => {
      // Assuming a default userId for now. In a real app, this would come from auth.
      const fetchedCustomers = await getCustomersFromDb('user123');
      setCustomers(fetchedCustomers);
      if (fetchedCustomers.length > 0) {
        setSelectedCustomer(fetchedCustomers[0]);
      }
      setCustomersLoading(false);
    };

    fetchCustomers();
  }, []);
  

  const handleGenerateQuote = () => {
    clearError();
    generateQuote();
  };

  const handleResetQuote = () => {
    resetQuote();
    if (customers.length > 0) {
      setSelectedCustomer(customers[0]);
    }
  };

  const handleCustomerChange = (e) => {
    const customer = customers.find((c) => c.id === e.target.value);
    setSelectedCustomer(customer);
  };

  if (loading || customersLoading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="p-5 bg-white flex flex-col gap-5">
      <h1 className="text-3xl font-bold text-center text-blue-600 mb-5">Project RateEngine</h1>

      {error && (
        <div className="bg-red-500 text-white p-3 rounded-lg mb-5 flex items-center gap-2">
          <span className="text-lg">❌</span>
          <span className="flex-grow">{error}</span>
          <button onClick={clearError} aria-label="Clear error" className="bg-transparent border-none text-white text-lg cursor-pointer p-1 hover:bg-red-600 rounded">X</button>
        </div>
      )}

      {/* Service Type Selector will go here, above Customer */}
      <ServiceTypeSelector
        selectedServiceType={serviceType}
        onServiceTypeChange={(value) => setField('serviceType', value)}
      />

      <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
        <h2 className="text-xl font-bold text-blue-600 mb-4 border-b border-gray-200 pb-2">Customer</h2>
        <div className="mb-4">
          <label htmlFor="customer" className="block mb-2 font-bold text-gray-800">Customer</label>
          <select
            id="customer"
            name="customer"
            value={selectedCustomer?.id || ''}
            onChange={handleCustomerChange}
            className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            disabled={customersLoading}
          >
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name} ({customer.billingCurrency})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Conditional rendering for ModeSelector, Routing, and ShipmentDetails */}
      {(serviceType === 'airFreight' || serviceType === 'seaFreight') && (
        <>
          <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
            <h2 className="text-xl font-bold text-blue-600 mb-4">Transport Mode</h2>
            <ModeSelector selectedMode={freightMode} onModeChange={setFreightMode} />
          </div>

          <div className="bg-white p-6 rounded-2xl border border-gray-200 shadow-md text-gray-800">
            <h2 className="text-xl font-bold text-blue-600 mb-4 border-b border-gray-200 pb-2">Routing</h2>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="mb-4">
            <label htmlFor="origin" className="block mb-2 font-bold text-gray-800">Origin</label>
            <select
              id="origin"
              name="origin"
              value={origin}
              onChange={(e) => setField('origin', e.target.value)}
              disabled={!locations.length}
              className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
          <div className="mb-4">
            <label htmlFor="destination" className="block mb-2 font-bold text-gray-800">Destination</label>
            <select
              id="destination"
              name="destination"
              value={destination}
              onChange={(e) => setField('destination', e.target.value)}
              disabled={!locations.length}
              className="w-full p-2 border border-gray-300 rounded-md bg-gray-100 text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

          {/* ShipmentDetails is also part of this conditional block */}
          {/* The inner condition for ShipmentDetails based on freightMode still applies */}
          {(freightMode === 'air-domestic' || freightMode === 'air-international' || freightMode === 'sea-lcl') && (
            <ShipmentDetails
              pieces={pieces}
              setPieces={setPieces}
              freightMode={freightMode}
              incoterm={incoterm}
              onIncotermChange={(value) => setField('incoterm', value)}
              warehouseCutoffDate={warehouseCutoffDate}
              onWarehouseCutoffDateChange={(value) => setField('warehouseCutoffDate', value)}
              displayCBM={displayCBM}
              displayRT={displayRT}
            />
          )}
        </>
      )}

      {/* Customs Clearance specific fields */}
      {serviceType === 'customsClearance' && (
        <CustomsClearanceBlock
          onChange={setCustomsClearanceData}
          locations={locations} // Pass locations to CustomsClearanceBlock
        />
      )}

      <div className="flex justify-center gap-4 mt-5">
        <button
          type="button"
          className="bg-blue-600 text-white font-bold py-3 px-6 rounded-xl hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
          onClick={handleGenerateQuote}
          disabled={!origin || !destination}
        >
          Generate Quote
        </button>
        <button
          type="button"
          className="bg-orange-500 text-white font-bold py-3 px-6 rounded-xl hover:bg-orange-600"
          onClick={handleResetQuote}
        >
          Reset
        </button>
      </div>

      <QuoteOutput quote={quote} />
    </div>
  );
}

export default QuoteBuilder;