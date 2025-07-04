import { useState, useEffect } from 'react';
import { getAuth, onAuthStateChanged } from 'firebase/auth';
import { getClientDataByUID } from '../lib/firestore/clients'; // Adjusted path

export default function useFirebaseUser() {
  const [firebaseUser, setFirebaseUser] = useState(null); // Renamed to avoid confusion
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const auth = getAuth();
    setLoading(true);

    const unsubscribe = onAuthStateChanged(auth, async (authUser) => {
      if (authUser) {
        try {
          const clientData = await getClientDataByUID(authUser.uid);
          // Merge auth user data with client Firestore data
          setFirebaseUser({
            ...authUser, // Basic auth properties like uid, email, displayName
            clientData: clientData || {}, // Attach client-specific data, default to empty object if null
          });
          setError(null);
        } catch (e) {
          console.error("Failed to fetch client data:", e);
          setError(e);
          // Set basic auth user even if client data fetch fails, or handle error differently
          setFirebaseUser(authUser);
        }
      } else {
        setFirebaseUser(null);
      }
      setLoading(false);
    });

    return () => {
      unsubscribe();
      setLoading(true); // Reset loading state on cleanup
      setError(null); // Reset error state
      setFirebaseUser(null); // Reset user
    };
  }, []);

  // Return an object for more extensibility, e.g., including loading/error states
  return { user: firebaseUser, loading, error };
}