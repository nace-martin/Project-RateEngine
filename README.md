# Project-RateEngine 

# RateEngine MVP 🚚

RateEngine is an internal web application designed to streamline and automate the air freight quoting process for freight forwarders.

> For a detailed breakdown of the current project status, architecture, and future roadmap, please see the [**Project Brief (docs/PROJECT_BRIEF.md)**](./docs/PROJECT_BRIEF.md).

---

## ## Technology Stack

This project is a modern full-stack application built with a separate backend and frontend.

* **Backend:** Python with **Django** & **Django REST Framework**
* **Frontend:** JavaScript with **Next.js (React)** & **TypeScript**
* **Styling:** **Tailwind CSS**
* **Database:** **SQLite** (for development), **PostgreSQL** (for production)

---

## ## Getting Started

To get the project running on your local machine, you will need two separate terminals.

### **Prerequisites**

* [Python 3.10+](https://www.python.org/downloads/)
* [Node.js 18+](https://nodejs.org/en)
* [Git](https://git-scm.com/downloads/)

### **Terminal 1: Run the Backend Server**

1.  **Navigate to the backend directory:**
    ```bash
    cd backend
    ```

2.  **Activate the virtual environment:**
    ```bash
    # On Windows
    .\venv\Scripts\activate
    ```

3.  **Run the database migrations:**
    ```bash
    python manage.py migrate
    ```

4.  **Start the Django server:**
    ```bash
    python manage.py runserver
    ```
    > The backend API will now be running at `http://127.0.0.1:8000`. The admin panel is at `http://127.0.0.1:8000/admin`.

### **Terminal 2: Run the Frontend Server**

1.  **Navigate to the frontend directory:**
    ```bash
    cd frontend
    ```

2.  **Install dependencies (only needed the first time):**
    ```bash
    npm install
    ```

3.  **Start the Next.js server:**
    ```bash
    npm run dev
    ```
    > The frontend application will now be running at `http://localhost:3000`.
````