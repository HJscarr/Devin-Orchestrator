import logging

import httpx
from app.config import get_settings

logger = logging.getLogger(__name__)

# Structured output schema for Devin triage sessions.
# Devin will return JSON matching this schema.
TRIAGE_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "severity": {
            "type": "string",
            "enum": ["low", "medium", "high", "critical"],
        },
        "category": {
            "type": "string",
            "enum": ["bug", "feature", "refactor", "docs", "test", "security"],
        },
        "estimated_effort": {
            "type": "string",
            "enum": ["small", "medium", "large"],
        },
        "suggested_approach": {"type": "string"},
        "affected_files": {
            "type": "array",
            "items": {"type": "string"},
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": [
        "severity",
        "category",
        "estimated_effort",
        "suggested_approach",
        "affected_files",
        "confidence",
    ],
}


class DevinService:
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.devin_api_key
        self.org_id = settings.devin_org_id
        self.base_url = f"{settings.devin_api_base}/organizations/{self.org_id}"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        self.triage_playbook_id = settings.triage_playbook_id
        self.fix_playbook_id = settings.fix_playbook_id

    async def create_triage_session(
        self, issue_number: int, issue_title: str, issue_body: str, repo: str
    ) -> dict:
        """Create a Devin session to triage a GitHub issue."""
        prompt = (
            f"Analyze the following GitHub issue from the repo {repo} and provide "
            f"a triage assessment. Do NOT create a fix — just analyze the issue.\n\n"
            f"Issue #{issue_number}: {issue_title}\n\n"
            f"{issue_body}\n\n"
            f"Examine the codebase to understand the issue, identify affected files, "
            f"assess severity, estimate effort to fix, and suggest an approach."
        )

        payload = {
            "prompt": prompt,
            "title": f"Triage: #{issue_number} — {issue_title}",
            "tags": [f"issue-{issue_number}", "triage"],
            "repos": [repo],
            "structured_output_schema": TRIAGE_OUTPUT_SCHEMA,
        }
        if self.triage_playbook_id:
            payload["playbook_id"] = self.triage_playbook_id

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/sessions",
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Triage session created for issue #%d: session_id=%s", issue_number, data.get("session_id"))
            return data

    async def create_fix_session(
        self, issue_number: int, issue_title: str, issue_body: str,
        triage_approach: str, repo: str
    ) -> dict:
        """Create a Devin session to fix a GitHub issue and open a PR."""
        prompt = (
            f"Fix the following GitHub issue in repo {repo} and open a pull request.\n\n"
            f"Issue #{issue_number}: {issue_title}\n\n"
            f"{issue_body}\n\n"
            f"Suggested approach from triage:\n{triage_approach}\n\n"
            f"Requirements:\n"
            f"- Create a branch named `fix/issue-{issue_number}`\n"
            f"- Implement the fix following the suggested approach\n"
            f"- Write or update tests if applicable\n"
            f"- Verify your fix by running: pytest tests/test_bug{issue_number}_*.py -v\n"
            f"- Update .github/workflows/tests.yml so the CI step runs ONLY "
            f"the test for this bug: pytest tests/test_bug{issue_number}_*.py -v "
            f"(this ensures the PR shows a green check for the specific fix)\n"
            f"- Open a PR referencing issue #{issue_number}\n"
            f"- PR title should start with 'Fix #{issue_number}:'"
        )

        payload = {
            "prompt": prompt,
            "title": f"Fix: #{issue_number} — {issue_title}",
            "tags": [f"issue-{issue_number}", "fix"],
            "repos": [repo],
        }
        if self.fix_playbook_id:
            payload["playbook_id"] = self.fix_playbook_id

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/sessions",
                headers=self.headers,
                json=payload,
                timeout=30.0,
            )
            resp.raise_for_status()
            data = resp.json()
            logger.info("Fix session created for issue #%d: session_id=%s", issue_number, data.get("session_id"))
            return data

    async def get_session(self, session_id: str) -> dict:
        """Get the current status of a Devin session via the list endpoint."""
        # The v3 single-session GET returns 403 with service-user keys,
        # so we use the list endpoint filtered by session_id instead.
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/sessions",
                headers=self.headers,
                params={"session_id": session_id, "limit": 1},
                timeout=30.0,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if not items:
                logger.warning("Session %s not found in list response", session_id)
                return {"status": "unknown"}
            session = items[0]
            logger.info("Session %s poll: status=%s detail=%s", session_id, session.get("status"), session.get("status_detail", ""))
            return session

    async def list_sessions(self, tag: str = None) -> list[dict]:
        """List Devin sessions, optionally filtered by tag."""
        params = {}
        if tag:
            params["tag"] = tag
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/sessions",
                headers=self.headers,
                params=params,
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json().get("items", [])

    async def send_message(self, session_id: str, message: str) -> dict:
        """Send a follow-up message to a running Devin session."""
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/sessions/{session_id}/messages",
                headers=self.headers,
                json={"message": message},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()
