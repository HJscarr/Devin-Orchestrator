# Devin Issue Orchestrator

An automated issue triage and resolution system powered by [Devin](https://devin.ai), built for FinServ Co.

## The Problem

FinServ Co has **300+ open GitHub issues** across their monorepo. Senior engineers are heads-down on platform work, and junior engineers spend more time understanding issues than fixing them. Issues sit stale for months.

## The Solution

This orchestrator sits between GitHub and Devin AI, turning a backlog of stale issues into a managed pipeline:

```
┌─────────────┐      ┌──────────────────┐      ┌───────────┐
│   GitHub     │      │   Orchestrator   │      │  Devin AI │
│   Issues     │─────▶│                  │─────▶│           │
│              │      │  Triage → Approve│      │  Analyse  │
│              │◀─────│  → Fix → Report  │◀─────│  Code     │
│   PRs +      │      │                  │      │  Fix      │
│   Comments   │      └───────┬──────────┘      └───────────┘
└─────────────┘              │
                    ┌────────┴────────┐
                    │                 │
              ┌─────▼─────┐   ┌──────▼──────┐
              │ Dashboard │   │    Slack     │
              │  (Web UI) │   │ Notifications│
              └───────────┘   └─────────────┘
```

### How It Works

1. **Triage** — Issues are sent to Devin for analysis. Devin returns structured assessments: severity, category, effort estimate, suggested approach, affected files, and a confidence score.
2. **Approve** — Engineers review triage results on the dashboard or in Slack and decide which issues Devin should fix. Human-in-the-loop keeps the team in control.
3. **Fix** — Devin opens PRs for approved issues. The orchestrator tracks session progress and detects PRs via both the Devin API and GitHub.
4. **Report** — A live dashboard shows the full pipeline: what's pending, triaged, in-progress, and resolved. Slack notifications keep the team updated without context-switching.

### Status Lifecycle

```
PENDING → TRIAGED → APPROVED → IN_PROGRESS → PR_OPEN
               ↘ FAILED (retryable)
```

## Quick Start

### Local

```bash
cp .env.example .env
# Fill in your API keys (see Environment Variables below)

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Docker

```bash
cp .env.example .env
# Fill in your API keys

docker build -t devin-orchestrator .
docker run --env-file .env -p 8000:8000 devin-orchestrator
```

Then open:
- **Dashboard**: http://localhost:8000/dashboard
- **API docs**: http://localhost:8000/docs

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/dashboard` | Web UI — live pipeline view |
| `GET` | `/health` | Health check |
| `POST` | `/triage` | Triage all open issues |
| `POST` | `/triage/{issue_number}` | Triage a single issue |
| `POST` | `/approve/{issue_number}` | Approve an issue for Devin to fix |
| `POST` | `/approve-all` | Approve all triaged issues |
| `POST` | `/sync` | Recover state from Devin + GitHub APIs |
| `GET` | `/status` | All tracked issues (JSON) |
| `GET` | `/status/{issue_number}` | Single issue status (JSON) |
| `POST` | `/webhook/github` | GitHub webhook receiver (auto-triage on issue open) |
| `POST` | `/webhook/slack` | Slack interactive button handler |

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `DEVIN_API_KEY` | Yes | Devin service-user API key (`cog_...`) |
| `DEVIN_ORG_ID` | Yes | Devin organization ID (`org-...`) |
| `GITHUB_TOKEN` | Yes | GitHub PAT with `repo` scope |
| `GITHUB_REPO` | Yes | Target repo, e.g. `HJscarr/Spot-Fintech` |
| `SLACK_WEBHOOK_URL` | No | Slack incoming webhook for notifications |
| `TRIAGE_PLAYBOOK_ID` | No | Devin playbook ID for triage sessions |
| `FIX_PLAYBOOK_ID` | No | Devin playbook ID for fix sessions |

## Project Structure

```
app/
├── main.py                  # FastAPI app + router registration
├── config.py                # Pydantic Settings (env var loading)
├── models.py                # Data models + in-memory issue store
├── routers/
│   ├── triage.py            # Triage endpoints + background polling
│   ├── approve.py           # Approval endpoints + fix polling
│   ├── status.py            # Status + dashboard endpoints
│   └── webhook.py           # GitHub + Slack webhook handlers
└── services/
    ├── devin_service.py     # Devin API client + session management
    ├── github_service.py    # GitHub API client + issue/PR operations
    └── notification_service.py  # Slack notifications
```

## Key Design Decisions

- **Polling for Devin sessions** — Devin's API has no webhook/callback mechanism, so background tasks poll session status (15s for triage, 30s for fixes).
- **Structured output enforcement** — Triage sessions use a JSON schema to guarantee consistent, parseable results from Devin.
- **Dual PR detection** — Checks both Devin's API and GitHub directly, since Devin's `pull_requests` field can lag behind actual PR creation.
- **Sync recovery** — The `/sync` endpoint rebuilds state from Devin + GitHub APIs after a restart, since state is held in-memory.
- **Human-in-the-loop** — Engineers approve which issues get fixed. Devin doesn't act autonomously on the codebase without explicit approval.
