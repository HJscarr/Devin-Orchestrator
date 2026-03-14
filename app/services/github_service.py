import httpx
from app.config import get_settings


class GitHubService:
    def __init__(self):
        settings = get_settings()
        self.repo = settings.github_repo
        self.headers = {
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
        }
        self.base_url = f"https://api.github.com/repos/{self.repo}"

    async def get_open_issues(self) -> list[dict]:
        """Fetch all open issues from the target repo."""
        issues = []
        page = 1
        async with httpx.AsyncClient(follow_redirects=True) as client:
            while True:
                resp = await client.get(
                    f"{self.base_url}/issues",
                    headers=self.headers,
                    params={"state": "open", "per_page": 100, "page": page},
                )
                resp.raise_for_status()
                batch = resp.json()
                if not batch:
                    break
                # Filter out pull requests (GitHub returns PRs in issues endpoint)
                issues.extend(
                    i for i in batch if "pull_request" not in i
                )
                page += 1
        return issues

    async def get_issue(self, issue_number: int) -> dict:
        """Fetch a single issue by number."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                f"{self.base_url}/issues/{issue_number}",
                headers=self.headers,
            )
            resp.raise_for_status()
            return resp.json()

    async def post_comment(self, issue_number: int, body: str):
        """Post a comment on an issue."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                f"{self.base_url}/issues/{issue_number}/comments",
                headers=self.headers,
                json={"body": body},
            )
            resp.raise_for_status()
            return resp.json()

    async def find_pr_for_issue(self, issue_number: int) -> str | None:
        """Check if a PR referencing this issue exists. Returns the PR URL or None."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(
                f"{self.base_url}/pulls",
                headers=self.headers,
                params={"state": "open", "per_page": 50},
            )
            resp.raise_for_status()
            for pr in resp.json():
                title = pr.get("title", "").lower()
                body = (pr.get("body") or "").lower()
                branch = pr.get("head", {}).get("ref", "").lower()
                if (
                    f"#{issue_number}" in title
                    or f"#{issue_number}" in body
                    or f"issue-{issue_number}" in branch
                ):
                    return pr.get("html_url", "")
        return None

    async def add_labels(self, issue_number: int, labels: list[str]):
        """Add labels to an issue."""
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.post(
                f"{self.base_url}/issues/{issue_number}/labels",
                headers=self.headers,
                json={"labels": labels},
            )
            resp.raise_for_status()
            return resp.json()
