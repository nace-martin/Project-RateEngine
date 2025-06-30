
import { useState } from 'react';
import ShipmentDetails from '../components/ShipmentDetails.jsx';
import QuoteOutput from '../components/QuoteOutput.jsx';
import { useQuoteBuilder } from '../hooks/useQuoteBuilder';
import { customers } from '../config/customers.js';

function QuoteBuilder() {
  const [selectedCustomer, setSelectedCustomer] = useState(customers[0]);

  const {
    origin,
    destination,
    quote,
    error,
    loading,
    locations,
    pieces,
    setField,
    generateQuote,
    clearError,
    setPieces,
    resetQuote,
  } = useQuoteBuilder(selectedCustomer.billingCurrency); // Pass currency to the hook

  const handleGenerateQuote = () => {
    clearError();
    generateQuote();
  };

  const handleResetQuote = () => {
    resetQuote();
    setSelectedCustomer(customers[0]); // Reset customer selection as well
  };

  const handleCustomerChange = (e) => {
    const customer = customers.find((c) => c.id === e.target.value);
    setSelectedCustomer(customer);
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="container mx-auto p-4 flex flex-col gap-5">
        <img src="/efm_logo.svg" alt="Company Logo" className="h-10 mx-auto mb-5" />
        <h1 className="text-dark-charcoal text-3xl font-bold text-center mb-5">Project RateEngine</h1>

        {error && (
          <div className="bg-error text-white p-3 rounded-md flex justify-between items-center">
            {error}
            <button onClick={clearError} className="text-white font-bold text-lg">X</button>
          </div>
        )}

        <div className="bg-white p-4 rounded-2xl shadow-soft border border-cool-gray">
          <h2 className="text-efm-blue text-2xl font-semibold mb-4 pb-2 border-b border-cool-gray">Customer</h2>
          <div className="mb-4">
            <label htmlFor="customer" className="block text-mid-gray text-sm font-bold mb-2">Customer</label>
            <select
              id="customer"
              name="customer"
              value={selectedCustomer.id}
              onChange={handleCustomerChange}
              className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue"
            >
              {customers.map((customer) => (
                <option key={customer.id} value={customer.id}>
                  {customer.name} ({customer.billingCurrency})
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="bg-white p-4 rounded-2xl shadow-soft border border-cool-gray">
          <h2 className="text-efm-blue text-2xl font-semibold mb-4 pb-2 border-b border-cool-gray">Routing</h2>
          <div className="mb-4">
            <label htmlFor="origin" className="block text-mid-gray text-sm font-bold mb-2">Origin</label>
            <select
              id="origin"
              name="origin"
              value={origin}
              onChange={(e) => setField('origin', e.target.value)}
              disabled={!locations.length}
              className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue disabled:opacity-50"
            >
              {locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
          <div className="mb-4">
            <label htmlFor="destination" className="block text-mid-gray text-sm font-bold mb-2">Destination</label>
            <select
              id="destination"
              name="destination"
              value={destination}
              onChange={(e) => setField('destination', e.target.value)}
              disabled={!locations.length}
              className="w-full p-2 border border-cool-gray rounded-md bg-light-gray text-dark-charcoal focus:outline-none focus:border-efm-blue disabled:opacity-50"
            >
              {locations.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
          </div>
        </div>

        <ShipmentDetails pieces={pieces} setPieces={setPieces} />

        <div className="flex justify-center gap-4 mt-5">
          <button
            type="button"
            className="bg-efm-blue text-white px-6 py-3 rounded-xl font-bold text-lg hover:bg-blue-700 disabled:bg-light-gray disabled:text-mid-gray disabled:cursor-not-allowed"
            onClick={handleGenerateQuote}
            disabled={!origin || !destination}
          >
            Generate Quote
          </button>
          <button
            type="button"
            className="bg-efm-orange text-white px-6 py-3 rounded-xl font-bold text-lg hover:bg-orange-700"
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