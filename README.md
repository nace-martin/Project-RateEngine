#  Project RateEngine

**A modern, scalable Rate Management System (RMS) for the freight and logistics industry.**

Project RateEngine is built by a freight forwarding professional to solve real-world challenges faced by quoting teams in fast-paced environments. It removes ambiguity, reduces manual data entry, and provides a single source of truth for generating accurate, client-ready quotes.

## ✨ Features (MVP - Phase 1)

- Multi-Modal Quoting: Initial support for Domestic Air Freight.
- Dynamic Chargeable Weight Calculation (IATA 1:6000 logic).
- Live Rate Lookup from a centralized data source.
- Automated Ancillary Charges based on shipment profile.
- Detailed Line-Item Quote Summary with GST and total.
- Secure Firebase Authentication.

##  Tech Stack

| Layer       | Tool                     |
|-------------|--------------------------|
| Frontend    | React (Vite)             |
| Backend     | Firebase Platform        |
| Auth        | Firebase Authentication  |
| Database    | Cloud Firestore          |
| Functions   | Firebase Cloud Functions |
| Hosting     | Firebase Hosting (planned) |
| Language    | JavaScript (ES6+)        |

##  Getting Started

### Prerequisites

- Node.js (LTS)
- Git
- Firebase Project

### Installation

```bash
git clone https://github.com/nace-martin/Project-RateEngine.git
cd Project-RateEngine
npm install
```

### Firebase Environment Setup

1. Create a `.env` file in the root.
2. Add the following config values from your Firebase Web App:

```env
VITE_API_KEY="AIzaSyXXXXXXXXX"
VITE_AUTH_DOMAIN="your-project-id.firebaseapp.com"
VITE_PROJECT_ID="your-project-id"
VITE_STORAGE_BUCKET="your-project-id.appspot.com"
VITE_MESSAGING_SENDER_ID="1234567890"
VITE_APP_ID="1:1234567890:web:xxxxxxxxxxxxxxxx"
```

> Required `VITE_` prefix is used by Vite to expose variables.

## ▶️ Run the Dev Server

```bash
npm run dev
```

Visit: [http://localhost:5173](http://localhost:5173)

##  Project Structure

```bash
/
├── public/           # Static assets
├── src/
│   ├── components/   # UI elements
│   ├── pages/        # Route-based views
│   ├── logic/        # Business logic
│   ├── services/     # Firebase/API services
│   ├── config/       # Ancillary charges, FX config
│   └── App.jsx
├── .env              # Firebase secrets
└── README.md
```

## ⚖️ License

MIT License (to be added)