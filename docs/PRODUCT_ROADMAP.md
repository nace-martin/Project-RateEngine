# RateEngine: Product Roadmap

---

## Phase 1: MVP Foundation (✅ Complete)

**Goal:** Prove that the core technical concept is viable by building a functional, end-to-end "happy path" for the main air freight leg.

**Key Features (Completed):**
- **Backend:** Django backend with database models for Clients, Rate Cards, and Quotes.
- **API:** DRF-powered API for all core models.
- **Pricing Engine:** Chargeable weight calculator from multiple pieces, applied to an Airport-to-Airport (A2A) rate.
- **Frontend:** Next.js pages to create, list, and view quotes.

**Business Value:** We have successfully de-risked the project. The core technology works, and the foundational logic is sound.

---

## Phase 2: Security, UI/UX & Core Usability

**Goal:** Make the MVP usable and safe for sales reps by professionalizing the UI and locking down sensitive business rules.

**Key Features / Tasks:**
1. **Role-Based Access (RBAC):**  
   - Sales reps can input buy rates (COGS) but cannot change FX, CAF, or margin rules.  
   - Managers/Finance can see COGS; sales only see Sell.
2. **System Settings:** Centralize FX source, CAF%, margin policy, rounding rules (read-only for sales).
3. **UI Professionalization:** Replace basic HTML with `shadcn/ui` components (`Card`, `Table`, `Input`, `Select`, `Button`) for Quote List, Create, and Detail.
4. **PDF v1:** Branded PDF export with quote version, validity date, DRAFT/FINAL watermark, and standard T&Cs.
5. **Error Handling:** Replace `alert()` with toast notifications.

**Business Value:** Sales reps get a tool that feels professional, is safe to use, and produces client-ready PDFs without risking margin leakage.

---

## Phase 3: Ancillary & Multi-Currency Charges (Controlled Categories)

**Goal:** Expand the pricing engine beyond the main leg and allow complete Door-to-Door / Airport-to-Door quoting. Introduce **controlled categories** so reps stop free-typing inconsistent charges.

**Key Features / Tasks:**
1. **Introduce `RateComponent`:**  
   - Fields: `leg`, `category`, `basis` (`per_kg`, `per_awb`, `per_page`, `percent_of_subtotal`, `percent_of_external`), `unit_buy`, `min`, `max`, `currency`.  
   - Categories: Freight, Fuel, DG, Handling, Cartage, Customs, Disbursement, etc.
2. **Data Entry:** Use Django Admin to seed RateComponents from spreadsheets (PGK, AUD, USD).
3. **Frontend Form:** Add Ancillary Charges section — reps can enter COGS values but must assign them to a **controlled category**.
4. **Pricing Engine Upgrade:** Convert all COGS to PGK, apply FX+CAF, add margin, and produce final Sell in client currency.

**Business Value:**  
- Protects pricing discipline (sales can’t change FX/margins).  
- Produces professional, consistent quotes (no messy labels).  
- Allows Door-to-Door and Airport-to-Door quoting, covering 80% of daily scenarios.  
- Sets the foundation for later AI-assisted normalisation of agent rate sheets.

---

## Phase 4: Multi-Leg Rating Engine (RFC Vision)

**Goal:** Implement the full rule-based engine from the RFC, handling any quoting scenario with precision and auditability.

**Key Features / Tasks:**
1. **Models:** Implement `RateComponent` and `QuotePricingComponent` for all legs.  
2. **Leg Resolver:** Auto-select legs based on Service Type + Incoterm.  
3. **COGS vs Sell Separation:** Enforce strict separation in pricing engine and API.  
4. **Role Views:** API/UI masking so only Finance/Managers see COGS.  
5. **Complex Logic:** Handle per-page, per-ULD, per-week storage, % on subtotals (fuel on cartage), % on external (disbursement on taxes).

**Business Value:**  
- Enables precise, auditable quoting across all scenarios (PX/POM fees, first/last mile, customs, domestic).  
- Powers profitability analysis and protects margin discipline.  
- Turns RateEngine into a strategic quoting platform, not just a calculator.

---

## Phase 5: Enterprise Features & Scalability

**Goal:** Prepare for wider adoption, better performance, and smoother operations.

**Key Features / Tasks:**
1. **Professional Tooling:** Docker for local dev, pre-commit hooks for lint/tests.  
2. **Production Deployment:** Cloud-hosted deployment with PostgreSQL migration.  
3. **CI/CD:** Automated testing and deploys (GitHub Actions).  
4. **Observability:** Add Sentry/logging, backups, monitoring.  

**Business Value:** Application becomes a scalable, maintainable enterprise tool that can grow with the business.

---

## Phase 6: Insights & Reporting

**Goal:** Add visibility and business intelligence.

**Key Features / Tasks:**
- Dashboards for quote volume, conversion rates, profitability by client/lane.  
- Shadow mode: compare old vs new pricing logic.  
- Exportable audit reports for compliance.

**Business Value:** Empowers management with insight into pricing performance, client profitability, and compliance.

---
