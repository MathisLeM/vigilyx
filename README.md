# Vigilyx

Proactive anomaly detection for Stripe revenue metrics. Vigilyx pulls your transaction data from Stripe, computes daily KPI snapshots, and automatically surfaces anomalies (revenue spikes, drops, refund surges, chargeback patterns) using MAD + Z-score detectors gated by a per-account Isolation Forest — grouped by day with AI-style combo analysis.

## Architecture

```
vigilyx/
├── app/                    # FastAPI backend
│   ├── models/             # SQLAlchemy models (tenants, alerts, metrics, stripe_connections, ...)
│   ├── routers/            # API endpoints (auth, alerts, metrics, config, ingestion)
│   ├── services/
│   │   ├── detection/      # MAD + Z-score detectors + Isolation Forest gating layer
│   │   └── ingestion/      # Stripe data ingestion pipeline
│   ├── config.py           # Environment settings (pydantic-settings)
│   ├── database.py         # SQLAlchemy engine + session
│   └── scheduler.py        # APScheduler: ingestion + detection + nightly model retraining
├── frontend/               # Next.js 14 (App Router) dashboard
│   ├── app/
│   │   ├── dashboard/      # Main KPI + alerts view, per-account filtering
│   │   ├── profile/        # Stripe connections, ingestion, Slack, AI model, team
│   │   └── login/
│   ├── components/         # KPICards, KPIChart, AlertsTable, NavSidebar
│   └── lib/                # api.ts (typed fetch wrappers), auth.tsx (cookie-based auth)
├── models/                 # Trained model artifacts (.pkl) — gitignored, regenerate locally
├── scripts/                # train_base_model.py — trains the synthetic base IF model
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
git clone https://github.com/MathisLeM/vigilyx.git
cd vigilyx

cp .env.example .env
# Edit .env — set SECRET_KEY and FERNET_KEY (see below)
```

Generate required secrets:
```bash
# SECRET_KEY (JWT signing)
python -c "import secrets; print(secrets.token_hex(32))"

# FERNET_KEY (encrypts Stripe API keys at rest)
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 2. Install backend dependencies

```bash
pip install -r requirements.txt
```

### 3. Train the base Isolation Forest model

The base model is a synthetic fallback used before enough real data is collected (< 30 days per account).

```bash
python scripts/train_base_model.py
```

### 4. Seed the database with demo data

Creates two demo tenants with ~90 days of simulated Stripe-like revenue data, demo Stripe connections, and initial anomaly detection.

```bash
python simulation/seed_demo.py
```

Demo accounts created:
| Email | Password | Role |
|-------|----------|------|
| `admin@demo.com` | `admin1234` | Admin (sees all tenants) |
| `acme@demo.com` | `demo1234` | Acme SaaS |
| `globex@demo.com` | `demo1234` | Globex Commerce |

### 5. Start the backend

```bash
uvicorn main:app --reload
```

API available at: `http://localhost:8000`
Swagger docs: `http://localhost:8000/docs`

### 6. Configure the frontend

```bash
cd frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
npm install
npm run dev
```

Dashboard available at: `http://localhost:3000`

## Using with Real Stripe Data

1. Log in as a company account (not admin)
2. Go to **Profile → Stripe Connections** → add a connection (name + secret key)
3. Click **Test** to verify the key and link the Stripe account ID
4. Go to **Profile → Data Ingestion** → click **Sync** to pull transaction history
5. Go back to **Dashboard** → click **Run Detection** to generate alerts
6. Once you have 30+ days of data, go to **Profile → AI Model** → click **Train model**

The scheduler runs ingestion and detection automatically every hour, and retrains models nightly at 03:00 UTC.

## Key Features

- **Multi-tenant**: Each company sees only its own data
- **Multi-Stripe-account**: Each tenant can connect up to 5 Stripe accounts; all data and alerts are scoped per account
- **Isolation Forest gating**: MAD + Z-score anomalies are confirmed by a per-account IF model before being persisted — reduces false positives. Falls back to a pre-trained synthetic base model until 30 days of real data are available
- **Dual-confirmation alerts**: When both MAD and Z-score fire on the same metric, a single `DUAL` alert is created with bumped severity
- **Daily grouping**: Alerts are grouped by date with a combo-hint engine that identifies patterns (outage, fraud wave, billing error, enterprise deal, etc.)
- **Accordion UI**: Click a day row to expand all anomalies with per-metric explanations
- **Slack notifications**: Configurable severity filter (HIGH / Med+High / All)
- **Team invitations**: Invite teammates by email; they join your tenant directly

## Roadmap

**Production hardening**
- [x] PostgreSQL migration + Alembic migrations
- [x] Stripe API key encryption at rest (Fernet)
- [x] Slack webhook alerting — configurable severity filter (HIGH / Med+High / All)
- [x] CORS + SECRET_KEY locked down for production domain
- [x] Rate limiting on login (brute-force protection)
- [x] API docs disabled in production
- [x] httpOnly cookie auth — session tokens invisible to JavaScript (XSS-proof)
- [x] Invitation tokens secured — raw token returned only at creation, never in list endpoint
- [ ] Email alerting
- [ ] Deploy (Neon + EC2 + Vercel)

**ML model layer** *(hosted inline in FastAPI — requires ≥ 1 GB RAM server)*
- [x] Isolation Forest detector — unsupervised anomaly gating per account, augments MAD+Z-score
- [x] Per-account model training pipeline — scheduled nightly via APScheduler; base synthetic model as fallback
- [ ] LSTM forecasting — predict next-day metric values, alert when actual deviates from forecast
- [ ] Model artifact storage — serialized models (.pkl / .pt) persisted to S3/R2 or local volume
- [ ] Model versioning — track which model version produced each alert

**Platform**
- [x] Multi-Stripe-account per tenant (up to 5 connections, per-account data isolation)
- [x] Team invitations (invite by email, role-based access)
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

**Backend**: FastAPI · SQLAlchemy · Alembic · APScheduler · pandas · scikit-learn · stripe-python · python-jose · cryptography
**Frontend**: Next.js 14 · Tailwind CSS · Recharts · date-fns
**Database**: SQLite (local) → PostgreSQL (production)
**ML**: scikit-learn (Isolation Forest) · PyTorch (LSTM, planned) — served inline in FastAPI
