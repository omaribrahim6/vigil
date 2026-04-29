"""Environment + feature-flag configuration. Each external source is independently
optional; the rest of the app reads `Settings.has_*` flags and degrades gracefully
when a key isn't set."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "backend" / ".env", override=False)


@dataclass(frozen=True)
class Settings:
    gcp_project_id: str
    bq_data_project: str
    anthropic_api_key: str | None
    anthropic_model: str
    aws_bearer_token_bedrock: str | None
    aws_region: str
    bedrock_model_id: str
    opensanctions_api_key: str | None
    tavily_api_key: str | None
    canlii_api_key: str | None
    backend_port: int

    @property
    def has_anthropic_direct(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def has_bedrock(self) -> bool:
        return bool(self.aws_bearer_token_bedrock)

    @property
    def has_anthropic(self) -> bool:
        """True if either Bedrock or direct Anthropic is configured."""
        return self.has_bedrock or self.has_anthropic_direct

    @property
    def has_opensanctions(self) -> bool:
        return bool(self.opensanctions_api_key)

    @property
    def has_tavily(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def has_canlii(self) -> bool:
        return bool(self.canlii_api_key)


def _env(name: str, default: str | None = None) -> str | None:
    v = os.getenv(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def get_settings() -> Settings:
    return Settings(
        gcp_project_id=_env("GCP_PROJECT_ID", "agency2026ot-kova-0429") or "agency2026ot-kova-0429",
        bq_data_project=_env("BQ_DATA_PROJECT", "agency2026ot-data-1776775157")
        or "agency2026ot-data-1776775157",
        anthropic_api_key=_env("ANTHROPIC_API_KEY"),
        anthropic_model=_env("ANTHROPIC_MODEL", "claude-sonnet-4-20250514")
        or "claude-sonnet-4-20250514",
        aws_bearer_token_bedrock=_env("AWS_BEARER_TOKEN_BEDROCK"),
        aws_region=_env("AWS_REGION", "us-east-1") or "us-east-1",
        bedrock_model_id=_env("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-5-20250929-v1:0")
        or "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
        opensanctions_api_key=_env("OPENSANCTIONS_API_KEY"),
        tavily_api_key=_env("TAVILY_API_KEY"),
        canlii_api_key=_env("CANLII_API_KEY"),
        backend_port=int(_env("BACKEND_PORT", "8000") or "8000"),
    )


SETTINGS = get_settings()
DATA_PROJECT = SETTINGS.bq_data_project
CACHE_DIR = REPO_ROOT / "cache"
SCREENINGS_DIR = CACHE_DIR / "screenings"
SCREENINGS_DIR.mkdir(parents=True, exist_ok=True)
