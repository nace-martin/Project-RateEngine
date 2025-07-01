# 📍 RateEngine Roadmap

This roadmap outlines key milestones for the RateEngine freight quotation platform. Each phase builds on the core goal of automating and streamlining international and domestic quoting, CRM integration, and eventually client self-service. For now, internal adoption and team readiness take priority.

---

## 🚧 Phase 1 – Dynamic Quoting MVP (In Progress)

**Focus**: Build a dynamic, single-page interface that reconfigures itself in real-time based on user selections. The goal is to provide a fast, intuitive quoting experience for all domestic freight modes.

- [x] Core Air Freight Logic Engine  
  - The underlying calculations for volumetric weight and domestic air charges are complete and validated.

- [ ] Dynamic Single-Page Quoting UI  
  - A single screen that contextually adapts to user choices, replacing the need for a multi-step wizard.  
  - All quoting functions will exist on one page for maximum speed and user efficiency.  
  - The UI will dynamically show, hide, or alter fields based on the selected freight mode.

- [ ] Transport Mode & Scope Selector  
  - The "master control" panel at the top of the UI. This selection will drive all other contextual logic on the page in real-time.

- [ ] Enable LCL Sea Freight Module  
  - Integrate the LCL-specific logic into the new dynamic UI.  
  - Implement Revenue Ton (RT) logic within the Chargeable Weight Engine.  
  - Build the instant quote calculator for Bismark rates.  
  - Build the Agent Rate Fallback workflow for Consort (e.g., "Generate Email Request").

- [ ] Address Book Module  
  - Add a client search/select feature within the single-page UI.

- [ ] Quote Finalization Features  
  - Auto-generate Quote ID + Timestamp upon quote creation.  
  - Implement a PDF Quote Export function.

- [ ] (Deferred) FX Conversion Logic  
  - This feature is not required for the domestic (PGK) MVP and will be built alongside the international module in Phase 2.

---

## 🚀 Phase 2 – V1 Launch (Internal-Only)

Adds international freight support, audit trail, and margin visibility.

- [ ] Incoterms + DG Logic  
  - Selectable incoterms, DG fee triggers, and flags for customs/airlines

- [ ] International Air + FCL Quoting  
  - Carrier-based pricing in foreign currencies + markup + FX logic

- [ ] FX Conversion Logic  
  - Convert PGK ↔ AUD/USD using TT Sell/Buy logic + buffered rate option

- [ ] Quote Status Lifecycle  
  - Status flow: Draft → Sent → Follow-up → Approved/Expired

- [ ] CRM Logging Integration  
  - Store all quotes in Firestore with metadata (user, mode, totals, currency)

- [ ] Margin Transparency  
  - Show buy/sell rate per kg or RT, client vs cost breakdown

- [ ] Quote Reminder Logic  
  - Manual or auto-reminder to follow up on sent quotes, email template support

- [ ] Quote Duplication Tool  
  - Reuse/edit past quotes to speed up repeat quoting

---

## 🧱 Internal Adoption Milestone (Pre-Client Rollout)

This milestone ensures the system is fully embedded within the internal workflow before exposing it to clients.

- [ ] Internal onboarding of all quoting users  
  - Air, Sea, Customs teams trained and actively using RateEngine

- [ ] Internal SOP alignment  
  - Ensure quoting process aligns with operations, billing, and margin policies

- [ ] Client quote QA  
  - Manual checks of 100+ real quotes to validate accuracy and output

- [ ] Feedback loop  
  - Internal feedback cycle with refinements before client exposure

---

## 🧠 Phase 3 – Automation & Ops Intelligence

Focus on automating workflows, improving compliance, and preparing for future client-facing capabilities.

- [ ] Rate Versioning & Approvals  
  - Admin-only approval workflow, version history for edited quotes

- [ ] Internal Quote Approvals  
  - Optional approval before sending client-facing version

- [ ] Role-Based Access (Admin, Sales, Client)  
  - Restrict view/edit rights per user type (client roles to be activated in future phase)

- [ ] OCR + Auto HS Code Tagger (Customs Module)  
  - Extract invoice data → auto-assign HS codes using AI

- [ ] Pre-Alert Upload Interface  
  - Drag-and-drop doc intake for Customs compilers, tied to job ID

- [ ] Slack Bot Integration  
  - "/quote" command + new quote notifications + reminders

---

## 📈 Future Enhancements / Stretch Goals

- [ ] Client Portal *(Deferred)*  
  - Secure login, view quote history, request new quotes  
  > ❗ Deferred until full internal integration and training is complete.

- [ ] Reporting Dashboard  
  - Quoting trends, margin %, rep activity, top routes

- [ ] FX Admin Override Tool  
  - Manual locking of FX rates + margin buffer tool

- [ ] Custom Quote Terms Editor  
  - Add/edit notes & T&Cs per client or quote

- [ ] Mobile Quoting Mode  
  - Optimized quote flow for phones/tablets

---

## 🤖 Gemini CLI Usage

Gemini, use this roadmap to:

- Suggest schema designs and UI flows per phase  
- Validate quote logic against current business rules (e.g., margin, FX, fallback)  
- Assist with feature scaffolding for items not yet built  
- Flag inconsistencies between modules (e.g., missing CRM logging on quote submit)  
- Cross-reference user flows across modules (e.g., CRM logging → lead follow-up)  
- Identify reusable logic patterns across modules (e.g., FX in air/sea/customs)
