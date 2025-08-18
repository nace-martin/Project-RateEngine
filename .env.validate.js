// .env.validate.js
import fs from 'fs';
import dotenv from 'dotenv';

dotenv.config();

const REQUIRED_VARS = [
  'FIREBASE_API_KEY',
  'FIREBASE_AUTH_DOMAIN',
  'FIREBASE_PROJECT_ID',
  'FIREBASE_STORAGE_BUCKET',
  'FIREBASE_MESSAGING_SENDER_ID',
  'FIREBASE_APP_ID',
  'FIREBASE_MEASUREMENT_ID',
  // add more required variables here
];

let missing = [];

REQUIRED_VARS.forEach((key) => {
  if (!process.env[key]) {
    missing.push(key);
  }
});

if (missing.length) {
  console.error(`❌ Missing required env vars: ${missing.join(', ')}`);
  process.exit(1);
} else {
  console.log('✅ All required env vars are set.');
}
