import httpx
from app.config import get_settings
from app.models import TrackedIssue


class NotificationService:
    """Sends notifications to Slack when issue status changes."""

    def __init__(self):
        settings = get_settings()
        self.webhook_url = settings.slack_webhook_url

    async def notify_triage_complete(self, issue: TrackedIssue):
        if not self.webhook_url:
            return

        triage = issue.triage_result
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"Issue #{issue.issue_number} triaged",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Title:*\n{issue.title}"},
                    {"type": "mrkdwn", "text": f"*Severity:*\n{triage.severity}"},
                    {"type": "mrkdwn", "text": f"*Effort:*\n{triage.estimated_effort}"},
                    {"type": "mrkdwn", "text": f"*Category:*\n{triage.category}"},
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Suggested approach:*\n{triage.suggested_approach}",
                },
            },
        ]

        await self._send(blocks)

    async def notify_fix_started(self, issue: TrackedIssue):
        if not self.webhook_url:
            return

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"Devin is now working on *#{issue.issue_number}: "
                        f"{issue.title}*\n"
                        f"<{issue.devin_session_url}|View Devin session>"
                    ),
                },
            },
        ]

        await self._send(blocks)

    async def notify_pr_opened(self, issue: TrackedIssue):
        if not self.webhook_url:
            return

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"PR opened for *#{issue.issue_number}: {issue.title}*\n"
                        f"<{issue.pr_url}|Review PR>"
                    ),
                },
            },
        ]

        await self._send(blocks)

    async def _send(self, blocks: list[dict]):
        async with httpx.AsyncClient() as client:
            await client.post(
                self.webhook_url,
                json={"blocks": blocks},
                timeout=10.0,
            )
