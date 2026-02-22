# Vigilyx — Deployment Guide

Stack: **Railway** (backend) · **Vercel** (frontend) · **Supabase** (PostgreSQL) · **Cloudflare R2** (model artifacts)

---

## Overview

```
GitHub repo
  ├── Railway  ← FastAPI + APScheduler + scikit-learn (always-on)
  ├── Vercel   ← Next.js frontend (auto-deploy on push)
  ├── Supabase ← Managed PostgreSQL (Alembic runs at startup)
  └── R2       ← .pkl model files (downloaded at startup, uploaded after retraining)
```

> **Model artifacts note:** R2 upload/download is not yet wired in code.
> Until it is, add a Railway Volume mounted at `/app/models` so `.pkl` files
> survive redeploys (see Step 3c).

---

## Step 1 — Supabase (PostgreSQL)

1. Go to [supabase.com](https://supabase.com) → **New project**
   - Choose a region close to your Railway region
   - Save the database password — you won't see it again

2. Once the project is ready: **Project Settings → Database → Connection string → URI**
   Copy the URI. It looks like:
   ```
   postgresql://postgres:[YOUR-PASSWORD]@db.[YOUR-REF].supabase.co:5432/postgres
   ```

3. That's your `DATABASE_URL`. Keep it — you'll paste it into Railway in Step 3.

> **Free tier caveat:** Supabase pauses projects after 7 days of inactivity.
> For production, upgrade to Pro ($25/mo) or use [Neon](https://neon.tech) (auto-resumes on connection, free tier).

---

## Step 2 — Cloudflare R2 (model artifacts)

1. Go to [dash.cloudflare.com](https://dash.cloudflare.com) → **R2 Object Storage → Create bucket**
   - Name: `vigilyx-models`
   - Region: automatic

2. On the R2 overview page, note your **Account ID** (top right of the R2 page).

3. **Manage R2 API Tokens → Create API Token**
   - Permissions: **Object Read & Write**
   - Scope: `vigilyx-models` bucket only
   - Save the **Access Key ID** and **Secret Access Key** — shown once only

4. Your R2 endpoint:
   ```
   https://[ACCOUNT_ID].r2.cloudflarestorage.com
   ```

> These credentials will be added to Railway env vars.
> Until R2 upload/download is coded, Railway Volumes keep models persistent (Step 3c).

---

## Step 3 — Railway (FastAPI backend)

### 3a. Create the project

1. Go to [railway.app](https://railway.app) → **New Project → Deploy from GitHub repo**
2. Select the `vigilyx` repository
3. Railway auto-detects Python via `requirements.txt` and uses `railway.toml` for the start command

### 3b. Set environment variables

In Railway: **your service → Variables → Add all of the following**

```
# Required
ENVIRONMENT=production
DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres
SECRET_KEY=<generate: python -c "import secrets; print(secrets.token_hex(32))">
FERNET_KEY=<generate: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())">

# CORS — set to your Vercel URL (fill in after Step 4)
ALLOWED_ORIGINS=https://your-app.vercel.app

# Email alerts (optional — leave blank to disable)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASS=your-app-password
FROM_EMAIL=Vigilyx <alerts@yourdomain.com>
APP_URL=https://your-app.vercel.app

# Cloudflare R2 (optional until R2 integration is coded)
R2_ACCOUNT_ID=
R2_ACCESS_KEY_ID=
R2_SECRET_ACCESS_KEY=
R2_BUCKET_NAME=vigilyx-models
```

> `DATABASE_URL` pointing to PostgreSQL triggers `alembic upgrade head` automatically
> at startup — all tables and migrations are applied without any manual step.

### 3c. Add a Volume for model persistence

Without persistent storage, `.pkl` model files are lost every redeploy.

1. Railway service → **Volumes → Add Volume**
2. Mount path: `/app/models`
3. Size: 1 GB (sufficient for scikit-learn `.pkl` files)

This keeps trained models across deploys until R2 upload/download is implemented.

### 3d. Verify the deploy

Once deployed, check:
```
https://your-backend.railway.app/health
# → {"status": "ok", "version": "0.5.0"}
```

The first deploy will:
- Install dependencies from `requirements.txt`
- Run `alembic upgrade head` (creates all tables in Supabase)
- Start APScheduler
- Load or train the base Isolation Forest model

---

## Step 4 — Vercel (Next.js frontend)

1. Go to [vercel.com](https://vercel.com) → **New Project → Import Git Repository**
2. Select the `vigilyx` repo
3. **Root Directory:** set to `frontend`
   - Vercel auto-detects Next.js — no build command changes needed
4. **Environment Variables → Add:**
   ```
   NEXT_PUBLIC_API_URL=https://your-backend.railway.app
   ```
5. Click **Deploy**

Once deployed, copy your Vercel URL (e.g. `https://vigilyx.vercel.app`) and:
- Go back to Railway → update `ALLOWED_ORIGINS` and `APP_URL` to this URL
- Trigger a Railway redeploy (Variables → any save triggers redeploy)

---

## Step 5 — Seed demo data (optional)

To populate Supabase with demo tenants and metrics, run the seed script once
with the production `DATABASE_URL`:

```bash
DATABASE_URL="postgresql://postgres:..." python simulation/seed_demo.py
```

Or connect to Railway's shell: **Railway service → Shell** and run it there.

---

## Post-deploy checklist

- [ ] `https://your-backend.railway.app/health` returns `{"status": "ok"}`
- [ ] Frontend loads at Vercel URL and login works
- [ ] `ALLOWED_ORIGINS` on Railway matches the Vercel URL exactly (no trailing slash)
- [ ] `APP_URL` on Railway matches Vercel URL (used in email verification links)
- [ ] SMTP email: save an email config in Profile → Email Alerts and confirm you receive the verification email
- [ ] Train the base model via Profile → AI Model → Train model (or wait for nightly scheduler)
- [ ] Add a real Stripe connection via Profile → Stripe Connections → Add

---

## Cost summary

| Service | Tier | Monthly |
|---------|------|---------|
| Railway | Hobby ($5 seat + usage ~$2–5) | ~$7–10 |
| Vercel | Free (Hobby) | $0 |
| Supabase | Free (pauses after inactivity) / Pro | $0 / $25 |
| Cloudflare R2 | Free (10 GB, 10M reads) | $0 |
| **Total** | | **~$7–10 (free DB) / ~$32–35 (Pro DB)** |
