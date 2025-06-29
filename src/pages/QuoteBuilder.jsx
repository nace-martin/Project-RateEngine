import '../App.css';
import ShipmentDetails from '../components/ShipmentDetails.jsx';
import QuoteOutput from '../components/QuoteOutput.jsx';
import { useQuoteBuilder } from '../hooks/useQuoteBuilder';
import { fxRates } from '../config/fxRates.js';

function QuoteBuilder() {
  const {
    origin,
    destination,
    quote,
    error,
    loading,
    locations,
    currency,
    pieces,
    setField,
    generateQuote,
    clearError,
    setPieces,
  } = useQuoteBuilder();

  const handleGenerateQuote = () => {
    clearError();
    generateQuote();
  };

  if (loading) {
    return <div>Loading...</div>;
  }

  return (
    <div className="container">
      <h1>Project RateEngine</h1>

      {error && (
        <div className="error-banner">
          {error}
          <button onClick={clearError}>X</button>
        </div>
      )}

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
        <div className="form-group">
          <label htmlFor="currency">Currency</label>
          <select
            id="currency"
            name="currency"
            value={currency}
            onChange={(e) => setField('currency', e.target.value)}
          >
            {Object.keys(fxRates).map((currencyCode) => (
              <option key={currencyCode} value={currencyCode}>
                {currencyCode}
              </option>
            ))}
          </select>
        </div>
      </div>

      <ShipmentDetails pieces={pieces} setPieces={setPieces} />

      <div className="action-buttons">
        <button
          type="button"
          className="btn-generate"
          onClick={handleGenerateQuote}
          disabled={!origin || !destination}
        >
          Generate Quote
        </button>
      </div>

      <QuoteOutput quote={quote} />
    </div>
  );
}

export default QuoteBuilder;