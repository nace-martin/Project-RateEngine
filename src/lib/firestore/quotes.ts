import { getFirestore, collection, addDoc, serverTimestamp } from 'firebase/firestore';
import { app } from '../../firebase/config.js'; // Updated path

// Initialize Firestore
const db = getFirestore(app);

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

/**
 * Saves a quote to Firestore.
 * @param quoteData The quote data from useQuoteBuilder.
 * @param userEmail The email of the current user.
 * @returns The ID of the newly created document.
 * @throws Will throw an error if the save operation fails.
 */
export const saveQuote = async (quoteData: QuoteData, userEmail: string): Promise<string> => {
  try {
    const docRef = await addDoc(collection(db, 'quotes'), {
      ...quoteData,
      createdAt: serverTimestamp(),
      createdBy: userEmail,
      status: 'draft',
    });
    return docRef.id;
  } catch (error) {
    console.error('Error saving quote to Firestore:', error);
    throw new Error('Failed to save quote');
  }
};
