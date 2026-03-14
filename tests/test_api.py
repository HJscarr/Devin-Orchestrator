"""Tests for the Devin Orchestrator API endpoints."""

import json
import pytest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.models import (
    TrackedIssue,
    TriageResult,
    TriageStatus,
    Severity,
    issue_store,
)
from app.routers import triage as triage_router_module
from app.routers import approve as approve_router_module
from app.routers import webhook as webhook_router_module


@pytest.fixture
def client():
    """Create a TestClient and clear issue_store between tests."""
    issue_store.clear()
    with TestClient(app) as c:
        yield c
    issue_store.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_triage_result(**overrides) -> TriageResult:
    defaults = {
        "severity": Severity.MEDIUM,
        "category": "bug",
        "estimated_effort": "small",
        "suggested_approach": "Fix the null check in handler.py",
        "affected_files": ["src/handler.py"],
        "confidence": 0.85,
    }
    defaults.update(overrides)
    return TriageResult(**defaults)


def _make_tracked_issue(
    issue_number: int = 42,
    status: TriageStatus = TriageStatus.TRIAGED,
    with_triage: bool = True,
) -> TrackedIssue:
    issue = TrackedIssue(
        issue_number=issue_number,
        title="Test issue",
        body="Something is broken",
        labels=["bug"],
        status=status,
    )
    if with_triage:
        issue.triage_result = _make_triage_result()
    return issue


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------

def test_health_returns_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------

