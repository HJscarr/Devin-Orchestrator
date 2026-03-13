from pydantic import BaseModel
from datetime import datetime
from enum import Enum
from typing import Optional


class TriageStatus(str, Enum):
    PENDING = "pending"
    TRIAGED = "triaged"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    PR_OPEN = "pr_open"
    RESOLVED = "resolved"
    FAILED = "failed"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TriageResult(BaseModel):
    severity: Severity
    category: str  # e.g. "bug", "feature", "refactor"
    estimated_effort: str  # e.g. "small", "medium", "large"
    suggested_approach: str
    affected_files: list[str]
    confidence: float  # 0-1 how confident Devin is in the assessment


class TrackedIssue(BaseModel):
    issue_number: int
    title: str
    body: str
    labels: list[str]
    status: TriageStatus = TriageStatus.PENDING
    triage_result: Optional[TriageResult] = None
    devin_session_id: Optional[str] = None
    devin_session_url: Optional[str] = None
    pr_url: Optional[str] = None
    created_at: datetime = datetime.utcnow()
    updated_at: datetime = datetime.utcnow()


# In-memory store for demo purposes. In production, use a database.
issue_store: dict[int, TrackedIssue] = {}
