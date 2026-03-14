import logging

import httpx
from app.config import get_settings
from app.models import TrackedIssue

logger = logging.getLogger(__name__)


SEVERITY_EMOJI = {"critical": "\U0001f534", "high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f7e2"}
EFFORT_EMOJI = {"small": "\U0001f7e2", "medium": "\U0001f7e1", "large": "\U0001f534"}


class NotificationService:
    """Sends notifications to Slack when issue status changes."""

    def __init__(self):
        settings = get_settings()
        self.webhook_url = settings.slack_webhook_url

    async def notify_triage_complete(self, issue: TrackedIssue):
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured, skipping triage notification for issue #%d", issue.issue_number)
            return
        logger.info("Sending triage-complete Slack notification for issue #%d", issue.issue_number)

        triage = issue.triage_result
        sev_emoji = SEVERITY_EMOJI.get(triage.severity, "\u26aa")
        eff_emoji = EFFORT_EMOJI.get(triage.estimated_effort, "\u26aa")

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"\U0001f50d *Triage complete \u2014 #{issue.issue_number}*\n"
                        f"{issue.title}"
                    ),
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Severity:*  {sev_emoji} {triage.severity.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*Effort:*  {eff_emoji} {triage.estimated_effort.capitalize()}"},
                    {"type": "mrkdwn", "text": f"*Confidence:*  {int(triage.confidence * 100)}%"},
                ],
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"{triage.suggested_approach[:280]}"},
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Session"},
                        "url": issue.devin_session_url or "",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Create PR"},
                        "action_id": f"approve_{issue.issue_number}",
                        "style": "primary",
                    },
                ],
            },
        ]

        await self._send(blocks)

    async def notify_fix_started(self, issue: TrackedIssue):
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured, skipping fix-started notification for issue #%d", issue.issue_number)
            return
        logger.info("Sending fix-started Slack notification for issue #%d", issue.issue_number)

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"\U0001f6e0\ufe0f *Fix in progress \u2014 #{issue.issue_number}*\n"
                        f"{issue.title}"
                    ),
                },
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Watch Devin"},
                    "url": issue.devin_session_url or "",
                },
            },
        ]

        await self._send(blocks)

    async def notify_pr_opened(self, issue: TrackedIssue):
        if not self.webhook_url:
            logger.warning("Slack webhook URL not configured, skipping PR-opened notification for issue #%d", issue.issue_number)
            return
        logger.info("Sending PR-opened Slack notification for issue #%d", issue.issue_number)

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f"\u2705 *PR ready for review \u2014 #{issue.issue_number}*\n"
                        f"{issue.title}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Review PR"},
                        "url": issue.pr_url or "",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Session"},
                        "url": issue.devin_session_url or "",
                    },
                ],
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
