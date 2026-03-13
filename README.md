# Devin Issue Orchestrator

An automated issue triage and resolution system powered by [Devin](https://devin.ai) for FinServ Co.

## Problem

FinServ Co has 300+ open GitHub issues across their monorepo. Senior engineers are heads-down on platform work, and junior engineers spend more time understanding issues than fixing them. Issues sit stale for months.

## Solution

This orchestrator connects GitHub Issues to Devin AI to automatically:

1. **Triage** — Scan open issues, have Devin assess complexity, category, and suggested approach
2. **Approve** — Engineers review triage results and approve which issues Devin should fix
3. **Fix** — Devin opens PRs for approved issues, with progress tracked end-to-end
4. **Report** — Dashboard shows what's triaged, in-flight, and resolved

## Architecture

```
GitHub Issues → Orchestrator API → Devin API
     ↑              ↓                  ↓
     └── Comments ←─┴── Dashboard ←── Session Status
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/triage` | Scan & triage all open issues |
| POST | `/triage/{issue_number}` | Triage a single issue |
| POST | `/approve/{issue_number}` | Approve an issue for Devin to fix |
| GET | `/status` | Dashboard of all sessions |
| GET | `/status/{issue_number}` | Status of a specific issue |
| POST | `/webhook/github` | GitHub webhook for new issues |

## Setup

```bash
cp .env.example .env
# Fill in your API keys

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `DEVIN_API_KEY` | Devin API key (starts with `cog_`) |
| `DEVIN_ORG_ID` | Devin organization ID |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITHUB_REPO` | Target repo (e.g. `HJscarr/Spot-Fintech`) |
| `SLACK_WEBHOOK_URL` | (Optional) Slack webhook for notifications |
