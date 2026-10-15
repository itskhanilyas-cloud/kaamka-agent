# Kaam Ka AI — Instagram Business Agent

An approval-first agent that plans, creates and publishes Instagram content for a faceless
"practical AI tools" brand, and tracks costs and revenue honestly.

**Status: Phase 5 (dashboard).** Mobile-first web dashboard at `/`: Overview, Content Studio, Approval Center, Posts, Money, Settings, Audit log (Trend Lab and Analytics show what is coming; no fake numbers). Built on Phase 4 (text generation): Phase 3 foundation plus the Content Studio: AI-written
captions, hooks, carousel slides and Reel scripts in the brand voice, 1-4 variants per idea,
each scored by a quality checklist and saved as a draft. 72 automated tests pass.
**Live on Azure** (Container Apps, Central India) behind Microsoft sign-in, deployed by GitHub Actions on every green
CI run. Live AI generation via Azure OpenAI (`text-main` = gpt-5.4-mini, managed identity) verified 2026-10-15.
**Phase 4b:** every draft gets branded 1080×1350 JPEG slides (Instagram's API accepts JPEG only), drawn from
brand templates with Pillow and the bundled Inter font (SIL OFL): no AI imagery, no per-image cost. Slide text is
editable in the dashboard and re-renders the images. Reels get a cover; Reel video is a later phase.
Not yet built: Reel video, Instagram (Phase 6), scheduled jobs in Azure (Phase 7).

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

Open http://127.0.0.1:8000/ for the dashboard (or /api/docs for the raw API), or run the publish job once:

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
| POST | `/api/studio/generate` | `{"idea", "media_type": IMAGE/CAROUSEL/REELS, "pillar", "variants": 1-4, "has_affiliate_link", "test_notes"}` → scored drafts |

Pillars: `tool_test`, `workflow`, `prompts`, `news`, `career` (see `app/ai/brand.py`).

## Content Studio safeguards

- Budget is reserved **before** the model is called; the call is refused if it would break the monthly cap.
  The estimate is replaced by the measured token cost afterwards.
- The brand prompt forbids invented test results, guarantees, real people and investment/medical/legal advice.
- Quality checklist (`app/ai/quality.py`): hook ≤ 12 words, caption 80-2,200 characters, 3-8 hashtags, call to
  action, no over-claiming, affiliate disclosure, carousel 3-10 slides of ≤ 30 words, Reel hook in seconds 0-3, alt text.
  Blocking failures are flagged; variants are returned best first.
- Mock output is labelled `[MOCK DRAFT]` and `is_mock: true` everywhere, so it can never be mistaken for real content.

## Database tables

`posts`, `action_requests` (approval queue + idempotency key), `audit_log`, `spend`,
`revenue`, `policies`. Tables are created on start-up for now; Alembic migrations arrive
before the first Azure deployment.
