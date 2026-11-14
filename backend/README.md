# Backend — MyNest Design Studio

Python + FastAPI + Uvicorn.

## Setup

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# macOS/Linux:        source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

- API root docs: http://localhost:8000/docs
- Health check: http://localhost:8000/api/health

## Endpoints

| Method | Path | Response |
|--------|------|----------|
| GET | `/api/health` | `{ "status": "ok" }` |

## Structure

```
backend/
├── app/
│   ├── __init__.py
│   └── main.py       FastAPI application
├── requirements.txt
└── README.md
```

## Development tooling

Install dev dependencies (linter, formatter, type checker, tests):

```bash
pip install -r requirements-dev.txt
```

| Command | Purpose |
|---------|---------|
| `ruff check .` | Lint |
| `ruff format .` | Format code (Ruff, Black-compatible) |
| `mypy .` | Static type checking (strict) |
| `pytest` | Run tests |

Configuration lives in `pyproject.toml`.
