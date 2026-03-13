import asyncio
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, HTTPException

from app.config import get_settings
from app.models import TrackedIssue, TriageResult, TriageStatus, issue_store
from app.services.github_service import GitHubService
from app.services.devin_service import DevinService
from app.services.notification_service import NotificationService

router = APIRouter(tags=["triage"])

github = GitHubService()
devin = DevinService()
notifications = NotificationService()


async def _poll_triage_session(issue_number: int, session_id: str):
    """Background task: poll Devin until triage session completes."""
    tracked = issue_store[issue_number]

    while True:
        await asyncio.sleep(15)
        session = await devin.get_session(session_id)
        status = session.get("status")

        if status in ("exit", "error", "suspended"):
            break

    if status == "exit" and session.get("structured_output"):
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
    else:
        tracked.status = TriageStatus.FAILED
        tracked.updated_at = datetime.utcnow()


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
