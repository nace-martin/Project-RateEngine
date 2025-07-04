import { doc, getDoc, getFirestore } from 'firebase/firestore';
// Assuming app is initialized and exported from @/firebase/config or a similar path
// For robust path resolution, especially if this file is deep, ensure tsconfig paths are set up
// or use relative paths. Using a common alias for this example.
import { app } from '@/firebase/config';

const db = getFirestore(app);

export interface ClientData {
  id?: string; // UID will be the document ID
  name?: string;
  companyName?: string;
  billingLocation?: string; // e.g., "PNG", "AUS", "USA"
  // Add other client-specific fields here
}

/**
 * Fetches a client's profile data from Firestore using their UID.
 * Assumes a 'clients' collection where document IDs are user UIDs.
 *
 * @param uid The user's UID.
 * @returns A promise that resolves to the client's data (ClientData) or null if not found or on error.
 */
export const getClientDataByUID = async (uid: string): Promise<ClientData | null> => {
  if (!uid) {
    console.error("getClientDataByUID: UID is missing.");
    return null;
  }
  try {
    const clientDocRef = doc(db, 'clients', uid);
    const clientDocSnap = await getDoc(clientDocRef);

    if (clientDocSnap.exists()) {
      return { id: clientDocSnap.id, ...clientDocSnap.data() } as ClientData;
    } else {
      console.warn(`No client document found in 'clients' collection for UID: ${uid}`);
      return null;
    }
  } catch (error) {
    console.error("Error fetching client data from Firestore:", error);
    return null;
  }
};