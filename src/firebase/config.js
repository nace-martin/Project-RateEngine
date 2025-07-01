// src/firebase/config.js
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
// import { getAuth } from "firebase/auth"; // We'll need this later for logins

// Your web app's Firebase configuration from your .env file
// Vite automatically makes these available via import.meta.env
const firebaseConfig = {
  apiKey: import.meta.env.VITE_API_KEY,
  authDomain: import.meta.env.VITE_AUTH_DOMAIN,
  projectId: import.meta.env.VITE_PROJECT_ID,
  storageBucket: import.meta.env.VITE_STORAGE_BUCKET,
  messagingSenderId: import.meta.env.VITE_MESSAGING_SENDER_ID,
  appId: import.meta.env.VITE_APP_ID
};



// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize and export Cloud Firestore database service
export const db = getFirestore(app);

// Initialize and export Auth service
// export const auth = getAuth(app);