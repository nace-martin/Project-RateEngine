import { useState, useCallback } from 'react';

// Mock locations data as it seems QuoteBuilder expects it
const MOCK_LOCATIONS = ['New York, USA', 'Los Angeles, USA', 'London, UK', 'Paris, FR', 'Tokyo, JP'];

const useQuoteBuilder = (selectedCustomerBillingCurrency, freightMode) => { // Added params from QuoteBuilder
  const [serviceType, setServiceType] = useState('import');
  const [mode, setMode] = useState(freightMode || 'air'); // Use freightMode from param if available
  const [pieces, setPieces] = useState([{ id: 1, weight: '', length: '', width: '', height: '' }]);
  const [incoterm, setIncoterm] = useState('FOB');
  const [warehouseCutoffDate, setWarehouseCutoffDate] = useState('');

  // State expected by QuoteBuilder.jsx
  const [origin, setOrigin] = useState(MOCK_LOCATIONS[0] || '');
  const [destination, setDestination] = useState(MOCK_LOCATIONS[1] || '');
  const [quote, setQuote] = useState(null); // Or some initial quote structure
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [locations] = useState(MOCK_LOCATIONS); // Read-only for now
  const [displayCBM, setDisplayCBM] = useState(0); // Will need calculation
  const [displayRT, setDisplayRT] = useState(0);   // Will need calculation
  const [customsClearanceData, setCustomsClearanceData] = useState({});
  const [inlandTransportData, setInlandTransportData] = useState({});


  const handleServiceTypeChange = useCallback((eventOrValue) => {
    const value = eventOrValue?.target?.value !== undefined ? eventOrValue.target.value : eventOrValue;
    setServiceType(value);
  }, []);

  const handleModeChange = useCallback((eventOrValue) => {
    const value = eventOrValue?.target?.value !== undefined ? eventOrValue.target.value : eventOrValue;
    setMode(value);
  }, []);

  const handleIncotermChange = useCallback((eventOrValue) => {
    const value = eventOrValue?.target?.value !== undefined ? eventOrValue.target.value : eventOrValue;
    setIncoterm(value);
  }, []);

  const handleWarehouseCutoffDateChange = useCallback((eventOrValue) => {
    const value = eventOrValue?.target?.value !== undefined ? eventOrValue.target.value : eventOrValue;
    setWarehouseCutoffDate(value);
  }, []);

  const setField = useCallback((fieldName, value) => {
    switch (fieldName) {
      case 'serviceType':
        setServiceType(value);
        break;
      case 'mode': // Note: QuoteBuilder uses setFreightMode, not setField('mode',...)
        setMode(value);
        break;
      case 'incoterm':
        setIncoterm(value);
        break;
      case 'warehouseCutoffDate':
        setWarehouseCutoffDate(value);
        break;
      case 'origin':
        setOrigin(value);
        break;
      case 'destination':
        setDestination(value);
        break;
      case 'customsClearanceData':
        setCustomsClearanceData(value);
        break;
      case 'inlandTransportData':
        setInlandTransportData(value);
        break;
      // Add other fields as necessary that QuoteBuilder might try to set via setField
      default:
        console.warn(`setField called for unhandled field: ${fieldName}`);
    }
  }, []);

  // Placeholder functions expected by QuoteBuilder
  const generateQuote = useCallback(() => {
    console.log('generateQuote called with:', { origin, destination, pieces, incoterm, serviceType, mode, selectedCustomerBillingCurrency });
    setLoading(true);
    setError(null);
    // Simulate API call
    setTimeout(() => {
      setQuote({
        summary: `Quote generated for ${serviceType} from ${origin} to ${destination}.`,
        details: pieces,
        // ... other quote details
      });
      setLoading(false);
    }, 1000);
  }, [origin, destination, pieces, incoterm, serviceType, mode, selectedCustomerBillingCurrency]);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const resetQuote = useCallback(() => {
    console.log('resetQuote called');
    setServiceType('import');
    setMode(freightMode || 'air');
    setPieces([{ id: 1, weight: '', length: '', width: '', height: '' }]);
    setIncoterm('FOB');
    setWarehouseCutoffDate('');
    setOrigin(MOCK_LOCATIONS[0] || '');
    setDestination(MOCK_LOCATIONS[1] || '');
    setQuote(null);
    setError(null);
    setCustomsClearanceData({});
    setInlandTransportData({});
    // Reset CBM/RT if they are calculated and stored in state
    setDisplayCBM(0);
    setDisplayRT(0);
  }, [freightMode]);

  // TODO: Implement CBM and RT calculations based on pieces
  // For now, just placeholders. These might need useEffect to update.

  return {
    // States and setters for AirQuoteBuilder
    serviceType,
    handleServiceTypeChange, // Specific handler for AirQuoteBuilder if it uses it
    mode,
    handleModeChange, // Specific handler for AirQuoteBuilder if it uses it
    pieces,
    setPieces,
    incoterm,
    handleIncotermChange, // Specific handler for AirQuoteBuilder if it uses it
    warehouseCutoffDate,
    handleWarehouseCutoffDateChange, // Specific handler for AirQuoteBuilder if it uses it

    // States and setters expected by QuoteBuilder.jsx
    origin,
    destination,
    quote,
    error,
    loading,
    locations,
    displayCBM,
    displayRT,
    customsClearanceData,
    inlandTransportData,
    setField, // Generic setter
    generateQuote,
    clearError,
    resetQuote,
  };
};

export default useQuoteBuilder;
