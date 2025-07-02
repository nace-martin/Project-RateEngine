import { useReducer, useEffect } from 'react';
import { loadRateData } from '../services/api';
import { generateQuote as generateQuoteFromLogic } from '../logic/QuoteLogicEngine';

const initialState = {
  freightRates: {},
  locations: [],
  origin: '',
  destination: '',
  quote: null,
  chargeableWeight: 0,
  error: null,
  loading: true,
  pieces: [{ id: 1, weight: '', length: '', width: '', height: '' }],
  incoterm: 'EXW', // Default Incoterm
  warehouseCutoffDate: '', // For LCL
  // Derived values for display, not part of core state for quote generation but for UI
  displayCBM: 0,
  displayRT: 0,
  serviceType: 'airFreight', // Default service type
};

function calculateDisplayMetrics(pieces, freightMode) {
  const totalWeight = pieces.reduce((sum, piece) => sum + Number(piece.weight || 0), 0);
  const totalCBM = pieces.reduce((sum, piece) => {
    const length = Number(piece.length || 0);
    const width = Number(piece.width || 0);
    const height = Number(piece.height || 0);
    return sum + (length * width * height) / 1000000; // Convert cm3 to m3 (CBM)
  }, 0);

  let displayRT = 0;
  if (freightMode === 'sea-lcl') {
    const totalMetricTons = totalWeight / 1000;
    displayRT = Math.max(totalCBM, totalMetricTons);
  } else if (freightMode === 'air-domestic' || freightMode === 'air-international') {
    // For air, RT isn't typically displayed, chargeable weight is key.
    // However, if RT concept is needed for air based on 1:6000, it's Volumetric Weight / 1000 if comparing to MT.
    // Or simply the chargeable weight itself. For now, let's keep it specific to LCL display.
    const volumetricWeight = totalCBM * 167;
    displayRT = Math.max(totalWeight, volumetricWeight); // This is chargeable weight for air
  }


  return { displayCBM: totalCBM, displayRT };
}

function reducer(state, action) {
  switch (action.type) {
    case 'FETCH_SUCCESS': {
      // Metrics will be updated by the useEffect hook based on initial pieces and freightMode
      return {
        ...state,
        freightRates: action.payload.freightRates,
        locations: action.payload.locations,
        origin: action.payload.locations[0] || '',
        destination: action.payload.locations[1] || action.payload.locations[0] || '',
        loading: false,
      };
    }
    case 'FETCH_ERROR':
      return { ...state, error: action.payload, loading: false };
    case 'SET_FIELD': {
      // If pieces are being updated, the useEffect will catch it.
      // This primarily handles fields like origin, destination, incoterm, warehouseCutoffDate
      return { ...state, [action.field]: action.value };
    }
    case 'UPDATE_DISPLAY_METRICS': // New action type specifically for metrics
      return { ...state, displayCBM: action.payload.displayCBM, displayRT: action.payload.displayRT };
    case 'GENERATE_QUOTE': {
      console.log('useQuoteBuilder.js - reducer action.payload.freightMode:', action.payload.freightMode);
      // Add CBM > 0 validation for LCL before attempting to generate quote
      if (action.payload.freightMode === 'sea-lcl') {
        // Recalculate metrics here to ensure fresh data for validation, though useEffect should keep it up to date.
        const currentMetrics = calculateDisplayMetrics(state.pieces, action.payload.freightMode);
        if (currentMetrics.displayCBM <= 0) {
          return { ...state, error: 'Total CBM must be greater than 0 for LCL shipments.', quote: null };
        }
      }
      try {
        const newQuote = generateQuoteFromLogic(
          {
            origin: state.origin,
            destination: state.destination,
            pieces: state.pieces,
            rateCurrency: action.payload.rateCurrency,
            targetCurrency: action.payload.targetCurrency,
            freightMode: action.payload.freightMode,
            incoterm: state.incoterm,
            warehouseCutoffDate: state.warehouseCutoffDate,
          },
          state.freightRates
        );
        return { ...state, quote: newQuote, error: null };
      } catch (_err) {
        return { ...state, error: _err.message, quote: null };
      }
    }
    case 'CLEAR_ERROR':
      return { ...state, error: null };
    case 'RESET': {
      // When resetting, also recalculate display metrics for the initial state
      const resetMetrics = calculateDisplayMetrics(initialState.pieces, initialState.freightMode);
      return {
        ...initialState,
        loading: true, // Ensure loading state is true to re-fetch data
        displayCBM: resetMetrics.displayCBM, // Apply reset metrics
        displayRT: resetMetrics.displayRT,   // Apply reset metrics
      };
    }
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }
}

export function useQuoteBuilder(targetCurrency, freightMode) { // freightMode is a prop from QuoteBuilder
  const [state, dispatch] = useReducer(reducer, initialState);

  // Effect to update display metrics when pieces or the freightMode prop changes
  useEffect(() => {
    const metrics = calculateDisplayMetrics(state.pieces, freightMode);
    dispatch({ type: 'UPDATE_DISPLAY_METRICS', payload: metrics });
  }, [state.pieces, freightMode]);

  useEffect(() => {
    let isMounted = true;
    async function getRates() {
      try {
        const { freightRates, locations } = await loadRateData();
        if (isMounted) {
          dispatch({ type: 'FETCH_SUCCESS', payload: { freightRates, locations } });
        }
      } catch (err) { // eslint-disable-line no-unused-vars
        if (isMounted) {
          dispatch({ type: 'FETCH_ERROR', payload: 'Failed to load rate data.' });
        }
      }
    }
    // Only fetch if loading is true (initial state or after reset)
    if (state.loading) {
      getRates();
    }
    return () => {
      isMounted = false;
    };
  }, [state.loading]); // Depend on state.loading

  const setField = (field, value) => {
    dispatch({ type: 'SET_FIELD', field, value });
  };

  const generateQuote = () => {
    dispatch({ type: 'GENERATE_QUOTE', payload: { targetCurrency, rateCurrency: 'PGK', freightMode } });
  };

  const clearError = () => {
    dispatch({ type: 'CLEAR_ERROR' });
  };

  const setPieces = (newPieces) => {
    dispatch({ type: 'SET_FIELD', field: 'pieces', value: newPieces });
  };

  const resetQuote = () => {
    dispatch({ type: 'RESET' });
  };

  // Ensure all necessary state variables are returned from the hook
  return {
    ...state, // includes origin, destination, quote, error, loading, pieces, incoterm, warehouseCutoffDate, displayCBM, displayRT
    setField,
    generateQuote,
    clearError,
    setPieces,
    resetQuote,
  };
}
