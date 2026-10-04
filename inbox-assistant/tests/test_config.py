from __future__ import annotations

from pathlib import Path

import pytest

from conftest import CLIENTS
from inbox_assistant.config import ConfigError, Secrets, load_client

VALID_YAML = """\
business_name: Test Biz
languages: [FI, en]
signature: Thanks
"""


def make_client(tmp_path: Path, yaml_text: str, knowledge: str | None = "Facts.") -> Path:
    folder = tmp_path / "biz"
    folder.mkdir()
    (folder / "config.yaml").write_text(yaml_text, encoding="utf-8")
    if knowledge is not None:
        (folder / "knowledge.md").write_text(knowledge, encoding="utf-8")
    return tmp_path


def test_demo_client_loads():
    client = load_client("demo-cottage", CLIENTS)
    cfg = client.config
    assert cfg.business_name == "Lakeside Cottages (demo)"
    assert cfg.languages == ["fi", "en", "sv"]
    assert cfg.mode == "draft"
    assert cfg.auto_send_categories == ["faq"]
    assert "number of guests" in cfg.quote_required_fields
    assert cfg.models.classifier.startswith("claude-")
    assert "Check-in" in client.knowledge


def test_defaults_and_language_normalisation(tmp_path):
    client = load_client("biz", make_client(tmp_path, VALID_YAML))
    assert client.config.languages == ["fi", "en"]
    assert client.config.mode == "draft"
    assert client.config.drafts_folder == "Drafts"
    assert client.config.min_confidence == 0.7


@pytest.mark.parametrize(
    "extra, message",
    [
        ("mode: yolo\n", "mode"),
        ("auto_send_categories: [complaint]\n", "only these can be auto-sent"),
        ("languages: [english]\n", "not an ISO language code"),
        ("min_confidence: 2\n", "min_confidence"),
        ("unknown_setting: 1\n", "unknown_setting"),
    ],
)
def test_invalid_settings_give_clear_errors(tmp_path, extra, message):
    root = make_client(tmp_path, VALID_YAML.replace("languages: [FI, en]\n", "") + extra)
    with pytest.raises(ConfigError, match=message):
        load_client("biz", root)


def test_missing_client_lists_available_ones():
    with pytest.raises(ConfigError, match="Available clients: demo-cottage"):
        load_client("nope", CLIENTS)


def test_missing_knowledge_file(tmp_path):
    with pytest.raises(ConfigError, match="knowledge.md"):
        load_client("biz", make_client(tmp_path, VALID_YAML, knowledge=None))


def test_empty_knowledge_file(tmp_path):
    with pytest.raises(ConfigError, match="is empty"):
        load_client("biz", make_client(tmp_path, VALID_YAML, knowledge="  \n"))


def test_invalid_yaml(tmp_path):
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_client("biz", make_client(tmp_path, "business_name: [unclosed\n"))


def test_secrets_repr_hides_passwords():
    text = repr(Secrets(email_user="a@b.c", email_password="hunter2", anthropic_api_key="sk-x"))
    assert "hunter2" not in text and "sk-x" not in text
    assert "a@b.c" in text
