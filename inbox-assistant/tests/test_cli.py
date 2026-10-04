from __future__ import annotations

from conftest import CLIENTS, FIXTURES
from inbox_assistant.main import main


def base_args(tmp_path) -> list[str]:
    return ["--clients-dir", str(CLIENTS), "--env-file", str(tmp_path / "missing.env")]


def test_dry_run_prints_plan(tmp_path, capsys):
    code = main(
        [
            "run",
            "--client",
            "demo-cottage",
            "--dry-run",
            "--eml-dir",
            str(FIXTURES),
            *base_args(tmp_path),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "DRY RUN" in out
    assert "WOULD SAVE DRAFT" in out
    assert "WOULD FLAG for owner" in out
    assert "In-Reply-To: <matti-quote-4410@example.fi>" in out
    assert "Planned mailbox writes (not performed)" in out


def test_without_dry_run_refuses(tmp_path, capsys):
    code = main(["run", "--client", "demo-cottage", *base_args(tmp_path)])
    assert code == 2
    assert "Milestone 4" in capsys.readouterr().err


def test_unknown_client_is_a_clear_error(tmp_path, capsys):
    code = main(["run", "--client", "nope", "--dry-run", *base_args(tmp_path)])
    assert code == 2
    assert "Client folder not found" in capsys.readouterr().err


def test_missing_eml_dir(tmp_path, capsys):
    code = main(
        [
            "run",
            "--client",
            "demo-cottage",
            "--dry-run",
            "--eml-dir",
            str(tmp_path / "none"),
            *base_args(tmp_path),
        ]
    )
    assert code == 2
    assert "Email folder not found" in capsys.readouterr().err


def test_report_not_built_yet(capsys):
    assert main(["report", "--client", "demo-cottage"]) == 2
    assert "Milestone 7" in capsys.readouterr().err
