from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse

from app.models import TrackedIssue, TriageStatus, issue_store

router = APIRouter(tags=["status"])


@router.get("/status")
async def get_all_status() -> dict:
    """Return a summary of all tracked issues grouped by status."""
    summary = {status.value: [] for status in TriageStatus}

    for issue in issue_store.values():
        summary[issue.status.value].append({
            "issue_number": issue.issue_number,
            "title": issue.title,
            "severity": issue.triage_result.severity if issue.triage_result else None,
            "effort": issue.triage_result.estimated_effort if issue.triage_result else None,
            "devin_session_url": issue.devin_session_url,
            "pr_url": issue.pr_url,
        })

    counts = {status: len(items) for status, items in summary.items()}

    return {"counts": counts, "issues": summary}


@router.get("/status/{issue_number}")
async def get_issue_status(issue_number: int) -> dict:
    """Get detailed status for a specific tracked issue."""
    if issue_number not in issue_store:
        raise HTTPException(
            status_code=404,
            detail=f"Issue #{issue_number} is not being tracked.",
        )

    tracked = issue_store[issue_number]
    return {
        "issue_number": tracked.issue_number,
        "title": tracked.title,
        "status": tracked.status,
        "triage_result": tracked.triage_result,
        "devin_session_id": tracked.devin_session_id,
        "devin_session_url": tracked.devin_session_url,
        "pr_url": tracked.pr_url,
        "updated_at": tracked.updated_at,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard():
    """Simple HTML dashboard showing all tracked issues."""
    rows = ""
    for issue in sorted(issue_store.values(), key=lambda i: i.issue_number):
        severity = issue.triage_result.severity if issue.triage_result else "—"
        effort = issue.triage_result.estimated_effort if issue.triage_result else "—"
        session_link = (
            f'<a href="{issue.devin_session_url}" target="_blank">View</a>'
            if issue.devin_session_url else "—"
        )
        pr_link = (
            f'<a href="{issue.pr_url}" target="_blank">Review PR</a>'
            if issue.pr_url else "—"
        )

        status_colors = {
            "pending": "#6b7280",
            "triaged": "#3b82f6",
            "approved": "#8b5cf6",
            "in_progress": "#f59e0b",
            "pr_open": "#10b981",
            "resolved": "#059669",
            "failed": "#ef4444",
        }
        color = status_colors.get(issue.status.value, "#6b7280")

        rows += f"""
        <tr>
            <td>#{issue.issue_number}</td>
            <td>{issue.title}</td>
            <td><span style="color:{color};font-weight:bold">{issue.status.value}</span></td>
            <td>{severity}</td>
            <td>{effort}</td>
            <td>{session_link}</td>
            <td>{pr_link}</td>
        </tr>"""

    counts = {}
    for issue in issue_store.values():
        counts[issue.status.value] = counts.get(issue.status.value, 0) + 1

    stats_html = " | ".join(
        f"<strong>{status}:</strong> {count}"
        for status, count in counts.items()
    ) or "No issues tracked yet"

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Devin Issue Orchestrator — FinServ Co</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 2rem; background: #f9fafb; }}
            h1 {{ color: #111827; }}
            .stats {{ padding: 1rem; background: white; border-radius: 8px; margin-bottom: 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
            th {{ background: #1f2937; color: white; padding: 0.75rem 1rem; text-align: left; }}
            td {{ padding: 0.75rem 1rem; border-bottom: 1px solid #e5e7eb; }}
            tr:hover {{ background: #f3f4f6; }}
            a {{ color: #3b82f6; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <h1>Devin Issue Orchestrator</h1>
        <p>Automated issue triage and resolution for FinServ Co</p>
        <div class="stats">{stats_html}</div>
        <table>
            <thead>
                <tr>
                    <th>Issue</th>
                    <th>Title</th>
                    <th>Status</th>
                    <th>Severity</th>
                    <th>Effort</th>
                    <th>Devin Session</th>
                    <th>PR</th>
                </tr>
            </thead>
            <tbody>
                {rows if rows else '<tr><td colspan="7" style="text-align:center;padding:2rem;color:#6b7280">No issues tracked yet. Call POST /triage to get started.</td></tr>'}
            </tbody>
        </table>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
