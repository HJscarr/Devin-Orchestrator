import hashlib
import hmac
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException

from app.models import TrackedIssue, issue_store
from app.routers.triage import _poll_triage_session
from app.config import get_settings
from app.services.devin_service import DevinService

router = APIRouter(tags=["webhook"])

devin = DevinService()


@router.post("/webhook/github")
async def github_webhook(request: Request, background_tasks: BackgroundTasks):
    """Handle GitHub webhook events for new/updated issues."""
    event = request.headers.get("X-GitHub-Event", "")
    payload = await request.json()

    if event != "issues":
        return {"message": f"Ignored event: {event}"}

    action = payload.get("action")
    if action not in ("opened", "reopened"):
        return {"message": f"Ignored action: {action}"}

    issue = payload["issue"]
    issue_number = issue["number"]
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
