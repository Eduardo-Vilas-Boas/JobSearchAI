from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPANIES_PATH = REPO_ROOT / "config" / "companies.yaml"


class CompanyConfig(BaseModel):
    name: str
    ats: str
    board_token: str
    canton_hint: str | None = None
    # Short/informal names a company uses to refer to itself in posting prose
    # (e.g. "SonarSource" posts as "Sonar") — Anonymize's NER model can
    # misread these as a PERSON if they're not also exempted.
    aliases: list[str] = []


def load_companies(path: Path = DEFAULT_COMPANIES_PATH) -> list[CompanyConfig]:
    data = yaml.safe_load(path.read_text())
    return [CompanyConfig.model_validate(entry) for entry in data["companies"]]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JOBFIT_", env_file=".env")

    database_url: str = "postgresql+psycopg://jobfit:jobfit@localhost:5432/jobfit"
    raw_storage_dir: Path = REPO_ROOT / "data" / "raw"


settings = Settings()
