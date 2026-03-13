import asyncio
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import get_settings
from app.models import TriageStatus, issue_store
from app.services.devin_service import DevinService
from app.services.github_service import GitHubService
from app.services.notification_service import NotificationService

router = APIRouter(tags=["approve"])

devin = DevinService()
github = GitHubService()
notifications = NotificationService()


async def _poll_fix_session(issue_number: int, session_id: str):
    """Background task: poll Devin until fix session completes."""
    tracked = issue_store[issue_number]
    tracked.status = TriageStatus.IN_PROGRESS
    tracked.updated_at = datetime.utcnow()

    await notifications.notify_fix_started(tracked)

    while True:
        await asyncio.sleep(30)
        session = await devin.get_session(session_id)
        status = session.get("status")

        # Check if Devin opened a PR
        pull_requests = session.get("pull_requests", [])
        if pull_requests and tracked.status != TriageStatus.PR_OPEN:
            tracked.pr_url = pull_requests[0].get("url", "")
            tracked.status = TriageStatus.PR_OPEN
            tracked.updated_at = datetime.utcnow()

            await github.post_comment(
                issue_number,
                f"Devin has opened a PR to fix this issue: {tracked.pr_url}\n\n"
                f"Please review and merge when ready.",
            )
            await notifications.notify_pr_opened(tracked)

        if status in ("exit", "error", "suspended"):
            break

    if status == "exit" and tracked.pr_url:
        tracked.status = TriageStatus.PR_OPEN
    elif status == "error":
        tracked.status = TriageStatus.FAILED
        await github.post_comment(
            issue_number,
            "Devin encountered an error while working on this issue. "
            "Manual intervention may be required.",
        )
    tracked.updated_at = datetime.utcnow()


@router.post("/approve/{issue_number}")
async def approve_issue(issue_number: int, background_tasks: BackgroundTasks):
    """Approve an issue for Devin to fix. Must be triaged first."""
    settings = get_settings()

    if issue_number not in issue_store:
        raise HTTPException(
            status_code=404,
            detail=f"Issue #{issue_number} not found. Triage it first.",
        )

    tracked = issue_store[issue_number]

    if tracked.status != TriageStatus.TRIAGED:
        raise HTTPException(
            status_code=400,
            detail=f"Issue #{issue_number} is in status '{tracked.status}'. "
            f"Only triaged issues can be approved.",
        )

    approach = ""
    if tracked.triage_result:
        approach = tracked.triage_result.suggested_approach

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

    return {
        "message": f"Fix session started for issue #{issue_number}",
        "session_id": session["session_id"],
        "session_url": session.get("url"),
    }
