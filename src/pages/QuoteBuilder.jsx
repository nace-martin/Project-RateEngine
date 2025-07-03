
import { useState, useEffect } from 'react';
import ShipmentDetails from '@/components/quoteBuilder/air/ShipmentDetails.jsx';
import QuoteOutput from '@/components/quoteBuilder/common/QuoteOutput.jsx';
import useQuoteBuilder from '../hooks/useQuoteBuilder.js'; // Corrected import
import { getCustomersFromDb } from '../services/database.js';
import ModeSelector from '@/components/quoteBuilder/common/ModeSelector.jsx';
import ServiceTypeSelector from '@/components/quoteBuilder/common/ServiceTypeSelector.jsx'; // Import new component
import CustomsClearanceBlock from '@/components/quoteBuilder/sea/CustomsClearanceBlock.jsx'; // Import CustomsClearanceBlock
import InlandTransportBlock from '@/components/quoteBuilder/transport/InlandTransportBlock.jsx'; // Import InlandTransportBlock
import { getAuth, onAuthStateChanged } from 'firebase/auth'; // Import Firebase Auth
import { app } from '../firebase/config.js'; // Assuming your Firebase app init is here
import { saveQuote } from '@/lib/firestore/quotes.ts'; // Import saveQuote

const auth = getAuth(app);

function QuoteBuilder() {
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [freightMode, setFreightMode] = useState('air-domestic'); // Default freight mode
  const [customersLoading, setCustomersLoading] = useState(true);
  const [currentUserEmail, setCurrentUserEmail] = useState(null);
  const [isSavingQuote, setIsSavingQuote] = useState(false); // To track save operation

  // Listen for auth state changes
  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        setCurrentUserEmail(user.email);
      } else {
        setCurrentUserEmail(null);
        // Handle user not logged in if necessary, e.g., disable save, redirect, etc.
        console.log("User is not logged in. Quotes will not be saved.");
      }
    });
    return () => unsubscribe(); // Cleanup subscription
  }, []);


  // Destructure serviceType and inlandTransportData from useQuoteBuilder
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
    totalGrossWeight, // Destructure totalGrossWeight
    serviceType, 
    inlandTransportData, // Destructure inlandTransportData
    customsClearanceData, // Destructure customsClearanceData
    setField, // Generic setter from useQuoteBuilder
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
    // We only trigger generateQuote here. Saving will be handled by a useEffect hook
    // that watches for changes in the 'quote' object from useQuoteBuilder.
    generateQuote();
  };

  // useEffect to save quote when it's generated and user is logged in
  useEffect(() => {
    // Ensure quote exists, is not currently being saved, and user is logged in
    if (quote && !isSavingQuote && currentUserEmail) {
      // Check if this quote has already been saved to prevent duplicates on re-renders
      // This simple check assumes quote objects don't get a unique ID until saved.
      // If your quote object from useQuoteBuilder might already have an ID or a timestamp 
      // that changes frequently, this condition might need adjustment.
      // A more robust check might involve comparing more fields or managing a 'lastSavedQuote' state.
      if (!quote.id) { // Assuming 'id' is added by Firestore, so a new quote won't have it.
        setIsSavingQuote(true);
        // Assuming 'quote' from useQuoteBuilder contains all necessary data for QuoteData interface
        // You might need to transform or pick specific fields from the 'quote' object
        // if its structure doesn't exactly match the QuoteData interface.
        const quoteDataForFirestore = {
          // Example: Assuming 'quote' has 'quoteText' and 'author'
          // quoteText: quote.fullText, 
          // author: quote.authorName,
          // ... and other fields that match your QuoteData interface in quotes.ts
          // For now, let's assume the entire 'quote' object (or relevant parts) is what we want to save.
          // Ensure that the 'quote' object's structure is compatible with 'QuoteData'.
          // This might involve spreading parts of it or mapping fields.
          // For simplicity, if 'quote' directly matches 'QuoteData' (excluding metadata):
          ...quote // Spread the generated quote details
        };

        // Remove fields that Firestore should generate or that are not part of the 'quotes' collection schema
        // For example, if 'quote' object from useQuoteBuilder contains 'generatedAt' client-side timestamp
        // or any other metadata that we are replacing/adding (like 'id', 'createdAt', 'createdBy', 'status')
        delete quoteDataForFirestore.id; // Ensure no client-side ID conflicts with Firestore's generated ID
        delete quoteDataForFirestore.generatedAt; // We'll use serverTimestamp for createdAt

        saveQuote(quoteDataForFirestore, currentUserEmail)
          .then((docId) => {
            alert(`Quote saved! ID: ${docId}`);
            // Optionally, you could update the local quote state with the new ID
            // if useQuoteBuilder is designed to handle it, e.g., by calling setField('id', docId)
            // This would also help the !quote.id check above.
          })
          .catch((err) => {
            // Error is already logged by saveQuote, just show alert
            alert('Failed to save quote. See console for details.');
          })
          .finally(() => {
            setIsSavingQuote(false);
          });
      }
    }
  }, [quote, currentUserEmail, isSavingQuote]); // Dependencies for the effect


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
          // Pass the current data to the component if it needs to display it, though it manages its own form state internally
          // customsData={customsClearanceData} 
          onChange={(newData) => setField('customsClearanceData', newData)}
          locations={locations} 
        />
      )}

      {/* Inland Transport specific fields */}
      {serviceType === 'inlandTransport' && (
        <InlandTransportBlock
          // Pass the current data to the component if it needs to display it, though it manages its own form state internally
          // inlandData={inlandTransportData} 
          onChange={(newData) => setField('inlandTransportData', newData)} 
          locations={locations} 
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