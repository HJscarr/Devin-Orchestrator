from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    devin_api_key: str = ""
    devin_org_id: str = ""
    github_token: str = ""
    github_repo: str = "HJscarr/Spot-Fintech"
    slack_webhook_url: str = ""
    orchestrator_base_url: str = "http://localhost:8000"
    triage_playbook_id: str = ""
    fix_playbook_id: str = ""

    devin_api_base: str = "https://api.devin.ai/v3"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
