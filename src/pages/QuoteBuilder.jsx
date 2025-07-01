import './QuoteBuilder.css';
import { useState } from 'react';
import ShipmentDetails from '../components/ShipmentDetails.jsx';
import QuoteOutput from '../components/QuoteOutput.jsx';
import { useQuoteBuilder } from '../hooks/useQuoteBuilder';
import { customers } from '../config/customers.js';

function QuoteBuilder() {
  const [selectedCustomer, setSelectedCustomer] = useState(customers[0]);
  const [freightMode, setFreightMode] = useState('domesticAir'); // Default to Domestic Air

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
  } = useQuoteBuilder(selectedCustomer.billingCurrency, freightMode); // Pass currency and freightMode to the hook
  console.log('QuoteBuilder.jsx - freightMode:', freightMode);

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
    <div className="container">
      <h1>Project RateEngine</h1>

      {error && (
        <div className="error-banner">
          <span className="error-banner-message">{error}</span>
          <button onClick={clearError} aria-label="Clear error">X</button>
        </div>
      )}

      <div className="form-section">
        <h2>Customer</h2>
        <div className="form-group">
          <label htmlFor="customer">Customer</label>
          <select
            id="customer"
            name="customer"
            value={selectedCustomer.id}
            onChange={handleCustomerChange}
          >
            {customers.map((customer) => (
              <option key={customer.id} value={customer.id}>
                {customer.name} ({customer.billingCurrency})
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="form-section">
        <h2>Transport Mode</h2>
        <div className="form-group">
          <label htmlFor="freightMode">Mode</label>
          <select
            id="freightMode"
            name="freightMode"
            value={freightMode}
            onChange={(e) => setFreightMode(e.target.value)}
          >
            <option value="domesticAir">Domestic Air Freight</option>
            <option value="lclSea">LCL Sea Freight</option>
            {/* Add other modes as they are implemented */}
          </select>
        </div>
      </div>

      <div className="form-section">
        <h2>Routing</h2>
        <div className="form-group">
          <label htmlFor="origin">Origin</label>
          <select
            id="origin"
            name="origin"
            value={origin}
            onChange={(e) => setField('origin', e.target.value)}
            disabled={!locations.length}
          >
            {locations.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="destination">Destination</label>
          <select
            id="destination"
            name="destination"
            value={destination}
            onChange={(e) => setField('destination', e.target.value)}
            disabled={!locations.length}
          >
            {locations.map((loc) => (
              <option key={loc} value={loc}>
                {loc}
              </option>
            ))}
          </select>
        </div>
      </div>

      {(freightMode === 'domesticAir' || freightMode === 'lclSea') && (
        <ShipmentDetails pieces={pieces} setPieces={setPieces} />
      )}

      <div className="action-buttons">
        <button
          type="button"
          className="btn-generate"
          onClick={handleGenerateQuote}
          disabled={!origin || !destination}
        >
          Generate Quote
        </button>
        <button
          type="button"
          className="btn-reset"
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