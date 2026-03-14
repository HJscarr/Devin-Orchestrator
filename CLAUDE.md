# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

An automated GitHub issue triage and resolution orchestrator powered by Devin AI, built for FinServ Co. It triages open issues via Devin's structured output, lets engineers approve fixes from a dashboard or Slack, and tracks the full lifecycle from issue → triage → PR.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server
uvicorn app.main:app --reload --port 8000

# Access
# Dashboard: http://localhost:8000/dashboard
# API docs:  http://localhost:8000/docs
# Health:    http://localhost:8000/health
```

No test suite exists yet. The project has no Dockerfile or CI pipeline.

## Architecture

### Request Flow

```
GitHub Issue → POST /webhook/github → Devin triage session → background poll
  → structured_output received → GitHub comment + labels + Slack notification
  → Engineer clicks "Create PR" (dashboard or Slack) → POST /approve/{N}
  → Devin fix session → background poll → PR detected (Devin API + GitHub check)
  → GitHub comment + Slack notification → dashboard shows "pr_open"
```

### Key Design Decisions

- **Polling, not webhooks, for Devin sessions.** Devin's API has no callback/webhook mechanism. Background tasks poll every 15s (triage) or 30s (fix) using `asyncio.sleep`.
- **In-memory state only.** `issue_store` in `models.py` is a plain dict. All state is lost on restart. The `/sync` endpoint recovers state from Devin + GitHub APIs.
- **Devin v3 single-session GET returns 403** with service-user keys. `get_session()` works around this by using the list endpoint filtered by `session_id`.
- **Devin session status stays `"running"`** with `status_detail: "waiting_for_user"` when done. Polling checks for `structured_output` presence rather than terminal status values.
- **Devin's `pull_requests` field is unreliable** — often empty even after PR creation. The fix poller also checks GitHub directly via `find_pr_for_issue()`.
- **Services are module-level singletons** instantiated at import time in each router. They read config via `get_settings()` which is LRU-cached.

### Devin API Integration

- **Structured output schema** (`TRIAGE_OUTPUT_SCHEMA` in `devin_service.py`) enforces JSON response format for triage sessions: severity, category, effort, suggested_approach, affected_files, confidence.
- **Playbooks** are optional (configured via `TRIAGE_PLAYBOOK_ID` / `FIX_PLAYBOOK_ID` env vars). When set, they're attached to sessions via `playbook_id`.
- **Knowledge notes** are managed in the Devin dashboard, not in code. A repo context note exists for Spot-Fintech.
- **Tags** (`issue-{N}`, `triage`, `fix`) are used to filter sessions during sync.

### Slack Interactive Buttons

The Slack "Create PR" button sends a `block_actions` payload to `POST /webhook/slack`. This requires:
- A publicly reachable URL (ngrok for local dev)
- The Slack app's Interactivity Request URL set to `{public_url}/webhook/slack`
- `python-multipart` installed for form parsing

### Dashboard

The dashboard at `/dashboard` is server-rendered HTML with embedded JavaScript (no framework). It polls `GET /status` and re-renders the table client-side. All interactive buttons (`Triage All`, `Sync`, `Create PR`, `Retry`) call API endpoints via `fetch()`.

## Configuration

All config is in `.env`, loaded via Pydantic Settings:

| Variable | Required | Purpose |
|---|---|---|
| `DEVIN_API_KEY` | Yes | Service user key (`cog_...`) |
| `DEVIN_ORG_ID` | Yes | Organization ID (`org-...`) |
| `GITHUB_TOKEN` | Yes | PAT with `repo` scope |
| `GITHUB_REPO` | Yes | Target repo (e.g., `HJscarr/Spot-Fintech`) |
| `SLACK_WEBHOOK_URL` | No | Incoming webhook for notifications |
| `TRIAGE_PLAYBOOK_ID` | No | Devin playbook for triage sessions |
| `FIX_PLAYBOOK_ID` | No | Devin playbook for fix sessions |

## Status State Machine

```
PENDING → TRIAGED → APPROVED → IN_PROGRESS → PR_OPEN
                  ↘ FAILED (retryable via approve endpoint)
```

The approve endpoint accepts issues in `TRIAGED`, `FAILED`, or `IN_PROGRESS` status.
