    // config.js
// This file holds static configuration data for the application.

export const ancillaryCharges = [
    { name: 'AWB Fee', type: 'Per-Shipment', rate: 70.00, min: 0 },
    { name: 'Security Surcharge', type: 'Per-KG', rate: 0.20, min: 5.00 },
    { name: 'Airline Fuel Surcharge', type: 'Per-KG', rate: 0.35, min: 0 },
    { name: 'PUD Fee', type: 'Per-KG', rate: 0.80, min: 80.00 },
    { name: 'PUD Fuel Surcharge', type: 'Percentage_Of_PUD', rate: 0.10, min: 0, dependsOn: 'PUD Fee' }
];

export const API_URL = 'https://script.google.com/macros/s/AKfycbx4P2c2KsVNuTbIfMX5UvMpAX-QiG2_9nP_KRvQt79R6EDcbI_aPJhjlrUkULKVwfEU/exec';
