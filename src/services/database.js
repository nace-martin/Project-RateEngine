// database.js

// Import our database instance from the config file
import { db } from './firebase-config.js';
// Import the Firestore functions we need
import { collection, addDoc, serverTimestamp, query, where, orderBy, getDocs, doc, updateDoc, deleteDoc } from "https://www.gstatic.com/firebasejs/9.15.0/firebase-firestore.js";

/**
 * Saves a quote data object to the 'quotes' collection in Firestore.
 * @param {object} quoteData - The quote data to save.
 * @returns {boolean} - True if successful, false otherwise.
 */
export async function saveQuoteToDb(quoteData) {
    try {
        // Add a new document with a generated ID to the "quotes" collection.
        const docRef = await addDoc(collection(db, "quotes"), {
            ...quoteData, // Spread the original quote data. Quote data may now include customerId and customerName.
            createdAt: serverTimestamp() // Add a server-side timestamp for sorting
        });
        console.log("Quote saved successfully with ID: ", docRef.id);
        return true; // Indicate success
    } catch (e) {
        console.error("Error adding document: ", e);
        return false; // Indicate failure
    }
}

/**
 * Fetches quotes from Firestore for a specific user, ordered by creation date.
 * @param {string} userId - The ID of the user whose quotes to fetch.
 * @returns {Array<object>} - An array of quote objects, or an empty array if an error occurs.
 */
export async function getQuotesFromDb(userId) {
    try {
        const q = query(
            collection(db, "quotes"),
            where("userId", "==", userId),
            orderBy("createdAt", "desc") // Order by creation date, newest first
        );
        const querySnapshot = await getDocs(q);
        const quotes = [];
        querySnapshot.forEach((doc) => {
            quotes.push({ id: doc.id, ...doc.data() });
        });
        console.log(`Fetched ${quotes.length} quotes for user ${userId}.`);
        return quotes;
    } catch (e) {
        console.error("Error fetching documents: ", e);
        return []; // Return empty array on error
    }
}

// --- Customer Management Functions ---

/**
 * Saves a customer data object to the 'customers' collection in Firestore.
 * @param {object} customerData - The customer data to save. Expected: { name, companyName, email, phone, address, userId }
 * @returns {string|null} - The ID of the new customer if successful, null otherwise.
 */
export async function addCustomerToDb(customerData) {
    if (!customerData.userId) {
        console.error("Error: userId is missing from customerData.");
        return null;
    }
    try {
        const docRef = await addDoc(collection(db, "customers"), {
            ...customerData,
            createdAt: serverTimestamp()
        });
        console.log("Customer saved successfully with ID: ", docRef.id);
        return docRef.id;
    } catch (e) {
        console.error("Error adding customer document: ", e);
        return null;
    }
}

/**
 * Fetches customers from Firestore for a specific user, ordered by name.
 * @param {string} userId - The ID of the user whose customers to fetch.
 * @returns {Array<object>} - An array of customer objects, or an empty array if an error occurs.
 */
export async function getCustomersFromDb(userId) {
    try {
        const q = query(
            collection(db, "customers"),
            where("userId", "==", userId),
            orderBy("name", "asc")
        );
        const querySnapshot = await getDocs(q);
        const customers = [];
        querySnapshot.forEach((doc) => {
            customers.push({ id: doc.id, ...doc.data() });
        });
        console.log(`Fetched ${customers.length} customers for user ${userId}.`);
        return customers;
    } catch (e) {
        console.error("Error fetching customer documents: ", e);
        return [];
    }
}

/**
 * Updates an existing customer document in Firestore.
 * @param {string} customerId - The ID of the customer to update.
 * @param {object} customerData - An object containing the fields to update.
 * @returns {boolean} - True if successful, false otherwise.
 */
export async function updateCustomerInDb(customerId, customerData) {
    try {
        const customerRef = doc(db, "customers", customerId);
        await updateDoc(customerRef, customerData);
        console.log("Customer updated successfully: ", customerId);
        return true;
    } catch (e) {
        console.error("Error updating customer document: ", e);
        return false;
    }
}

/**
 * Deletes a customer document from Firestore.
 * @param {string} customerId - The ID of the customer to delete.
 * @returns {boolean} - True if successful, false otherwise.
 */
export async function deleteCustomerFromDb(customerId) {
    try {
        const customerRef = doc(db, "customers", customerId);
        await deleteDoc(customerRef);
        console.log("Customer deleted successfully: ", customerId);
        return true;
    } catch (e) {
        console.error("Error deleting customer document: ", e);
        return false;
    }
}