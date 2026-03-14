import json
import hashlib
import hmac
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException, Form
from fastapi.responses import JSONResponse

from app.models import TrackedIssue, TriageStatus, issue_store

logger = logging.getLogger(__name__)
from app.routers.triage import _poll_triage_session
from app.routers.approve import _poll_fix_session
from app.config import get_settings
from app.services.devin_service import DevinService
from app.services.github_service import GitHubService
from app.services.notification_service import NotificationService

router = APIRouter(tags=["webhook"])

devin = DevinService()
github = GitHubService()
notifications = NotificationService()


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events for new/updated issues."""
    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()
    logger.info("GitHub webhook received: event=%s action=%s", event, payload.get("action"))

    if event != "issues":
        return {"message": f"Ignored event: {event}"}

    action = payload.get("action")
    if action not in ("opened", "reopened"):
        return {"message": f"Ignored action: {action}"}

    issue = payload["issue"]
    issue_number = issue["number"]
    logger.info("Processing %s issue #%d", action, issue_number)
    settings = get_settings()

    tracked = TrackedIssue(
        issue_number=issue_number,
        title=issue["title"],
        body=issue.get("body", "") or "",
        labels=[l["name"] for l in issue.get("labels", [])],
    )
    issue_store[issue_number] = tracked

    session = await devin.create_triage_session(
        issue_number=issue_number,
        issue_title=issue["title"],
        issue_body=tracked.body,
        repo=settings.github_repo,
    )

    tracked.devin_session_id = session["session_id"]
    tracked.devin_session_url = session.get("url")

    background_tasks.add_task(
        _poll_triage_session, issue_number, session["session_id"]
    )

    return {
        "message": f"Auto-triage started for new issue #{issue_number}",
        "session_id": session["session_id"],
    }


@router.post("/webhook/slack")
async def slack_interaction(request: Request, background_tasks: BackgroundTasks):
    """Handle Slack interactive button clicks (e.g. Create PR)."""
    form = await request.form()
    payload = json.loads(form.get("payload", "{}"))

    # Acknowledge immediately
    if payload.get("type") != "block_actions":
        return JSONResponse(content={"text": "OK"})

    for action in payload.get("actions", []):
        action_id = action.get("action_id", "")

        if action_id.startswith("approve_"):
            issue_number = int(action_id.split("_")[1])
            settings = get_settings()

            if issue_number not in issue_store:
                return JSONResponse(content={
                    "response_type": "ephemeral",
                    "text": f"Issue #{issue_number} not found. Sync first.",
                })

            tracked = issue_store[issue_number]
            if tracked.status != TriageStatus.TRIAGED:
                return JSONResponse(content={
                    "response_type": "ephemeral",
                    "text": f"Issue #{issue_number} is already {tracked.status.value}.",
                })

            approach = tracked.triage_result.suggested_approach if tracked.triage_result else ""
            session = await devin.create_fix_session(
                issue_number=issue_number,
                issue_title=tracked.title,
                issue_body=tracked.body,
                triage_approach=approach,
                repo=settings.github_repo,
            )

            tracked.status = TriageStatus.APPROVED
            tracked.devin_session_id = session["session_id"]
            tracked.devin_session_url = session.get("url")
            tracked.updated_at = datetime.utcnow()

            await github.post_comment(
                issue_number,
                f"This issue has been approved for automated fixing. "
                f"Devin is now working on it.\n\n"
                f"[View Devin session]({session.get('url', '')})",
            )

            background_tasks.add_task(
                _poll_fix_session, issue_number, session["session_id"]
            )

            return JSONResponse(content={
                "response_type": "in_channel",
                "text": f"\U0001f6e0\ufe0f Fix started for #{issue_number}: {tracked.title}\n<{session.get('url', '')}|Watch Devin>",
            })

    return JSONResponse(content={"text": "OK"})
