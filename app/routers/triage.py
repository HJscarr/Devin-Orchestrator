import asyncio
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import get_settings

logger = logging.getLogger(__name__)
from app.models import TrackedIssue, TriageResult, TriageStatus, issue_store
from app.services.github_service import GitHubService
from app.services.devin_service import DevinService
from app.services.notification_service import NotificationService
from app.utils import retry_async

router = APIRouter(tags=["triage"])

github = GitHubService()
devin = DevinService()
notifications = NotificationService()


async def _poll_triage_session(issue_number: int, session_id: str):
    """Background task: poll Devin until triage session completes."""
    tracked = issue_store[issue_number]
    poll_count = 0

    while True:
        await asyncio.sleep(15)
        poll_count += 1
        logger.info("Polling triage session for issue #%d (iteration %d)", issue_number, poll_count)
        session = await retry_async(lambda: devin.get_session(session_id))
        status = session.get("status")
        status_detail = session.get("status_detail", "")

        # Triage is done when structured_output appears, or session reaches a terminal state
        if session.get("structured_output"):
            break
        if status_detail == "waiting_for_user":
            break
        if status in ("blocked", "finished", "exit", "error", "suspended"):
            break

    if session.get("structured_output"):
        output = session["structured_output"]
        triage = TriageResult(**output)
        tracked.triage_result = triage
        tracked.status = TriageStatus.TRIAGED
        tracked.updated_at = datetime.utcnow()

        # Post triage summary as a comment on the GitHub issue
        comment = (
            f"## Devin Triage Report\n\n"
            f"| Field | Value |\n"
            f"|-------|-------|\n"
            f"| **Severity** | {triage.severity} |\n"
            f"| **Category** | {triage.category} |\n"
            f"| **Estimated Effort** | {triage.estimated_effort} |\n"
            f"| **Confidence** | {triage.confidence:.0%} |\n\n"
            f"**Suggested Approach:**\n{triage.suggested_approach}\n\n"
            f"**Affected Files:**\n"
            + "\n".join(f"- `{f}`" for f in triage.affected_files)
            + "\n\n---\n"
            f"_To approve Devin to fix this issue, call "
            f"`POST /approve/{issue_number}`_"
        )
        await github.post_comment(issue_number, comment)

        # Label the issue with triage metadata
        labels = [
            f"severity:{triage.severity}",
            f"effort:{triage.estimated_effort}",
            f"category:{triage.category}",
            "triaged",
        ]
        await github.add_labels(issue_number, labels)

        await notifications.notify_triage_complete(tracked)
        logger.info("Triage complete for issue #%d: severity=%s category=%s", issue_number, triage.severity, triage.category)
    else:
        tracked.status = TriageStatus.FAILED
        tracked.updated_at = datetime.utcnow()
        logger.error("Triage failed for issue #%d: no structured output received", issue_number)


@router.post("/sync")
async def sync_existing_sessions():
    """Pull already-completed triage sessions and PRs from Devin + GitHub into the local store.

    Useful after a server restart to recover state without creating new sessions.
    """
    issues = await github.get_open_issues()
    synced = []

    for issue in issues:
        number = issue["number"]
        tag = f"issue-{number}"
        sessions = await devin.list_sessions(tag=tag)

        # Find the most recent triage session with structured output
        triage_session = None
        fix_session = None
        for s in sessions:
            if "triage" in s.get("tags", []) and s.get("structured_output") and not triage_session:
                triage_session = s
            if "fix" in s.get("tags", []) and not fix_session:
                fix_session = s

        if not triage_session:
            continue

        tracked = TrackedIssue(
            issue_number=number,
            title=issue["title"],
            body=issue.get("body", "") or "",
            labels=[l["name"] for l in issue.get("labels", [])],
        )
        tracked.devin_session_id = triage_session["session_id"]
        tracked.devin_session_url = triage_session.get("url")

        triage = TriageResult(**triage_session["structured_output"])
        tracked.triage_result = triage
        tracked.status = TriageStatus.TRIAGED
        tracked.updated_at = datetime.utcnow()

        # If a fix session exists, check for PR
        if fix_session:
            tracked.devin_session_id = fix_session["session_id"]
            tracked.devin_session_url = fix_session.get("url")
            tracked.status = TriageStatus.IN_PROGRESS

            # Check Devin API for PR
            prs = fix_session.get("pull_requests", [])
            if prs:
                tracked.pr_url = prs[0].get("url", "")
                tracked.status = TriageStatus.PR_OPEN

            # Also check GitHub directly
            if not tracked.pr_url:
                pr_url = await github.find_pr_for_issue(number)
                if pr_url:
                    tracked.pr_url = pr_url
                    tracked.status = TriageStatus.PR_OPEN

            # If fix session errored out, mark as failed
            if fix_session.get("status") == "error":
                tracked.status = TriageStatus.FAILED

            # If fix session is done but no PR was found, fall back to TRIAGED
            # so the "Create PR" button appears again
            if tracked.status == TriageStatus.IN_PROGRESS and not tracked.pr_url:
                fix_status = fix_session.get("status", "")
                fix_detail = fix_session.get("status_detail", "")
                if fix_detail == "waiting_for_user" or fix_status in ("finished", "exit", "suspended", "blocked"):
                    tracked.status = TriageStatus.TRIAGED

        issue_store[number] = tracked
        synced.append(number)

    return {"message": f"Synced {len(synced)} issues", "issues": synced}


@router.post("/triage")
async def triage_all_issues(background_tasks: BackgroundTasks):
    """Scan all open issues and kick off Devin triage sessions."""
    settings = get_settings()
    issues = await github.get_open_issues()

    sessions_created = []
    for issue in issues:
        number = issue["number"]

        # Skip already-tracked issues
        if number in issue_store and issue_store[number].status != TriageStatus.PENDING:
            continue

        tracked = TrackedIssue(
            issue_number=number,
            title=issue["title"],
            body=issue.get("body", "") or "",
            labels=[l["name"] for l in issue.get("labels", [])],
        )
        issue_store[number] = tracked

        session = await devin.create_triage_session(
            issue_number=number,
            issue_title=issue["title"],
            issue_body=tracked.body,
            repo=settings.github_repo,
        )

        tracked.devin_session_id = session["session_id"]
        tracked.devin_session_url = session.get("url")

        background_tasks.add_task(
            _poll_triage_session, number, session["session_id"]
        )
        sessions_created.append(
            {"issue": number, "session_id": session["session_id"]}
        )

    return {
        "message": f"Triage started for {len(sessions_created)} issues",
        "sessions": sessions_created,
    }


@router.post("/triage/{issue_number}")
async def triage_single_issue(
    issue_number: int, background_tasks: BackgroundTasks
):
    """Triage a single issue by number."""
    logger.info("Starting triage for issue #%d", issue_number)
    settings = get_settings()
    issue = await github.get_issue(issue_number)

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
        "message": f"Triage started for issue #{issue_number}",
        "session_id": session["session_id"],
        "session_url": session.get("url"),
    }
