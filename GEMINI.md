# Project-RateEngine GEMINI.md

## Project Overview

This is a full-stack web application designed to streamline and automate the air freight quoting process.

*   **Backend:** The backend is built with Python using the Django framework and the Django REST Framework for creating APIs. It uses a SQLite database for development and PostgreSQL for production.
*   **Frontend:** The frontend is a single-page application built with Next.js (a React framework) and TypeScript. It uses Tailwind CSS for styling.
*   **Architecture:** The project follows a classic client-server architecture, with the frontend application consuming the backend's RESTful API.

## Building and Running

### Backend

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```
2.  **Activate the virtual environment:**
    ```bash
    # On Windows
    .\venv\Scripts\activate
    ```
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
4.  **Run database migrations:**
    ```bash
    python manage.py migrate
    ```
5.  **Start the development server:**
    ```bash
    python manage.py runserver
    ```
    The backend API will be available at `http://127.0.0.1:8000`.

### Frontend

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```
2.  **Install dependencies:**
    ```bash
    npm install
    ```
3.  **Start the development server:**
    ```bash
    npm run dev
    ```
    The frontend application will be available at `http://localhost:3000`.

## Development Conventions

*   **Backend:**
    *   The backend follows the standard Django project structure.
    *   The `rate_engine` directory contains the project settings, while `accounts`, `core`, `pricing`, and `quotes` are individual Django apps.
    *   The `requirements.txt` file lists all Python dependencies.
*   **Frontend:**
    *   The frontend uses Next.js with TypeScript.
    *   The `src` directory contains the main application code.
    *   The `package.json` file lists all JavaScript dependencies and defines scripts for running, building, and linting the application.
    *   Styling is done with Tailwind CSS.
*   **API:**
    *   The API is built with the Django REST Framework.
    *   Authentication is token-based.
    *   The API is versioned.
*   **Documentation:**
    *   The `docs` directory contains important project documentation, including the product roadmap and architecture plans.

