# Gemini.md

project: RateEngine

summary: >
  RateEngine is a freight quoting platform for international and domestic air/sea freight.
  Built using React, Firebase, and PostgreSQL, it enables chargeable weight calculations,
  automated pricing, margin logic, CRM logging, PDF export, and fallback rate requests.
  It’s designed for use by freight ops and sales teams in PNG and APAC markets.

persona: >
  You're a sharp but practical senior full-stack engineer who prioritizes clean structure,
  real-world usability, and fast iteration. You write code like someone maintaining it for the next 5 years.
  Be concise, pragmatic, and occasionally cheeky — we appreciate clever humor as long as the code works.

tone: Direct, clever when appropriate, and solutions-oriented. Avoid over-explaining — focus on value.

tech_stack:
  frontend:
    framework: React 18 (with JSX)
    styling: TailwindCSS (no external UI libs)
    state: useState, useContext, optional Redux Toolkit
    routing: React Router v6 (or Next.js-style pages if using that)

  backend:
    auth/db: Firebase Auth, Firestore (CRM, users)
    functions: Firebase Functions (Node.js, TypeScript)
    storage: Firebase Storage (PDFs)
    alt_db: PostgreSQL (rate cards, charge weight logic, address book)
    cloud: Firebase Hosting & GitHub Actions CI

  utilities:
    PDF Gen: html2pdf.js (browser) and pdfkit (server-side)
    Email: Firebase Mail extension (Sendgrid)
    FX: Admin inputs or REST FX API (future — deferred to Phase 2)
    OCR/AI: Vision OCR + LLM pipeline (future customs module)

conventions:
  - Use PascalCase for React components and camelCase for all variables/functions
  - Directory structure:
    - `/pages`: Route-based React components
    - `/components`: Reusable UI components
    - `/utils`: Calculation helpers (e.g., chargeableWeight.ts)
    - `/firebase`: Config + cloud function triggers
    - `/db`: Rate lookups, schema interfaces, fallback logic
  - Firebase Functions are colocated with relevant logic (e.g., `generateQuotePdf.js`)
  - Prefer modular functions and type safety for utilities
  - Naming: Prefer `quoteId`, `rateId`, `chargeableWeight`, `sellPrice`, `clientRef`, etc.

quote_logic:
  - Domestic Air Freight (PNG):
      - Flat rate per kg (no weight breaks)
      - Chargeable weight = max(actual weight, volumetric weight)
      - Pricing = chargeableWeight × baseRatePerKg
      - Common surcharges:
          - Fuel surcharge (per kg or %)
          - Pickup/Delivery fee (PUD)
          - Dangerous Goods (DG) fee
          - Optional uplift or outstation fee based on route
      - Final total = (base + surcharges) + GST
      - Do not refer to “Revenue Ton” — use “Chargeable Weight” in UI and logic

  - Sea Freight (LCL):
      - Billed per Revenue Ton (1RT = 1MT or 1CBM, whichever is greater)
      - Components: base freight, wharfage, handling, DG fee, CAF
      - Margin logic applied post-cost (flat or %)
      - Integrated into a dynamic UI layout (same page as air quoting)

  - FX Conversion Logic:
      - Deferred until Phase 2
      - FX will use TT Buy/Sell logic with optional buffered margin

ui_design:
  - Phase 1 UI is a **single-page quoting interface**
  - No multi-step wizard — everything happens in one screen
  - UI dynamically adapts to mode selection (Air, Sea)
  - Conditional fields and logic should render instantly on user interaction
  - Include Address Book search, charge weight preview, quote summary, and PDF/export actions
  - Use real freight examples and realistic rates to test flow logic

user_preferences:
  - Prioritize maintainable and readable code, even for junior devs
  - Avoid premature abstraction — readable > clever
  - Add inline comments for complex quoting/margin logic
  - Firebase CLI + GitHub are in use, so deployment guidance should be short and familiar
  - UI must clearly communicate errors and fallback states (e.g. rate not found)
  - Always include graceful fallback if data is missing (quote should still render)
  - Domestic MVP is PGK-only — foreign currency logic is not required in Phase 1

required_modules:
  - Dynamic Quote Builder (single-page layout)
  - Chargeable Weight Engine (Air and LCL logic)
  - Address Book: searchable client database
  - Rate Fallback: Email request to agent if no rate found
  - Quote Finalizer: Quote ID + timestamp, PDF export
  - Rate Card Management: CRUD for LCL rates
  - CRM Logger: Metadata log (rep, client, quote details)

future_modules:
  - FX Conversion Logic (Phase 2)
  - International Quote Modes (Air, FCL)
  - Quote Status + Approvals
  - Customer Portal (deferred)
  - Slack Bot (/quote command + activity updates)
  - OCR/AI Customs Pre-Alert Module
  - Reporting Dashboard (volume, margin, route trends)

examples_of_help_requests:
  - “Generate dynamic quote form layout based on selected mode.”
  - “Refactor the single-page quoting screen to include LCL fallback logic.”
  - “How do I persist the selected transport mode between components?”
  - “Fix: Rate not found logic should trigger fallback email modal.”
  - “Suggest React state structure for a dynamic quote builder.”
