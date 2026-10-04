"""Load secrets from .env and per-client settings from clients/<name>/."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from inbox_assistant.models import REPLY_CATEGORIES


class ConfigError(Exception):
    """Raised with a human-readable message when configuration is missing or invalid."""


class Models(BaseModel):
    classifier: str = "claude-haiku-4-5-20251001"
    responder: str = "claude-sonnet-5-5"


class ClientConfig(BaseModel):
    business_name: str = Field(min_length=1)
    languages: list[str] = Field(default_factory=lambda: ["en"], min_length=1)
    mode: Literal["draft", "auto"] = "draft"
    auto_send_categories: list[str] = Field(default_factory=list)
    drafts_folder: str = "Drafts"
    sent_folder: str = "Sent"
    quote_required_fields: list[str] = Field(default_factory=list)
    booking_link: str = ""
    signature: str = ""
    # Classifications below this confidence are treated as needs_human.
    min_confidence: float = Field(default=0.7, ge=0.0, le=1.0)
    models: Models = Field(default_factory=Models)

    model_config = {"extra": "forbid"}

    @field_validator("languages")
    @classmethod
    def _normalise_languages(cls, value: list[str]) -> list[str]:
        out = []
        for lang in value:
            code = str(lang).strip().lower()
            if not re.fullmatch(r"[a-z]{2,3}", code):
                raise ValueError(f"'{lang}' is not an ISO language code like 'fi' or 'en'")
            out.append(code)
        return out

    @model_validator(mode="after")
    def _check_auto_send(self) -> ClientConfig:
        bad = [c for c in self.auto_send_categories if c not in REPLY_CATEGORIES]
        if bad:
            allowed = ", ".join(sorted(REPLY_CATEGORIES))
            raise ValueError(
                f"auto_send_categories contains {bad}; only these can be auto-sent: {allowed}"
            )
        return self


@dataclass(frozen=True)
class Client:
    """Everything the pipeline needs to know about one business."""

    name: str
    config: ClientConfig
    knowledge: str
    path: Path


@dataclass(frozen=True)
class Secrets:
    imap_host: str = ""
    imap_port: int = 993
    smtp_host: str = ""
    smtp_port: int = 587
    email_user: str = ""
    email_password: str = ""
    anthropic_api_key: str = ""

    def __repr__(self) -> str:  # never leak secrets into logs or tracebacks
        return (
            f"Secrets(imap_host={self.imap_host!r}, smtp_host={self.smtp_host!r}, "
            f"email_user={self.email_user!r}, email_password=***, anthropic_api_key=***)"
        )


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} in .env must be a number, got {raw!r}") from exc


def load_secrets(env_file: Path | None = None) -> Secrets:
    """Read secrets from the environment, after loading `.env` if present.

    Nothing is required here; each feature checks for the secrets it needs when it starts.
    """
    load_dotenv(env_file or Path.cwd() / ".env", override=False)
    return Secrets(
        imap_host=os.environ.get("IMAP_HOST", "").strip(),
        imap_port=_int_env("IMAP_PORT", 993),
        smtp_host=os.environ.get("SMTP_HOST", "").strip(),
        smtp_port=_int_env("SMTP_PORT", 587),
        email_user=os.environ.get("EMAIL_USER", "").strip(),
        email_password=os.environ.get("EMAIL_PASSWORD", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", "").strip(),
    )


def _format_validation_error(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors():
        where = ".".join(str(p) for p in err["loc"]) or "(top level)"
        lines.append(f"  - {where}: {err['msg']}")
    return "\n".join(lines)


def load_client(name: str, clients_dir: Path) -> Client:
    """Load and validate clients/<name>/config.yaml and knowledge.md."""
    client_dir = clients_dir / name
    if not client_dir.is_dir():
        available = (
            sorted(p.name for p in clients_dir.iterdir() if p.is_dir())
            if clients_dir.is_dir()
            else []
        )
        hint = f" Available clients: {', '.join(available)}." if available else ""
        raise ConfigError(f"Client folder not found: {client_dir}.{hint}")

    config_path = client_dir / "config.yaml"
    if not config_path.is_file():
        raise ConfigError(f"Missing {config_path}")
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"{config_path} is not valid YAML:\n{exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} must contain key: value settings")

    try:
        config = ClientConfig.model_validate(data)
    except ValidationError as exc:
        raise ConfigError(
            f"{config_path} has invalid settings:\n{_format_validation_error(exc)}"
        ) from exc

    knowledge_path = client_dir / "knowledge.md"
    if not knowledge_path.is_file():
        raise ConfigError(f"Missing {knowledge_path} (the business's facts the bot may use)")
    knowledge = knowledge_path.read_text(encoding="utf-8").strip()
    if not knowledge:
        raise ConfigError(f"{knowledge_path} is empty; the bot needs facts to answer from")

    return Client(name=name, config=config, knowledge=knowledge, path=client_dir)
