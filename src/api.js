// api.js
// This file handles all communication with external APIs.

import { API_URL } from './config.js';

export async function loadRateData() {
    try {
        const response = await fetch(API_URL);
        if (!response.ok) throw new Error(`Network response was not ok: ${response.statusText}`);
        const dataFromSheet = await response.json();
        
        const nestedRates = {};
        const uniqueLocations = new Set();
        dataFromSheet.forEach(row => {
            const origin = row.OriginAirportCode;
            const dest = row.DestinationAirportCode;
            const rate = row.Rate_Per_KG_PGK;
            if(origin && dest && origin.trim() !== "" && dest.trim() !== "") {
                uniqueLocations.add(origin);
                uniqueLocations.add(dest);
                if (!nestedRates[origin]) nestedRates[origin] = {};
                nestedRates[origin][dest] = { rate: parseFloat(rate) };
            }
        });
        
        console.log("Freight rates and locations loaded successfully!");
        // Return the processed data
        return { freightRates: nestedRates, locations: Array.from(uniqueLocations).sort() };

    } catch (error) {
        console.error("Failed to load rate data:", error);
        alert("Error: Could not load freight rates. Please check the console for details.");
        // Return an empty state so the app doesn't crash
        return { freightRates: {}, locations: [] };
    }
}