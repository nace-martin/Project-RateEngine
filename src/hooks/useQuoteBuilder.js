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
};

function reducer(state, action) {
  switch (action.type) {
    case 'FETCH_SUCCESS':
      return {
        ...state,
        freightRates: action.payload.freightRates,
        locations: action.payload.locations,
        origin: action.payload.locations[0] || '',
        destination: action.payload.locations[1] || action.payload.locations[0] || '',
        loading: false,
      };
    case 'FETCH_ERROR':
      return { ...state, error: action.payload, loading: false };
    case 'SET_FIELD':
      return { ...state, [action.field]: action.value };
    case 'GENERATE_QUOTE':
      try {
        const newQuote = generateQuoteFromLogic(
          {
            origin: state.origin,
            destination: state.destination,
            pieces: state.pieces,
            rateCurrency: action.payload.rateCurrency, // Pass the rate currency
            targetCurrency: action.payload.targetCurrency, // Use the customer's currency
          },
          state.freightRates
        );
        return { ...state, quote: newQuote, error: null };
      } catch (_err) {
        return { ...state, error: _err.message, quote: null };
      }
    case 'CLEAR_ERROR':
      return { ...state, error: null };
    case 'RESET':
      return {
        ...initialState,
        loading: true, // Ensure loading state is true to re-fetch data
      };
    default:
      throw new Error(`Unknown action type: ${action.type}`);
  }
}

export function useQuoteBuilder(targetCurrency) {
  const [state, dispatch] = useReducer(reducer, initialState);

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
    dispatch({ type: 'GENERATE_QUOTE', payload: { targetCurrency, rateCurrency: 'PGK' } });
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

  return { ...state, setField, generateQuote, clearError, setPieces, resetQuote };
}
