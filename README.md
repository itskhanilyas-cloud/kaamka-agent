# Kaam Ka AI — approval-first Instagram content agent

An open-source agent that drafts, designs and publishes Instagram content for one brand, then
tracks how it performs. It never posts without the owner's approval and never invents numbers.

Running live for [@kaamkaai.official](https://www.instagram.com/kaamkaai.official/): practical AI
tools for Indian students and early-career professionals, in English and Roman-script Hinglish.

**What it does**

- **Content Studio:** turns an idea into 1–4 drafts (carousel, single image or Reel script) in your
  brand voice using Azure OpenAI, each scored by a quality checklist.
- **Brand images:** draws 1080×1350 carousel slides and Reel covers from templates (Pillow + Inter
  font). No AI imagery, no per-image cost. Reels: upload your MP4.
- **Approval Center:** every post waits for the owner. Approve, then publish now or at a set time.
- **Publishing:** Instagram API with Instagram Login (images, carousels, Reels), max 3 posts a day,
  each approved post published exactly once.
- **Results:** views, reach, likes, comments, saves, shares and followers pulled every 6 hours into
  snapshot tables, with comparisons only once there is enough data.
- **Money:** a monthly AI spending cap enforced before every paid call; revenue tracked with evidence.
- **Mobile-first dashboard**, installable on a phone's home screen.

## Safety rules enforced in code

| Rule | Where |
|---|---|
| Only the owner can call the API, approve, reject or change policies | `app/security.py`, `services/approvals.py`, `services/policy.py` |
| The agent can request actions but never approve them or change policies | `services/approvals.py`, `services/policy.py` |
| Nothing reaches Instagram outside production: always a dry run | `services/publishing.get_publisher` |
| Each approved post publishes at most once (idempotency key + conditional claim) | `services/publishing.py` |
| The timer job only publishes posts the owner gave a time to | `services/publishing.run_due(scheduled_only=True)` |
| Rolling 24-hour post cap (default 3) | `KA_MAX_POSTS_PER_DAY` |
| Monthly spend cap blocks paid AI calls before they happen | `services/budget.py` |
| Affiliate posts need #Ad/#Affiliate in the first 150 characters | `services/approvals.check_post_ready` |
| Instagram tokens encrypted at rest; media shared through 1-hour signed links | `instagram/service.py` |
| Secrets redacted from the audit log; dev sign-in bypass refused in production | `services/audit.redact`, `app/config.py` |

## Try it locally (5 minutes, no cloud account)

Requires Python 3.13. Uses SQLite and a free offline "mock" writer, and never posts anywhere.

```bash
git clone https://github.com/itskhanilyas-cloud/kaamka-agent.git
cd kaamka-agent/backend
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp ../.env.example .env                                  # set KA_OWNER_EMAIL and your brand
python -m pytest -q                                      # all tests should pass
uvicorn app.main:create_app --factory --reload
```

Open http://127.0.0.1:8000/. To use real AI drafts, set `KA_TEXT_PROVIDER=azure_openai` plus your
Azure OpenAI endpoint and deployment in `.env`.

## Run your own copy in the cloud

The reference deployment is Azure (roughly ₹1,500–2,500 a month at low volume, mostly the database and registry; AI calls extra and capped):

| Piece | Azure service |
|---|---|
| Web app + dashboard | Container Apps (scale to zero) with Microsoft sign-in (Easy Auth) |
| Scheduled jobs: publish (15 min), metrics (6 h), token renewal (daily) | Container Apps Jobs |
| Database | PostgreSQL Flexible Server |
| Secrets | Key Vault, read by managed identities |
| AI | Azure OpenAI |
| Deploys | GitHub Actions with OIDC (no stored cloud password) |

1. **Azure:** in Azure Cloud Shell run `infra/setup-azure.sh`, then `infra/create-jobs.sh`. See
   [infra/README.md](infra/README.md).
2. **GitHub:** put the IDs the setup script prints into `.github/workflows/deploy.yml` (they are
   identifiers, not secrets) and change the repository check at the top of that workflow to your fork.
3. **Instagram:** create a Meta app with "Instagram API with Instagram Login", add your account as a
   tester, set the redirect URL to `https://<your-app>/instagram/callback`, store the Instagram app
   secret in Key Vault, then press **Connect Instagram** in the dashboard's Settings.
4. **Brand:** set `KA_BRAND_NAME` and `KA_BRAND_HANDLE`, and adjust the voice in `backend/app/ai/brand.py`.

Other clouds work too: it is one Docker image (`Dockerfile`) plus a PostgreSQL database and three
scheduled commands (`python -m app.jobs publish | sync-metrics | refresh-token`).

## Project layout

```
backend/app/          FastAPI app: api.py, security.py, jobs.py
  ai/                 brand voice, generator, quality checks, AI providers
  render/             image templates and fonts
  instagram/          OAuth, publishing, insights, signed media links
  services/           approvals, publishing, budget, policy, revenue, analytics, audit
  static/             dashboard (vanilla JS, no build step)
backend/tests/        automated tests
content/reels/        Reel scripts and render code (motion graphics with Pillow + ffmpeg)
infra/                Azure setup scripts
```

## Contributing

Issues and pull requests are welcome. Keep the safety rules above intact, add tests for new
behaviour, and never commit secrets (CI scans every push). Security problems: see [SECURITY.md](SECURITY.md).

## Licence

[MIT](LICENSE). The bundled Inter font is under the SIL Open Font License.
