# MyNest Design Studio

## 1. Project Overview

MyNest Design Studio is an interior-design workspace that will take a floor plan
through deterministic 2D geometry, furniture layout, design versioning, and AI
photorealistic visualization — while keeping the floor-plan geometry as the single
source of truth (AI is only a visualizer, never authoritative for geometry).

**Current state:** this repository contains the project foundation only — a React +
TypeScript + Vite frontend and a FastAPI backend, wired together through a health
check. The frontend displays whether the backend is reachable.

> **Future phases (planned, _not_ implemented):** floor-plan upload & geometry,
> the 2D design canvas, the furniture library, drag/resize/rotate editing,
> validation & design rules, canonical design JSON, design versioning, AI
> visualization providers, the generation gallery, and export. These are described
> in `docs/ARCHITECTURE.md` and are not part of the current build.

## 2. Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React · TypeScript · Vite |
| Frontend tooling | ESLint (flat config), TypeScript strict mode |
| Backend | Python · FastAPI · Uvicorn |
| Backend tooling | Ruff (format + lint), mypy (strict), pytest |

Planned for future phases (not yet used): PostgreSQL, Redis, Celery, S3-compatible
storage, Konva/react-konva, and AI provider integrations.

## 3. Folder Structure

```
mynest-design-studio/
├── frontend/                 React + TypeScript + Vite app
│   ├── src/
│   │   ├── components/        (empty — future UI components)
│   │   ├── features/          (empty — future feature modules)
│   │   ├── lib/
│   │   │   └── api.ts         API service (calls /api/health)
│   │   ├── store/             (empty — future state slices)
│   │   ├── types/             (empty — future shared types)
│   │   ├── styles/index.css
│   │   ├── App.tsx            root component (backend status)
│   │   └── main.tsx           entry point
│   ├── public/
│   ├── index.html
│   ├── vite.config.ts         dev server + /api proxy
│   ├── tsconfig.json          TypeScript strict config
│   ├── eslint.config.js
│   ├── package.json
│   └── .env.example
├── backend/                  Python + FastAPI service
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            FastAPI app + /api/health
│   │   ├── models/            (empty — future persistence models)
│   │   ├── schemas/           (empty — future request/response schemas)
│   │   └── services/          (empty — future service boundaries)
│   ├── tests/
│   │   └── test_health.py
│   ├── requirements.txt       runtime dependencies
│   ├── requirements-dev.txt   dev dependencies (ruff, mypy, pytest)
│   ├── pyproject.toml         formatting / linting / type-check config
│   └── .env.example
├── docs/
│   └── ARCHITECTURE.md
└── README.md
```

## 4. How to Install the Frontend

```bash
cd frontend
npm install
cp .env.example .env   # optional — not required for local development
```

## 5. How to Install the Backend

```bash
cd backend
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env   # optional — not required for the health endpoint
```

## 6. How to Run the Frontend

```bash
cd frontend
npm run dev
```

Runs the Vite dev server at http://localhost:5173. Requests to `/api/*` are proxied
to the backend at http://localhost:8000 (see `vite.config.ts`), so start the backend
too for the status to show **Connected**.

## 7. How to Run the Backend

```bash
cd backend
# activate the virtualenv first (see step 5)
uvicorn app.main:app --reload
```

Runs the API at http://localhost:8000. Interactive docs are at
http://localhost:8000/docs.

## 8. API Health Endpoint

The only endpoint currently implemented:

```
GET /api/health
```

**Response** — `200 OK`:

```json
{
  "status": "ok"
}
```

The frontend calls this on load and shows **Backend Status: Connected** when it
responds successfully, or **Disconnected** when the API cannot be reached.
