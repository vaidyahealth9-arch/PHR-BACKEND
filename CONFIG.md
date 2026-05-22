PHR Backend — Configuration Guide

Purpose
- Document environment file usage, key variables, and run commands for the FastAPI backend.

Env files
- `.env.example` — template (committed)
- `.env` — local non-secret defaults
- `.env.local` — developer overrides (gitignored)

Precedence (highest → lowest)
1. Process environment variables (Docker/Compose/CI)
2. `.env.local`
3. `.env.development` / `.env.production`
4. `.env`

Key environment vars
- `DATABASE_URL` — DB connection string
- `SECRET_KEY` — application secret (must be strong in production)
- `RUN_SEED_DATA` — `true` to populate sample data on startup (dev-only)
- `LIMS_BASE_URL` — URL to LIMS when integrating locally

Standard commands
- `dev` (local): `uvicorn main:app --reload --host 0.0.0.0 --port 8000`
- `start` (non-dev): `uvicorn main:app --host 0.0.0.0 --port 8000`
- Docker: `docker compose up -d --build` (from `phr/` root)

Notes
- The `Dockerfile` runs `seed_local_db.py` when `RUN_SEED_DATA=true` — be cautious running that in shared environments.
- Keep secrets out of committed files and use a secret manager for production.
