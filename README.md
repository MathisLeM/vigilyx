# Vigilyx

Proactive anomaly detection for Stripe revenue metrics. Vigilyx pulls your transaction data from Stripe, computes daily KPI snapshots, and automatically surfaces anomalies (revenue spikes, drops, refund surges, chargeback patterns) using MAD and Z-score detectors — grouped by day with AI-style combo analysis.

## Architecture

```
vigilyx/
├── app/                    # FastAPI backend
│   ├── models/             # SQLAlchemy models (tenants, alerts, metrics, ...)
│   ├── routers/            # API endpoints (auth, alerts, metrics, config, ingestion)
│   ├── services/
│   │   ├── detection/      # MAD + Z-score anomaly detectors
│   │   └── ingestion/      # Stripe data ingestion pipeline
│   ├── config.py           # Environment settings (pydantic-settings)
│   ├── database.py         # SQLAlchemy engine + session
│   └── scheduler.py        # APScheduler: hourly ingestion + daily detection
├── frontend/               # Next.js 14 (App Router) dashboard
│   ├── app/
│   │   ├── dashboard/      # Main KPI + alerts view
│   │   ├── profile/        # Stripe key config + ingestion trigger
│   │   └── login/
│   ├── components/         # KPICards, KPIChart, AlertsTable, NavSidebar
│   └── lib/                # api.ts (typed fetch wrappers), auth.tsx (JWT context)
├── simulation/             # seed_demo.py — seeds DB with simulated Stripe data
├── data_contracts/         # Stripe-aligned Pydantic schemas
├── .env.example            # Required environment variables
└── requirements.txt
```

## Requirements

- Python 3.11+
- Node.js 18+
- pip

## Local Setup

### 1. Clone and configure environment

```bash
git clone https://github.com/YOUR_USERNAME/vigilyx.git
cd vigilyx

cp .env.example .env
# Edit .env and set a strong SECRET_KEY
```

Generate a secure `SECRET_KEY`:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Seed the database with demo data

This creates two demo tenants (Acme Corp, Globex Inc) with ~90 days of simulated Stripe-like revenue data and runs initial anomaly detection.

```bash
python simulation/seed_demo.py
```

Demo accounts created:
| Email | Password | Role |
|-------|----------|------|
| `admin@demo.com` | `admin1234` | Admin (sees all tenants) |
| `acme@demo.com` | `demo1234` | Acme Corp |
| `globex@demo.com` | `demo1234` | Globex Inc |

### 4. Start the backend

```bash
uvicorn main:app --reload
```

API available at: `http://localhost:8000`
Swagger docs: `http://localhost:8000/docs`

### 5. Configure the frontend

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev
```

Dashboard available at: `http://localhost:3000`

## Using with Real Stripe Data

1. Log in as a company account (not admin)
2. Go to **Profile** → paste your Stripe secret key (`sk_live_...` or `sk_test_...`)
3. Click **Test connection** to verify
4. Click **Sync (incremental)** to pull transaction data
5. Go back to **Dashboard** → click **Run Detection** to generate alerts

The scheduler also runs ingestion and detection automatically every 24 hours.

## Key Features

- **Multi-tenant**: Each company sees only its own data
- **Dual-confirmation alerts**: When both MAD and Z-score fire on the same metric, a single `DUAL` alert is created with bumped severity
- **Daily grouping**: Alerts are grouped by date with a combo-hint engine that identifies patterns (outage, fraud wave, billing error, enterprise deal, etc.)
- **Accordion UI**: Click a day row to expand all anomalies with per-metric explanations

## Roadmap

**Production hardening**
- [ ] PostgreSQL migration + Alembic migrations
- [ ] Stripe API key encryption at rest (Fernet)
- [ ] Email / Slack webhook alerting on HIGH severity alerts
- [ ] CORS + SECRET_KEY locked down for production domain

**ML model layer** *(hosted inline in FastAPI — requires ≥ 1 GB RAM server)*
- [ ] Isolation Forest detector — unsupervised anomaly scoring per metric, replaces/augments MAD+Z-score
- [ ] Per-tenant model training pipeline — scheduled via APScheduler after ingestion
- [ ] LSTM forecasting — predict next-day metric values, alert when actual deviates from forecast
- [ ] Model artifact storage — serialized models (.pkl / .pt) persisted to S3/R2 or local volume
- [ ] Model versioning — track which model version produced each alert

**Platform**
- [ ] Multi-currency support (EUR, GBP normalisation)
- [ ] CSV / PDF export of alerts and KPI snapshots
- [ ] Tenant self-registration flow (no manual DB seeding)
- [ ] Admin dashboard: cross-tenant anomaly overview

## Infrastructure (production)

| Component | Recommended service | Notes |
|-----------|-------------------|-------|
| Backend + ML model | Hetzner CX21 (€4/mo) or Railway Pro | Needs ≥ 1 GB RAM for model inference |
| Frontend | Vercel | Free tier, auto-deploy from GitHub |
| Database | Neon / Supabase (PostgreSQL) | Free tier sufficient to start |
| Model artifacts | Cloudflare R2 or S3 | Downloaded at server startup |

## Tech Stack

**Backend**: FastAPI · SQLAlchemy · Alembic · APScheduler · pandas · scikit-learn · stripe-python · python-jose
**Frontend**: Next.js 14 · Tailwind CSS · Recharts · date-fns
**Database**: SQLite (local) → PostgreSQL (production)
**ML**: scikit-learn (Isolation Forest) · PyTorch (LSTM) — served inline in FastAPI
