# Kaam Ka AI — Instagram Business Agent

An approval-first agent that plans, creates and publishes Instagram content for a faceless
"practical AI tools" brand, and tracks costs and revenue honestly.

**Status: Phase 3 foundation.** Backend API, database schema, approval workflow, owner-only
policies, monthly budget cap, duplicate-safe publish worker (dry run only), revenue ledger,
audit log with secret redaction, Docker image and CI. 32 automated tests pass.
Not yet built: dashboard UI (Phase 5), AI generation (Phase 4), Instagram connection (Phase 6),
Azure deployment (Phase 10).

## Safety rules enforced in code

| Rule | Where |
|---|---|
| Only the owner (your Entra ID email) can call the API, approve, reject or change policies | `app/security.py`, `services/approvals.py`, `services/policy.py` |
| The agent can request actions but never approve them or change policies | `services/approvals.py`, `services/policy.py` |
| Nothing reaches Instagram outside production — always a dry run | `services/publishing.get_publisher` |
| Each approved post publishes at most once (idempotency key + conditional claim) | `services/publishing.py` |
| Rolling 24-hour post cap (default 3) | `KA_MAX_POSTS_PER_DAY` |
| Monthly spend cap blocks paid AI calls before they happen | `services/budget.py` |
| Affiliate posts need #Ad/#Affiliate in the first 150 characters | `services/approvals.check_post_ready` |
| Confirmed revenue needs evidence; estimates are reported separately | `services/revenue.py` |
| Secrets redacted from the audit log; no secret defaults in config | `services/audit.redact`, `app/config.py` |
| Dev sign-in bypass refused in production | `Settings.validate_for_runtime` |

## Run it locally

Requires Python 3.13.

```bash
cd backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env                                  # then set KA_OWNER_EMAIL
python -m pytest -q                                      # expect: 32 passed
uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000/api/docs to try the API, or run the publish job once:

```bash
python -m app.jobs publish      # prints a dry-run result; never posts to Instagram
```

## Push to your GitHub

1. On github.com, create a **private** empty repository named `kaamka-agent` (no README).
2. From the project folder:

```bash
git remote add origin https://github.com/<your-username>/kaamka-agent.git
git push -u origin main
```

GitHub will ask you to sign in in your browser. CI then runs the tests, a secret scan
(gitleaks) and a Docker build on every push.

## API (Phase 3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness (public) |
| GET | `/api/overview` | Pipeline counts, pending approvals, spend vs cap |
| POST/GET | `/api/posts` | Create / list posts |
| PATCH | `/api/posts/{id}` | Edit caption, media, schedule |
| POST | `/api/posts/{id}/submit` | Run checks and request approval |
| GET | `/api/approvals` | Approval queue (default: pending) |
| POST | `/api/approvals/{id}/decision` | `{"approve": true/false, "note": "..."}` |
| GET/PUT | `/api/policies/auto_publish` | Owner-only switch, off by default |
| GET | `/api/revenue/summary` | Confirmed vs estimated revenue, costs, profit |
| POST | `/api/revenue` | Record revenue (confirmed needs evidence) |
| GET | `/api/audit` | Latest audit events |

## Database tables

`posts`, `action_requests` (approval queue + idempotency key), `audit_log`, `spend`,
`revenue`, `policies`. Tables are created on start-up for now; Alembic migrations arrive
before the first Azure deployment.
