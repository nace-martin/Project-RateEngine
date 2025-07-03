import { getFirestore, collection, addDoc, serverTimestamp } from 'firebase/firestore';
import { getAuth } from 'firebase/auth';
import { app } from '../../firebase/config.js';

const db = getFirestore(app);
const auth = getAuth(app);

// Define the structure of a piece
interface Piece {
  id: number | string; // string if it comes from form input, number if processed
  weight: string | number;
  length: string | number;
  width: string | number;
  height: string | number;
}

// Define the structure of a line item
interface LineItem {
  name: string;
  cost: number;
}

// Define the structure of your quote data based on useQuoteBuilder and QuoteOutput.jsx
interface QuoteData {
  origin: string;
  destination: string;
  chargeableWeight: number;
  lineItems: LineItem[];
  subTotal: number;
  gst: number;
  grandTotal: number;
  // Contextual fields from the quote generation process
  pieces: Piece[];
  // rateCurrency?: string; // Not directly in QuoteOutput, but part of generation
  targetCurrency?: string; // Part of generation context (billingCurrency of customer)
  freightMode: string;
  incoterm: string;
  warehouseCutoffDate?: string; // Optional, specific to LCL

  // Metadata (createdAt, createdBy, status) will be added by the saveQuote function
  // Client-side 'generatedAt' and 'id' (if any) from the quote object will be excluded
}

export const saveQuote = async (quoteData) => {
  const user = auth.currentUser;
  if (!user) {
    throw new Error('User not authenticated. Cannot save quote.');
  }

  const enrichedQuote = {
    ...quoteData,
    createdAt: serverTimestamp(),
    createdBy: user.uid,
  };

  const docRef = await addDoc(collection(db, 'quotes'), enrichedQuote);
  return docRef.id;
};