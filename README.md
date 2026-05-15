# Data Platform — Insurance Data Intelligence MVP

AI-powered data intelligence and cleaning platform for insurance datasets.
Built for pricing analysts, underwriters, MGA/brokerage operations teams,
and middle-office data professionals.

---

## Project Structure

```
/
├── backend/          FastAPI backend
├── frontend/         React + Vite + TypeScript + Tailwind frontend
├── data/samples/     Realistic sample insurance CSV files for testing
└── docs/             Architecture and design notes (added in later stages)
```

---

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.11+ | [python.org](https://python.org) |
| Node.js | 18+ | [nodejs.org](https://nodejs.org) |
| Java | 11 or 17 | **Only needed for Spark mode** — [Adoptium](https://adoptium.net) |

---

## Quick Start

### 1. Backend

```bash
cd backend

# Create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows

# Install dependencies
pip install -r requirements.txt

# Copy the environment file and edit if needed
cp .env.example .env

# Run the API server
uvicorn main:app --reload
```

The API will be available at **http://localhost:8000**.

Swagger docs: **http://localhost:8000/docs**

### 2. Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start the development server
npm run dev
```

The UI will be available at **http://localhost:5173**.

The Vite dev server proxies all `/api/*` requests to the FastAPI backend,
so no CORS configuration is needed during development.

---

## Engine Modes

The platform is designed around a data processing engine abstraction.
The same feature logic runs through either engine — only the engine
implementation differs.

### Pandas mode (default)

Best for: local development, small to medium datasets, rapid iteration.

```env
# backend/.env
ENGINE_MODE=pandas
```

- No extra dependencies beyond `requirements.txt`
- Fast startup — no JVM overhead
- Supports datasets up to ~1 million rows comfortably

### Spark mode

Best for: large datasets, production workloads, Databricks environments.

```env
# backend/.env
ENGINE_MODE=spark
```

**Additional setup required:**

1. Install Java 11 or 17 and confirm it is on your PATH:
   ```bash
   java -version
   ```

2. Install PySpark:
   ```bash
   pip install pyspark>=3.5.0
   ```

3. Set `ENGINE_MODE=spark` in `backend/.env` and restart the server.

**Note:** Spark has a JVM startup cost of ~15–20 s on the first request
when running locally. For rapid iteration on small files, use pandas mode.

### How to switch between engines

Edit `backend/.env`:

```env
ENGINE_MODE=pandas   # lightweight, default
ENGINE_MODE=spark    # distributed, production-scale
```

Restart the backend server after changing this value. The API response
format is identical regardless of which engine is active — the
`engine_used` field in the upload response tells you which was used.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| GET | `/api/v1/health` | Health check — returns status and active engine mode |
| POST | `/api/v1/datasets/upload` | Upload one or more CSV/Excel files |

---

## Sample Datasets

Three sample files are included in `data/samples/` for testing.
They contain deliberate quality issues that will be detected in Stage 2.

| File | Rows | Description |
|---|---|---|
| `policies.csv` | 25 | Policy records with mixed date formats, inconsistent casing, and null premiums/postcodes |
| `claims.csv` | 20 | Claims data with null amounts, orphaned policy reference (CLM-020 → POL-026 does not exist) |
| `quotes.csv` | 20 | Quotes with cross-dataset fill opportunities and entity mismatch (QT-020 has different postcode to POL-020) |

**Intentional quality issues planted for later stages:**

- Mixed date formats: ISO (`2023-01-15`), UK (`15/03/2023`), long-form (`April 5 2023`)
- Inconsistent product type casing: `Motor`, `motor`, `MOTOR`, `home`, `TRAVEL`
- Null premiums in `policies.csv` (POL-007, POL-014, POL-024) — fillable from `quotes.csv`
- Null postcode in `policies.csv` (POL-009, POL-017) — POL-009 fillable from `quotes.csv` (QT-009)
- Ghost join in `claims.csv`: CLM-020 references POL-026 which does not exist in policies
- Entity mismatch: POL-020 postcode is `HG1 1BB` but QT-020 postcode is `HG1 2BB`
- Null NCD in multiple policy rows
- Null claim amounts and descriptions in `claims.csv`

---

## Build Stages

| Stage | Description | Status |
|---|---|---|
| **Stage 1** | Project scaffold, upload flow, engine abstraction | ✅ Complete |
| Stage 2 | Dataset profiling, reliability scoring, UI results | Pending |
| Stage 3 | Cross-dataset null resolution, interpolation engine | Pending |
| Stage 4 | Human-in-the-loop review interface, audit log | Pending |
| Stage 5 | Export cleaned CSV, LLM analyst summary | Pending |
| Stage 6 | UI polish, demo flow | Pending |
