import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)
from app.models import TriageStatus, issue_store
from app.services.devin_service import DevinService
from app.services.github_service import GitHubService
from app.services.notification_service import NotificationService
from app.utils import retry_async

router = APIRouter(tags=["approve"])

devin = DevinService()
github = GitHubService()
notifications = NotificationService()


async def _poll_fix_session(issue_number: int, session_id: str):
    """Background task: poll Devin until fix session completes."""
    logger.info("Fix session started for issue #%d, session_id=%s", issue_number, session_id)
    tracked = issue_store[issue_number]
    tracked.status = TriageStatus.IN_PROGRESS
    tracked.updated_at = datetime.utcnow()

    await notifications.notify_fix_started(tracked)

    while True:
        await asyncio.sleep(30)
        session = await retry_async(lambda: devin.get_session(session_id))
        status = session.get("status")
        status_detail = session.get("status_detail", "")

        # Check Devin API for PR
        pull_requests = session.get("pull_requests", [])
        if pull_requests and tracked.status != TriageStatus.PR_OPEN:
            tracked.pr_url = pull_requests[0].get("url", "")

        # Also check GitHub directly (Devin API sometimes doesn't populate pull_requests)
        if not tracked.pr_url and tracked.status != TriageStatus.PR_OPEN:
            pr_url = await retry_async(lambda: github.find_pr_for_issue(issue_number))
            if pr_url:
                tracked.pr_url = pr_url

        # Notify on PR found
        if tracked.pr_url and tracked.status != TriageStatus.PR_OPEN:
            logger.info("PR detected for issue #%d: %s", issue_number, tracked.pr_url)
            tracked.status = TriageStatus.PR_OPEN
            tracked.updated_at = datetime.utcnow()
            await github.post_comment(
                issue_number,
                f"Devin has opened a PR to fix this issue: {tracked.pr_url}\n\n"
                f"Please review and merge when ready.",
            )
            await notifications.notify_pr_opened(tracked)

        # Done when PR is found, or session is done
        if tracked.pr_url:
            break
        if status_detail == "waiting_for_user":
            # Session done but no PR — check GitHub one last time
            pr_url = await retry_async(lambda: github.find_pr_for_issue(issue_number))
            if pr_url:
                tracked.pr_url = pr_url
                tracked.status = TriageStatus.PR_OPEN
                tracked.updated_at = datetime.utcnow()
                await notifications.notify_pr_opened(tracked)
            break
        if status in ("blocked", "finished", "exit", "error", "suspended"):
            break

    if tracked.pr_url:
        tracked.status = TriageStatus.PR_OPEN
        logger.info("Fix complete for issue #%d, PR: %s", issue_number, tracked.pr_url)
    elif status == "error":
        tracked.status = TriageStatus.FAILED
        logger.error("Fix session failed for issue #%d: Devin reported error", issue_number)
        await github.post_comment(
            issue_number,
            "Devin encountered an error while working on this issue. "
            "Manual intervention may be required.",
        )
    tracked.updated_at = datetime.utcnow()


@router.post("/approve-all")
async def approve_all_triaged(background_tasks: BackgroundTasks):
    """Approve all triaged issues for Devin to fix."""
    settings = get_settings()
    approved = []

    for number, tracked in issue_store.items():
        if tracked.status != TriageStatus.TRIAGED:
            continue

        approach = tracked.triage_result.suggested_approach if tracked.triage_result else ""
        session = await devin.create_fix_session(
            issue_number=number,
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
            number,
            f"This issue has been approved for automated fixing. "
            f"Devin is now working on it.\n\n"
            f"[View Devin session]({session.get('url', '')})",
        )

        background_tasks.add_task(
            _poll_fix_session, number, session["session_id"]
        )
        approved.append(number)

    return {
        "message": f"Fix sessions started for {len(approved)} issues",
        "issues": approved,
    }


@router.post("/approve/{issue_number}")
async def approve_issue(issue_number: int, background_tasks: BackgroundTasks):
    """Approve an issue for Devin to fix. Must be triaged first."""
    logger.info("Approval requested for issue #%d", issue_number)
    settings = get_settings()

    if issue_number not in issue_store:
        raise HTTPException(
            status_code=404,
            detail=f"Issue #{issue_number} not found. Triage it first.",
        )

    tracked = issue_store[issue_number]

    allowed = {TriageStatus.TRIAGED, TriageStatus.FAILED, TriageStatus.IN_PROGRESS}
    if tracked.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Issue #{issue_number} is in status '{tracked.status.value}'. "
            f"Cannot approve.",
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
