import { useState, useEffect, useCallback } from 'react';
import { calculateChargeableWeight } from '../lib/weight/calculateChargeableWeight'; // Import the new helper

// Initial state for a single piece
const initialPiece = { id: 1, weight: '', length: '', width: '', height: '' };

// Placeholder for API functions - replace with actual imports if they exist
const fetchLocationsFromAPI = async () => Promise.resolve(['New York', 'London', 'Tokyo', 'Sydney']);
const generateQuoteAPI = async (params) => Promise.resolve({ quoteText: `Quote for ${params.origin} to ${params.destination}`, ...params });


export default function useQuoteBuilder(billingCurrency, freightMode) {
  const [origin, setOrigin] = useState('');
  const [destination, setDestination] = useState('');
  const [pieces, setPieces] = useState([initialPiece]);
  const [incoterm, setIncoterm] = useState('FOB'); // Default Incoterm
  const [warehouseCutoffDate, setWarehouseCutoffDate] = useState('');
  const [serviceType, setServiceType] = useState('airFreight'); // Default service type
  const [inlandTransportData, setInlandTransportData] = useState({});
  const [customsClearanceData, setCustomsClearanceData] = useState({});
  
  const [quote, setQuote] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [locations, setLocations] = useState([]);

  // Calculated weight and volume states
  const [totalGrossWeight, setTotalGrossWeight] = useState(0);
  const [totalVolumeCBM, setTotalVolumeCBM] = useState(0);
  const [chargeableWeightRT, setChargeableWeightRT] = useState(0);

  // Fetch locations on mount
  useEffect(() => {
    const loadLocations = async () => {
      try {
        setLoading(true);
        const fetchedLocations = await fetchLocationsFromAPI();
        setLocations(fetchedLocations);
        if (fetchedLocations.length > 0) {
          setOrigin(fetchedLocations[0]);
          setDestination(fetchedLocations.length > 1 ? fetchedLocations[1] : fetchedLocations[0]);
        }
        setLoading(false);
      } catch (err) {
        setError('Failed to load locations.');
        setLoading(false);
      }
    };
    loadLocations();
  }, []);

  // Recalculate chargeable weight whenever pieces change
  useEffect(() => {
    const {
      totalGrossWeight: gw,
      totalVolumeCBM: cbm,
      chargeableWeightRT: rt,
    } = calculateChargeableWeight(pieces);
    setTotalGrossWeight(gw);
    setTotalVolumeCBM(cbm);
    setChargeableWeightRT(rt);
  }, [pieces]);

  const setField = useCallback((field, value) => {
    switch (field) {
      case 'origin':
        setOrigin(value);
        break;
      case 'destination':
        setDestination(value);
        break;
      case 'incoterm':
        setIncoterm(value);
        break;
      case 'warehouseCutoffDate':
        setWarehouseCutoffDate(value);
        break;
      case 'serviceType':
        setServiceType(value);
        break;
      case 'inlandTransportData':
        setInlandTransportData(value);
        break;
      case 'customsClearanceData':
        setCustomsClearanceData(value);
        break;
      default:
        console.warn(`Attempted to set unknown field: ${field}`);
    }
  }, []);
  
  const generateQuote = useCallback(async () => {
    if (!origin || !destination) {
      setError('Origin and Destination are required to generate a quote.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const quoteParams = {
        origin,
        destination,
        pieces,
        incoterm,
        warehouseCutoffDate,
        serviceType,
        inlandTransportData,
        customsClearanceData,
        totalGrossWeight,
        totalVolumeCBM,
        chargeableWeightRT,
        billingCurrency: billingCurrency || 'USD', // Use provided or default
        freightMode,
      };
      const result = await generateQuoteAPI(quoteParams);
      setQuote(result);
    } catch (err) {
      setError('Failed to generate quote. ' + (err.message || ''));
      setQuote(null);
    } finally {
      setLoading(false);
    }
  }, [
    origin, destination, pieces, incoterm, warehouseCutoffDate, serviceType, 
    inlandTransportData, customsClearanceData, totalGrossWeight, totalVolumeCBM, 
    chargeableWeightRT, billingCurrency, freightMode
  ]);

  const clearError = useCallback(() => {
    setError('');
  }, []);

  const resetQuote = useCallback(() => {
    // Reset relevant fields to initial or default states
    // setOrigin(locations.length > 0 ? locations[0] : '');
    // setDestination(locations.length > 1 ? locations[1] : (locations.length > 0 ? locations[0] : ''));
    setPieces([initialPiece]);
    setIncoterm('FOB');
    setWarehouseCutoffDate('');
    // setServiceType('airFreight'); // Or persist user's last selection? For now, reset.
    setInlandTransportData({});
    setCustomsClearanceData({});
    setQuote(null);
    setError('');
    // Recalculation of weights will be triggered by useEffect on pieces change
  }, [locations]); // Add locations if origin/destination are reset based on them

  // The setPieces function is passed directly, so no special handler needed here unless more logic is required.

  return {
    origin,
    destination,
    pieces,
    setPieces, // Allow direct manipulation of pieces array
    incoterm,
    warehouseCutoffDate,
    serviceType,
    inlandTransportData,
    customsClearanceData,
    quote,
    error,
    loading,
    locations,
    setField,
    generateQuote,
    clearError,
    resetQuote,
    // Expose the calculated values.
    // For consistency with what QuoteBuilder.jsx expects (displayCBM, displayRT)
    displayCBM: totalVolumeCBM,
    displayRT: chargeableWeightRT,
    totalGrossWeight, // Also exposing total gross weight
  };
}
