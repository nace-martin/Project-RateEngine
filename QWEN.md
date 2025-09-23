# Project-RateEngine Context for Qwen Code

## Project Overview

RateEngine is a Django/Next.js application designed to streamline and automate air-freight quoting for freight forwarders. It provides a backend API for managing clients, rate cards, and computing quotes, along with a frontend UI for users to interact with these features.

The system is built with a clear separation of concerns:
- **Backend (Python/Django):** Handles business logic, data persistence, and API endpoints.
- **Frontend (Next.js/TypeScript):** Provides a user interface for creating, viewing, and managing quotes.

## Technology Stack

- **Backend:**
  - Language: Python
  - Framework: Django 5 with Django REST Framework (DRF)
  - Database: PostgreSQL (required)
- **Frontend:**
  - Framework: Next.js (React) with TypeScript
  - Styling: Tailwind CSS
- **Development & Deployment:**
  - Docker Compose for local Postgres instance
  - Makefile for common commands
  - npm for frontend package management

## Key Directories and Files

- `backend/`: Contains the Django project and apps (`accounts`, `core`, `organizations`, `pricing`, `quotes`).
- `frontend/`: Contains the Next.js application.
- `docs/`: Contains project documentation including the product roadmap.
- `scripts/`: Contains utility scripts for development tasks.
- `Makefile`: Defines shortcuts for common development tasks (db-up, backend-install, frontend-dev, etc.).
- `README.md`: Primary guide for setting up and running the project.
- `AGENTS.md`: Guidelines for repository structure, coding style, and development practices.

## Building and Running

### Prerequisites

- Python 3.8+
- Node.js 18+
- PostgreSQL
- Docker & Docker Compose (for local DB)

### Quick Start

1. **Start Database:**
   - Unix/macOS: `make db-up`
   - Windows PowerShell: `./scripts/dev_db_up.ps1`
   - Note the printed `DATABASE_URL` and set it in your environment or `.env` file.

2. **Backend Setup:**
   - Navigate to `backend/`: `cd backend`
   - Create and activate a virtual environment:
     - Windows: `python -m venv .venv && . .venv/Scripts/activate`
     - Unix/macOS: `python -m venv .venv && source .venv/bin/activate`
   - Install dependencies: `pip install -r requirements.txt`
   - Run migrations: `python manage.py migrate`
   - (Optional) Create test users: `python manage.py create_test_users`
   - Start the development server: `python manage.py runserver`
   - The backend API will be available at `http://127.0.0.1:8000`.

3. **Frontend Setup:**
   - Navigate to `frontend/`: `cd frontend`
   - Install dependencies: `npm install`
   - Start the development server: `npm run dev`
   - The frontend will be available at `http://localhost:3000`.

### Makefile Commands (from repo root)

- `make db-up`: Start Postgres via Docker Compose.
- `make db-down`: Stop Postgres.
- `make db-logs`: Tail Postgres logs.
- `make backend-install`: Set up backend virtual environment and install dependencies.
- `make backend-run`: Run the Django development server.
- `make test-backend`: Run backend tests.
- `make frontend-install`: Install frontend dependencies.
- `make frontend-dev`: Start the Next.js development server.

## Development Conventions

### Backend (Python/Django)

- **Coding Style:** Follow PEP 8. Use `snake_case` for modules/files. Prefer explicit, descriptive names.
- **App Structure:** Keep views/serializers within their respective app packages. API endpoints are under the `api/` namespace.
- **Testing:** Write tests using Django's `TestCase` in each app's `tests.py`. Run tests with `python manage.py test`.
- **Authentication:** Uses DRF Token Authentication. Protected endpoints require an `Authorization: Token <token>` header.

### Frontend (Next.js/TypeScript)

- **Component Naming:** Components use `PascalCase`; hooks and utilities use `camelCase`.
- **Styling:** Utilize Tailwind CSS utility classes.
- **Linting:** ESLint configuration is located at `frontend/eslint.config.mjs`.

## Project Roadmap Highlights

The project is structured in phases:
1. **MVP Foundation:** Core technical concept proven with basic quoting functionality.
2. **Security, UI/UX & Core Usability:** Implement RBAC, professionalize UI, add PDF export.
3. **Ancillary & Multi-Currency Charges:** Expand pricing engine to handle complex charges and Door-to-Door quoting.
4. **Multi-Leg Rating Engine:** Implement a full rule-based engine for any quoting scenario.
5. **Enterprise Features & Scalability:** Add Docker, CI/CD, monitoring for production readiness.
6. **Insights & Reporting:** Add dashboards and business intelligence features.