def test_status_empty_state(client):
    resp = client.get("/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "counts" in data
    assert "issues" in data
    # All counts should be zero when nothing is tracked
    for count in data["counts"].values():
        assert count == 0


# ---------------------------------------------------------------------------
# GET /status/{issue_number}
# ---------------------------------------------------------------------------

def test_status_unknown_issue_returns_404(client):
    resp = client.get("/status/9999")
    assert resp.status_code == 404
    assert "not being tracked" in resp.json()["detail"]


def test_status_known_issue(client):
    tracked = _make_tracked_issue(issue_number=10)
    issue_store[10] = tracked

    resp = client.get("/status/10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["issue_number"] == 10
    assert data["status"] == TriageStatus.TRIAGED.value
    assert data["triage_result"]["severity"] == "medium"


# ---------------------------------------------------------------------------
# POST /triage/{issue_number}
# ---------------------------------------------------------------------------

def test_triage_single_issue(client):
    fake_github_issue = {
        "number": 7,
        "title": "Login button broken",
        "body": "Cannot click login",
        "labels": [{"name": "bug"}],
    }
    fake_session = {
        "session_id": "sess-abc123",
        "url": "https://app.devin.ai/sessions/sess-abc123",
    }
    # The background poller calls devin.get_session, so provide a completed session
    fake_completed_session = {
        "session_id": "sess-abc123",
        "status": "running",
        "status_detail": "waiting_for_user",
        "structured_output": {
            "severity": "medium",
            "category": "bug",
            "estimated_effort": "small",
            "suggested_approach": "Fix the null check",
            "affected_files": ["src/handler.py"],
            "confidence": 0.9,
        },
    }

    with (
        patch.object(
            triage_router_module.github, "get_issue",
            new=AsyncMock(return_value=fake_github_issue),
        ),
        patch.object(
            triage_router_module.devin, "create_triage_session",
            new=AsyncMock(return_value=fake_session),
        ),
        patch.object(
            triage_router_module.devin, "get_session",
            new=AsyncMock(return_value=fake_completed_session),
        ),
        patch.object(
            triage_router_module.github, "post_comment",
            new=AsyncMock(),
        ),
        patch.object(
            triage_router_module.github, "add_labels",
            new=AsyncMock(),
        ),
        patch.object(
            triage_router_module.notifications, "notify_triage_complete",
            new=AsyncMock(),
        ),
        patch("app.routers.triage.asyncio.sleep", new=AsyncMock()),
    ):
        resp = client.post("/triage/7")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-abc123"
    assert "session_url" in data
    # Issue should now be in the store
    assert 7 in issue_store
    assert issue_store[7].devin_session_id == "sess-abc123"


# ---------------------------------------------------------------------------
# POST /approve/{issue_number}  — success
# ---------------------------------------------------------------------------

def test_approve_triaged_issue(client):
    tracked = _make_tracked_issue(issue_number=42, status=TriageStatus.TRIAGED)
    issue_store[42] = tracked

    fake_session = {
        "session_id": "sess-fix-001",
        "url": "https://app.devin.ai/sessions/sess-fix-001",
    }
    # The background poller calls get_session and find_pr_for_issue, so mock them.
    # Return a session with a PR so the poller exits quickly.
    fake_fix_session = {
        "session_id": "sess-fix-001",
        "status": "running",
        "status_detail": "waiting_for_user",
        "pull_requests": [{"url": "https://github.com/org/repo/pull/1"}],
    }

    with (
        patch.object(
            approve_router_module.devin, "create_fix_session",
            new=AsyncMock(return_value=fake_session),
        ),
        patch.object(
            approve_router_module.devin, "get_session",
            new=AsyncMock(return_value=fake_fix_session),
        ),
        patch.object(
            approve_router_module.github, "post_comment",
            new=AsyncMock(),
        ),
        patch.object(
            approve_router_module.github, "find_pr_for_issue",
            new=AsyncMock(return_value=None),
        ),
        patch.object(
            approve_router_module.notifications, "notify_fix_started",
            new=AsyncMock(),
        ),
        patch.object(
            approve_router_module.notifications, "notify_pr_opened",
            new=AsyncMock(),
        ),
        patch("app.routers.approve.asyncio.sleep", new=AsyncMock()),
    ):
        resp = client.post("/approve/42")

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-fix-001"
    # After the background task runs, status transitions through APPROVED -> IN_PROGRESS -> PR_OPEN
    assert issue_store[42].status == TriageStatus.PR_OPEN


# ---------------------------------------------------------------------------
# POST /approve/{issue_number}  — not found
# ---------------------------------------------------------------------------

def test_approve_unknown_issue_returns_404(client):
    resp = client.post("/approve/9999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /approve/{issue_number}  — wrong status (pending)
# ---------------------------------------------------------------------------

def test_approve_pending_issue_returns_400(client):
    tracked = _make_tracked_issue(
        issue_number=50, status=TriageStatus.PENDING, with_triage=False
    )
    issue_store[50] = tracked

    resp = client.post("/approve/50")
    assert resp.status_code == 400
    assert "pending" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# POST /webhook/github  — issues/opened triggers auto-triage
# ---------------------------------------------------------------------------

def test_github_webhook_issues_opened(client):
    payload = {
        "action": "opened",
        "issue": {
            "number": 15,
            "title": "New critical bug",
            "body": "Production is down",
            "labels": [{"name": "urgent"}],
        },
    }
    fake_session = {
        "session_id": "sess-webhook-001",
        "url": "https://app.devin.ai/sessions/sess-webhook-001",
    }

    with (
        patch.object(
            webhook_router_module.devin, "create_triage_session",
            new=AsyncMock(return_value=fake_session),
        ),
    ):
        resp = client.post(
            "/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "issues"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["session_id"] == "sess-webhook-001"
    assert "auto-triage" in data["message"].lower()
    # Issue should be tracked
    assert 15 in issue_store
    assert issue_store[15].title == "New critical bug"


def test_github_webhook_ignores_non_issue_events(client):
    resp = client.post(
        "/webhook/github",
        json={"action": "created"},
        headers={"X-GitHub-Event": "push"},
    )
    assert resp.status_code == 200
    assert "ignored" in resp.json()["message"].lower()


def test_github_webhook_ignores_closed_action(client):
    payload = {
        "action": "closed",
        "issue": {
            "number": 99,
            "title": "Old issue",
            "body": "",
            "labels": [],
        },
    }
    resp = client.post(
        "/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert "ignored" in resp.json()["message"].lower()
    assert 99 not in issue_store
