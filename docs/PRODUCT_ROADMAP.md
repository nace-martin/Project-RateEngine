
---
## RateEngine: Product Roadmap

### **Phase 1: MVP Foundation (Current State - COMPLETE)**

* **Goal:** To build a functional, end-to-end "happy path" for creating a basic air freight quote. This phase proves the core technology and business logic are sound.
* **Key Features (Completed):**
    * **Backend:** A complete Django backend with a database for Clients, Rate Cards, and Quotes.
    * **API:** A fully functional API for all core models.
    * **Pricing Engine:** A backend engine that calculates chargeable weight from multiple pieces and applies the correct A2A rate.
    * **Frontend:** A Next.js application with pages to create, list, and view quotes.
* **Business Value:** We have successfully de-risked the project and proven that the core concept works.

---
### **Phase 2: UI/UX Professionalization & Core Usability (Our Next Steps)**

* **Goal:** To transform the functional but basic UI into a professional, intuitive, and user-friendly tool that sales reps *want* to use.
* **Key Features / Tasks:**
    1.  **Integrate `shadcn/ui`:** Install and configure the `shadcn/ui` library.
    2.  **Refactor All Pages:** Systematically replace the basic HTML elements on all pages (`Create Quote`, `Quote List`, `Quote Detail`) with polished `shadcn/ui` components (`Card`, `Table`, `Input`, `Button`, `Select`).
    3.  **Add PDF Generation:** Implement a feature to export a finalized quote as a professionally branded PDF document. This is a critical feature for sending quotes to clients.
    4.  **Improve Error Handling:** Add user-friendly "toast" notifications for success and error messages instead of simple `alert()` boxes.
* **Business Value:** This phase dramatically increases user adoption and satisfaction. A polished UI builds trust and makes the application feel reliable and easy to use, increasing the efficiency of sales reps.

---
### **Phase 3: Ancillary & Multi-Currency Charges**

* **Goal:** To expand the pricing engine beyond the main air freight leg, allowing sales reps to build complete Door-to-Door quotes for the most common scenarios.
* **Key Features / Tasks:**
    1.  **Create `Charge` Model:** Implement the new `Charge` model in the Django backend to store ancillary charges (e.g., Customs Clearance, Delivery Fee, Fuel Surcharge).
    2.  **Data Entry:** Use the Django Admin to pre-populate this table with your existing SQL data for PGK, AUD, and USD charges.
    3.  **Upgrade Frontend Form:** Add a new section to the "Create Quote" page where users can select the required ancillary charges from a checklist.
    4.  **Upgrade Backend Engine:** Enhance the pricing engine to add the costs of the selected ancillary charges to the quote's final total. The engine must handle charges in different currencies.
* **Business Value:** This is a massive step up in functionality. The application becomes a one-stop-shop for creating complete, accurate quotes, covering the majority of a sales rep's daily needs and significantly reducing manual work.

---
### **Phase 4: Full Multi-Leg Rating Engine (The RFC Vision)**

* **Goal:** To implement the full vision from your RFC document, transforming the application into a sophisticated, rule-based engine that can handle any quoting scenario with precision and auditability.
* **Key Features / Tasks:**
    1.  **Implement New Models:** Introduce the `RateComponent` and `QuotePricingComponent` models to the backend.
    2.  **Build the Leg Resolver:** Create the core logic that automatically selects the correct shipment "legs" based on the **Service Type** and **Incoterm** chosen by the user.
    3.  **Separate COGS from Sell:** Re-architect the pricing engine and API to strictly separate the internal costs (COGS) from the client-facing sell price.
    4.  **Implement Role-Based Views:** Add user roles (e.g., Sales, Finance, Manager) and update the API and UI to show or hide the COGS data based on the user's role.
* **Business Value:** The application becomes a powerful strategic asset. It allows for detailed profitability analysis, enforces business rules automatically, and provides a fully auditable trail for every quote.

---
### **Phase 5: Enterprise Features & Scalability**

* **Goal:** To prepare the application for wider use, better performance, and easier maintenance.
* **Key Features / Tasks:**
    1.  **Dashboards & Reporting:** Build a dashboard to visualize key metrics (e.g., quote volume, conversion rates, profitability by client).
    2.  **Professional Tooling:** Integrate `Docker` to simplify the development setup and `pre-commit` hooks to automate code quality checks.
    3.  **Deploy to Production:** Move the application from local development to a cloud hosting provider, including migrating the database to **PostgreSQL**.
    4.  **Continuous Integration/Continuous Deployment (CI/CD):** Set up a system (like GitHub Actions) to automatically test and deploy new code, making future updates faster and safer.
* **Business Value:** The application becomes a scalable, maintainable, and reliable enterprise tool that can grow with the business.