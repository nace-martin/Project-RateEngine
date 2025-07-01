// src/firebase/config.js
import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";
// import { getAuth } from "firebase/auth"; // We'll need this later for logins

// Your web app's Firebase configuration from your .env file
// Vite automatically makes these available via import.meta.env
const firebaseConfig = {
  apiKey: import.meta.env.VITE_API_KEY || (() => { throw new Error('VITE_API_KEY is required') })(),
  authDomain: import.meta.env.VITE_AUTH_DOMAIN || (() => { throw new Error('VITE_AUTH_DOMAIN is required') })(),
  projectId: import.meta.env.VITE_PROJECT_ID || (() => { throw new Error('VITE_PROJECT_ID is required') })(),
  storageBucket: import.meta.env.VITE_STORAGE_BUCKET || (() => { throw new Error('VITE_STORAGE_BUCKET is required') })(),
  messagingSenderId: import.meta.env.VITE_MESSAGING_SENDER_ID || (() => { throw new Error('VITE_MESSAGING_SENDER_ID is required') })(),
  appId: import.meta.env.VITE_APP_ID || (() => { throw new Error('VITE_APP_ID is required') })()
};



// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize and export Cloud Firestore database service
export const db = getFirestore(app);

// Initialize and export Auth service
// export const auth = getAuth(app);