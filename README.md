# Araneos

**The High-Integrity Data Engine for Insurance Brokers**

---

## Executive summary

Insurance brokers sit on fragmented spreadsheets, policy feeds, and claims files that rarely line up perfectly—**sequence gaps** in identifiers, **silent nulls** that should have been filled from another system, and **no single place** to prove the firm acted in customers’ best interests. **Araneos** is a broker-grade **data health engine** that profiles uploads, scores reliability, proposes **human-reviewed** fixes, and surfaces **joinable intelligence** across datasets.

The backend runs a configurable **processing engine**: **Pandas** for fast local iteration (default), or **PySpark** for distributed, production-scale runs (`ENGINE_MODE=spark`). That stack turns messy CSV/Excel into **audit-ready outputs**—scored datasets, explainable proposals, and export bundles with a **decision manifest**—so leadership can stand behind both **operational quality** and **outcomes-focused oversight** aligned with **FCA Consumer Duty** expectations (clear, fair, not misleading; supporting good customer outcomes through demonstrable controls).

---

## Core capabilities (from the codebase)


| Capability                                 | What it does                                                                                                                                                                     |
| ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Dataset profiling**                      | Engine-agnostic column stats, type inference, duplicate detection, and dataset-level issues (`app/features/profiling.py`).                                                       |
| **Reliability scoring**                    | 0–100 score with Green / Amber / Red grades and per-penalty explanations (`app/features/scoring.py`, `insurance_fields.SCORING_CONFIG`).                                         |
| **Cross-dataset null resolution**          | Detects join keys and proposes fills when another file in the same session has non-null values (`app/features/null_resolution.py`).                                              |
| **Conservative sequence & date inference** | Strict rules for annual policy date pairs and sequential identifier gaps—no reckless numeric interpolation between unrelated rows (`app/features/interpolation.py`).             |
| **Rule-based data corrections**            | Postcode, whitespace, product casing, date standardisation, currency cleaning, premium floors, and related business rules—all as proposals (`app/features/data_corrections.py`). |
| **Analyst-configurable rules**             | Tunable thresholds (e.g. max NCD) passed with upload (`app/features/analyst_rules.py`).                                                                                          |
| **Proposal workflow**                      | Pending → approved/rejected with human-in-the-loop review; standard cleaning types can be grouped (`app/features/review.py`, `proposals.py`).                                    |
| **Session export**                         | ZIP of cleaned CSVs plus **audit_manifest.csv** covering every proposal decision (`app/features/export.py`).                                                                     |
| **Join intelligence**                      | Pairwise join detection, match-quality signals, rule-based insight catalogue, and aggregation tables for selected insights (`app/features/join_intelligence.py`).                |
| **CTO dashboard**                          | Executive roll-up of health scores, alerts, join opportunities, trend context, and downloadable HTML report (`app/features/cto_dashboard.py`).                                   |
| **Analysis pipeline**                      | End-to-end orchestration from upload through profiling, scoring, resolutions, and proposal persistence (`app/features/pipeline.py`).                                             |


**Product surface (React):** upload flow, profiling/score results, proposal review, join insights, and the CTO dashboard (`frontend/src/pages`).

---

## Project structure

```
Spiderman/
├── backend/                 # FastAPI service, feature modules, engines, SQLite
│   ├── main.py              # App factory, CORS, router mount, startup DB init
│   ├── requirements.txt     # Python dependencies (PySpark installed separately)
│   ├── uploads/             # Persisted uploads (gitignored data; .gitkeep present)
│   └── app/
│       ├── api/routes/      # REST: health, upload, proposals, sessions
│       ├── core/            # Settings (engine mode, paths) + insurance field config
│       ├── engines/         # PandasEngine, SparkEngine, engine selector
│       ├── features/        # Profiling, scoring, null resolution, joins, dashboard, …
│       ├── models/          # SQLAlchemy models + SQLite engine/session
│       ├── services/        # Reserved for future service layer
│       └── utils/           # Shared helpers
├── data/
│   └── samples/             # Example broker CSVs (policies, claims, quotes, risk factors)
├── frontend/                # Vite + React + TypeScript + Tailwind UI
│   ├── src/
│   │   ├── api/             # Typed client for `/api/v1`
│   │   ├── components/      # Tables, workflow, navbar, drop zone, …
│   │   └── pages/           # Upload, results, proposals, joins, CTO dashboard
│   ├── vite.config.ts       # Dev server + `/api` proxy to FastAPI
│   └── tailwind.config.js   # Tailwind CSS configuration
└── README.md                # This file
```


