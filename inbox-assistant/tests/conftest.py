from __future__ import annotations

from pathlib import Path

import pytest

from inbox_assistant.config import Client, load_client
from inbox_assistant.mail_client import RawMessage, parse_email
from inbox_assistant.models import IncomingEmail

PROJECT_DIR = Path(__file__).resolve().parent.parent
FIXTURES = PROJECT_DIR / "tests" / "fixtures"
CLIENTS = PROJECT_DIR / "clients"


@pytest.fixture
def demo_client() -> Client:
    return load_client("demo-cottage", CLIENTS)


def load_fixture(name: str) -> IncomingEmail:
    return parse_email(RawMessage(uid=name, data=(FIXTURES / name).read_bytes()))
