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
            "confidence": issue.triage_result.confidence if issue.triage_result else None,
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
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
                background: #0a0a0f;
                color: #e4e4e7;
                min-height: 100vh;
            }}
            .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem 2rem; }}
            .header {{
                display: flex; align-items: center; justify-content: space-between;
                padding: 1.25rem 2rem;
                background: #111118;
                border-bottom: 1px solid #1e1e2a;
            }}
            .logo {{
                display: flex; align-items: center; gap: 0.75rem;
            }}
            .logo-icon {{
                width: 32px; height: 32px; border-radius: 8px;
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                display: flex; align-items: center; justify-content: center;
                font-weight: 700; font-size: 0.875rem; color: white;
            }}
            .logo-text {{ font-size: 1rem; font-weight: 600; color: #f4f4f5; }}
            .logo-sub {{ font-size: 0.75rem; color: #52525b; margin-left: 0.75rem; }}
            .stats {{
                display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap;
            }}
            .stat-chip {{
                padding: 0.4rem 0.85rem; border-radius: 20px; font-size: 0.8rem; font-weight: 500;
                background: #18181f; border: 1px solid #27272f;
            }}
            .table-card {{
                background: #111118; border: 1px solid #1e1e2a; border-radius: 12px; overflow: hidden;
            }}
            table {{ width: 100%; border-collapse: collapse; }}
            th {{
                padding: 0.7rem 1rem; text-align: left; font-size: 0.75rem;
                font-weight: 500; color: #71717a; text-transform: uppercase; letter-spacing: 0.05em;
                background: #111118; border-bottom: 1px solid #1e1e2a;
            }}
            td {{
                padding: 0.75rem 1rem; border-bottom: 1px solid #1a1a24; font-size: 0.875rem;
            }}
            tr:hover {{ background: #15151f; }}
            a {{ color: #818cf8; text-decoration: none; }}
            a:hover {{ color: #a5b4fc; text-decoration: underline; }}
            .badge {{
                display: inline-block; padding: 0.2rem 0.6rem; border-radius: 12px;
                font-size: 0.75rem; font-weight: 600;
            }}
            .badge-pending {{ background: #27272a; color: #a1a1aa; }}
            .badge-triaged {{ background: #1e1b4b; color: #818cf8; }}
            .badge-approved {{ background: #2e1065; color: #a78bfa; }}
            .badge-in_progress {{ background: #422006; color: #fbbf24; }}
            .badge-pr_open {{ background: #052e16; color: #4ade80; }}
            .badge-resolved {{ background: #052e16; color: #22c55e; }}
            .badge-failed {{ background: #450a0a; color: #f87171; }}
            .severity-high {{ color: #f87171; }}
            .severity-medium {{ color: #fbbf24; }}
            .severity-low {{ color: #4ade80; }}
            .severity-critical {{ color: #f43f5e; font-weight: 700; }}
            .btn {{
                padding: 0.45rem 0.9rem; border: none; border-radius: 8px; cursor: pointer;
                font-size: 0.8rem; font-weight: 600; transition: all 0.15s ease;
            }}
            .btn:hover {{ transform: translateY(-1px); }}
            .btn:active {{ transform: translateY(0); }}
            .btn:disabled {{ opacity: 0.4; cursor: not-allowed; transform: none; }}
            .btn-primary {{
                background: linear-gradient(135deg, #6366f1, #7c3aed);
                color: white; box-shadow: 0 2px 8px rgba(99,102,241,0.25);
            }}
            .btn-primary:hover {{ box-shadow: 0 4px 12px rgba(99,102,241,0.35); }}
            .btn-ghost {{
                background: #1e1e2a; color: #a1a1aa; border: 1px solid #27272f;
            }}
            .btn-ghost:hover {{ background: #27272f; color: #e4e4e7; }}
            .btn-approve {{
                background: linear-gradient(135deg, #6366f1, #8b5cf6);
                color: white; font-size: 0.75rem; padding: 0.35rem 0.75rem;
                box-shadow: 0 2px 6px rgba(99,102,241,0.2);
            }}
            .actions {{ display: flex; gap: 0.5rem; }}
            .working {{
                display: inline-flex; align-items: center; gap: 0.4rem;
                color: #fbbf24; font-size: 0.8rem;
            }}
            .working-dot {{
                width: 6px; height: 6px; border-radius: 50%; background: #fbbf24;
                animation: pulse 1.5s ease-in-out infinite;
            }}
            @keyframes pulse {{ 0%, 100% {{ opacity: 0.4; }} 50% {{ opacity: 1; }} }}
            .done {{ color: #4ade80; font-size: 0.8rem; font-weight: 500; }}
            .muted {{ color: #52525b; font-size: 0.8rem; }}
            .empty-state {{
                text-align: center; padding: 3rem; color: #52525b;
            }}
            .empty-state p {{ margin-bottom: 1rem; }}
            .toast {{
                position: fixed; bottom: 1.5rem; right: 1.5rem; padding: 0.75rem 1.25rem;
                background: #18181f; color: #e4e4e7; border: 1px solid #27272f;
                border-radius: 10px; font-size: 0.85rem;
                box-shadow: 0 8px 24px rgba(0,0,0,0.4); opacity: 0; transition: opacity 0.3s;
                z-index: 100;
            }}
            .toast.show {{ opacity: 1; }}
        </style>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    </head>
    <body>
        <div class="header">
            <div class="logo">
                <div class="logo-icon">D</div>
                <span class="logo-text">Issue Orchestrator</span>
                <span class="logo-sub">FinServ Co</span>
            </div>
            <div class="actions">
                <button class="btn btn-ghost" onclick="syncSessions()">Sync</button>
                <button class="btn btn-primary" onclick="startTriage()">Triage All Issues</button>
            </div>
        </div>
        <div class="container">
            <div class="stats" id="stats"></div>
            <div class="table-card">
                <table>
                    <thead>
                        <tr>
                            <th>Issue</th>
                            <th>Title</th>
                            <th>Status</th>
                            <th>Severity</th>
                            <th>Effort</th>
                            <th>Confidence</th>
                            <th>Session</th>
                            <th>PR</th>
                            <th>Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        <tr><td colspan="9" class="empty-state"><p>No issues tracked yet.</p><button class="btn btn-primary" onclick="startTriage()">Triage All Issues</button></td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        <div class="toast" id="toast"></div>
        <script>
            function showToast(msg, duration = 3000) {{
                const t = document.getElementById('toast');
                t.textContent = msg;
                t.classList.add('show');
                setTimeout(() => t.classList.remove('show'), duration);
            }}

            async function startTriage() {{
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = 'Triaging...';
                try {{
                    const resp = await fetch('/triage', {{ method: 'POST' }});
                    const data = await resp.json();
                    showToast(data.message);
                }} catch (e) {{
                    showToast('Triage failed');
                    console.error(e);
                }}
                btn.disabled = false;
                btn.textContent = 'Triage All Issues';
                refreshDashboard();
            }}

            async function syncSessions() {{
                const btn = event.target;
                btn.disabled = true;
                btn.textContent = 'Syncing...';
                try {{
                    const resp = await fetch('/sync', {{ method: 'POST' }});
                    const data = await resp.json();
                    showToast(data.message);
                }} catch (e) {{
                    showToast('Sync failed');
                    console.error(e);
                }}
                btn.disabled = false;
                btn.textContent = 'Sync';
                refreshDashboard();
            }}

            async function approveIssue(issueNumber) {{
                const btn = document.getElementById(`approve-${{issueNumber}}`);
                btn.disabled = true;
                btn.textContent = 'Starting...';
                try {{
                    const resp = await fetch(`/approve/${{issueNumber}}`, {{ method: 'POST' }});
                    const data = await resp.json();
                    if (resp.ok) {{
                        showToast(`Fix started for issue #${{issueNumber}}`);
                    }} else {{
                        showToast(data.detail || 'Failed');
                        btn.disabled = false;
                        btn.textContent = 'Create PR';
                    }}
                }} catch (e) {{
                    showToast('Failed');
                    console.error(e);
                    btn.disabled = false;
                    btn.textContent = 'Create PR';
                }}
                refreshDashboard();
            }}

            function renderAction(issueNumber, issueStatus, hasPr) {{
                if (issueStatus === 'triaged') {{
                    return `<button class="btn btn-approve" id="approve-${{issueNumber}}" onclick="approveIssue(${{issueNumber}})">Create PR</button>`;
                }}
                if (issueStatus === 'pr_open' || hasPr) {{
                    return '<span class="done">Done</span>';
                }}
                if (issueStatus === 'approved' || issueStatus === 'in_progress') {{
                    return '<span class="working"><span class="working-dot"></span>Devin working</span>';
                }}
                if (issueStatus === 'failed') {{
                    return `<button class="btn btn-approve" id="approve-${{issueNumber}}" onclick="approveIssue(${{issueNumber}})">Retry</button>`;
                }}
                if (issueStatus === 'pending') {{
                    return '<span class="muted">Awaiting triage</span>';
                }}
                return '<span class="muted">—</span>';
            }}

            function severityClass(s) {{
                if (!s) return '';
                return 'severity-' + s.toLowerCase();
            }}

            async function refreshDashboard() {{
                try {{
                    const resp = await fetch('/status');
                    const data = await resp.json();

                    // Stats chips
                    const statsEl = document.getElementById('stats');
                    const chipColors = {{
                        pending: '#a1a1aa', triaged: '#818cf8', approved: '#a78bfa',
                        in_progress: '#fbbf24', pr_open: '#4ade80', resolved: '#22c55e', failed: '#f87171'
                    }};
                    statsEl.innerHTML = Object.entries(data.counts)
                        .filter(([_, count]) => count > 0)
                        .map(([status, count]) =>
                            `<div class="stat-chip" style="border-color:${{chipColors[status] || '#27272f'}}40">
                                <span style="color:${{chipColors[status] || '#a1a1aa'}}">${{count}}</span>
                                <span style="color:#71717a;margin-left:0.3rem">${{status.replace('_', ' ')}}</span>
                            </div>`
                        ).join('') || '<div class="stat-chip">No issues tracked</div>';

                    // Table rows
                    let rows = '';
                    const allIssues = Object.values(data.issues).flat()
                        .sort((a, b) => a.issue_number - b.issue_number);

                    for (const issue of allIssues) {{
                        let issueStatus = '';
                        for (const [st, items] of Object.entries(data.issues)) {{
                            if (items.some(i => i.issue_number === issue.issue_number)) {{
                                issueStatus = st;
                                break;
                            }}
                        }}
                        const session = issue.devin_session_url
                            ? `<a href="${{issue.devin_session_url}}" target="_blank">View</a>` : '<span class="muted">—</span>';
                        const pr = issue.pr_url
                            ? `<a href="${{issue.pr_url}}" target="_blank">Review PR</a>` : '<span class="muted">—</span>';
                        const action = renderAction(issue.issue_number, issueStatus, !!issue.pr_url);
                        const sevClass = severityClass(issue.severity);
                        rows += `<tr>
                            <td style="color:#71717a;font-weight:500">#${{issue.issue_number}}</td>
                            <td style="color:#f4f4f5">${{issue.title}}</td>
                            <td><span class="badge badge-${{issueStatus}}">${{issueStatus.replace('_', ' ')}}</span></td>
                            <td><span class="${{sevClass}}">${{issue.severity || '—'}}</span></td>
                            <td>${{issue.effort || '—'}}</td>
                            <td>${{issue.confidence ? `<span style="color:${{issue.confidence >= 0.9 ? '#4ade80' : issue.confidence >= 0.7 ? '#fbbf24' : '#f87171'}}">${{Math.round(issue.confidence * 100)}}%</span>` : '—'}}</td>
                            <td>${{session}}</td>
                            <td>${{pr}}</td>
                            <td>${{action}}</td>
                        </tr>`;
                    }}

                    document.querySelector('tbody').innerHTML = rows ||
                        '<tr><td colspan="9" class="empty-state"><p>No issues tracked yet.</p><button class="btn btn-primary" onclick="startTriage()">Triage All Issues</button></td></tr>';
                }} catch (e) {{
                    console.error('Dashboard refresh failed:', e);
                }}
            }}

            refreshDashboard();
            setInterval(refreshDashboard, 5000);
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)
