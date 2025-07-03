
import { useState, useEffect } from 'react';
import ShipmentDetails from '@/components/quoteBuilder/air/ShipmentDetails.jsx';
import QuoteOutput from '@/components/quoteBuilder/common/QuoteOutput.jsx';
import useQuoteBuilder from '../hooks/useQuoteBuilder.js';
import { getCustomersFromDb } from '../services/database.js';
import ModeSelector from '@/components/quoteBuilder/common/ModeSelector.jsx';
import ServiceTypeSelector from '@/components/quoteBuilder/common/ServiceTypeSelector.jsx';
import CustomsClearanceBlock from '@/components/quoteBuilder/sea/CustomsClearanceBlock.jsx';
import InlandTransportBlock from '@/components/quoteBuilder/transport/InlandTransportBlock.jsx';
import { getAuth, onAuthStateChanged } from 'firebase/auth';
import { app } from '../firebase/config.js';
import { saveQuote } from '@/lib/firestore/quotes.ts';

const auth = getAuth(app);

function QuoteBuilder() {
  const [customers, setCustomers] = useState([]);
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [freightMode, setFreightMode] = useState('air-domestic');
  const [customersLoading, setCustomersLoading] = useState(true);
  const [currentUserEmail, setCurrentUserEmail] = useState(null);
  const [isSavingQuote, setIsSavingQuote] = useState(false);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        setCurrentUserEmail(user.email);
      } else {
        setCurrentUserEmail(null);
        console.log("User is not logged in. Quotes will not be saved.");
      }
    });
    return () => unsubscribe();
  }, []);

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
    totalGrossWeight,
    serviceType, 
    inlandTransportData,
    customsClearanceData,
    setField,
    generateQuote,
    clearError,
    setPieces,
    resetQuote,
  } = useQuoteBuilder(selectedCustomer?.billingCurrency, freightMode);

  useEffect(() => {
    if (serviceType === 'airFreight') {
      setFreightMode('air-domestic');
    } else if (serviceType === 'seaFreight') {
      setFreightMode('sea-lcl');
    } else {
      setFreightMode('air-domestic');
    }
  }, [serviceType]);

  useEffect(() => {
    const fetchCustomers = async () => {
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

  const handleDownloadPdf = async () => {
    if (!quote) {
      alert("Please generate a quote first.");
      return;
    }

    setIsDownloadingPdf(true);

    const pdfPayload = {
      quoteId: quote.quoteId || 'N/A',
      quoteDate: new Date().toISOString().split('T')[0],
      customerName: selectedCustomer?.name || 'N/A',
      origin: origin,
      destination: destination,
      incoterm: incoterm,
      transportMode: freightMode,
      isDangerousGoods: quote.isDangerousGoods ? 'Yes' : 'No',
      chargeableWeight: `${quote.totalChargeableWeight} RT`,
      piecesSummary: '...',
      totalAmount: quote.totalAmount,
      createdBy: currentUserEmail,
      notes: quote.notes || ''
    };

    try {
      const response = await fetch('https://australia-southeast1-long-justice-454003-b0.cloudfunctions.net/generateQuotePdf', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(pdfPayload),
      });

      if (!response.ok) {
        throw new Error('Failed to generate PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `quote-${pdfPayload.quoteId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();

    } catch (err) {
      console.error(err);
      alert('Failed to download PDF. See console for details.');
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  useEffect(() => {
    if (quote && !isSavingQuote && currentUserEmail) {
      if (!quote.id) {
        setIsSavingQuote(true);
        const quoteDataForFirestore = {
          ...quote
        };

        delete quoteDataForFirestore.id;
        delete quoteDataForFirestore.generatedAt;

        saveQuote(quoteDataForFirestore, currentUserEmail)
          .then((docId) => {
            alert(`Quote saved! ID: ${docId}`);
          })
          .catch((err) => {
            alert('Failed to save quote. See console for details.');
          })
          .finally(() => {
            setIsSavingQuote(false);
          });
      }
    }
  }, [quote, currentUserEmail, isSavingQuote]);

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

      {serviceType === 'customsClearance' && (
        <CustomsClearanceBlock
          onChange={(newData) => setField('customsClearanceData', newData)}
          locations={locations} 
        />
      )}

      {serviceType === 'inlandTransport' && (
        <InlandTransportBlock
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

      <QuoteOutput quote={quote} onDownloadPdf={handleDownloadPdf} isDownloadingPdf={isDownloadingPdf} />
    </div>
  );
}

export default QuoteBuilder; 