| Path                         | One-line purpose                                                         |
| ---------------------------- | ------------------------------------------------------------------------ |
| `backend/main.py`            | FastAPI entrypoint and API composition.                                  |
| `backend/app/api/routes/`    | HTTP handlers for upload, proposals, sessions, health.                   |
| `backend/app/core/`          | Environment-driven `Settings` and domain constants (`insurance_fields`). |
| `backend/app/engines/`       | Pluggable **Pandas** vs **PySpark** execution backends.                  |
| `backend/app/features/`      | Domain logic: profiling, scoring, pipeline, joins, dashboard, export.    |
| `backend/app/models/`        | ORM models and SQLite `data_platform.db` wiring.                         |
| `backend/uploads/`           | Stored upload files referenced by session rows.                          |
| `data/samples/`              | Reference CSVs for local demos and tests.                                |
| `frontend/src/pages/`        | Routed views for each major workflow stage.                              |
| `frontend/src/components/`   | Reusable UI for stats, issues, proposals, and navigation.                |
| `frontend/src/api/client.ts` | API types and fetch helpers for the backend.                             |


---

## Tech stack


| Layer           | Technology                                                                                             |
| --------------- | ------------------------------------------------------------------------------------------------------ |
| **API**         | **Python 3** · **FastAPI** · **Uvicorn**                                                               |
| **Data engine** | **Pandas** / **NumPy** / **SciPy** (default) · **PySpark** (optional, `pip install pyspark`, Java 11+) |
| **Persistence** | **SQLAlchemy** · **SQLite** (`./data_platform.db`)                                                     |
| **Frontend**    | **React 18** · **TypeScript** · **Vite**                                                               |
| **Styling**     | **Tailwind CSS**                                                                                       |
| **Routing**     | **react-router-dom**                                                                                   |


---

## The Intelligence Layer (vision)

Today, Araneos emphasises **deterministic**, **explainable** rules and metrics—ideal for regulated workflows. The roadmap extends into an **intelligence layer**:

- **Local LLMs (e.g. Ollama)** for policy-aware natural language explanations, analyst copilots, and assistive drafting—**without** sending client data to opaque third parties when run on-prem or in a controlled VPC.
- **Swarm-style multi-agent orchestration** to combine specialist evaluators (data quality, pricing fairness signals, join coverage) into **unified market and portfolio insights**—supporting faster, evidence-backed decisions.

The current codebase already separates **engines**, **feature modules**, and **API routes**, so these capabilities can land as additive services without rewriting the core health pipeline.

---

## Getting started

### Prerequisites

- **Python** 3.11+ recommended  
- **Node.js** 18+ and npm  
- **Java 11+** (only if enabling PySpark)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Optional: Spark mode for large-scale / distributed processing
# pip install "pyspark>=3.5.0"
# echo 'ENGINE_MODE=spark' >> .env

uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: `GET http://localhost:8000/api/v1/health`  
- API prefix: `/api/v1` (see `app/core/config.py`)

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open **[http://localhost:5173](http://localhost:5173)**. The Vite dev server **proxies** `/api` to `http://localhost:8000`, matching the backend CORS setup.

### Sample data

Use the CSVs under `data/samples/` when exercising multi-file sessions (e.g. policies, claims, quotes, risk factors).

---

## License & contact

*Add your license and company contact details here as the project matures.*

---

*Built for brokers who care about defensible data—and leaders who need to prove it.*
