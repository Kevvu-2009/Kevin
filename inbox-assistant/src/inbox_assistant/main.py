"""Command-line entry point.

inbox-assistant run --client demo-cottage --dry-run [--eml-dir tests/fixtures]
inbox-assistant report --client demo-cottage
"""

from __future__ import annotations

import argparse
import logging
import sys
import textwrap
from collections import Counter
from pathlib import Path

from inbox_assistant.classifier import StubClassifier
from inbox_assistant.config import ConfigError, load_client, load_secrets
from inbox_assistant.mail_client import DryRunMailbox, EmlDirMailbox
from inbox_assistant.models import Action, Outcome
from inbox_assistant.pipeline import Pipeline
from inbox_assistant.report import monthly_report
from inbox_assistant.responder import StubResponder
from inbox_assistant.store import MemoryStore

DEFAULT_EML_DIR = Path("tests/fixtures")

_ACTION_TEXT = {
    Action.SKIP: "SKIP (filtered before AI)",
    Action.IGNORE: "IGNORE (spam, log only)",
    Action.FLAG: "FLAG for owner (\\Flagged + Needs-Owner), no reply",
    Action.DRAFT: "SAVE DRAFT",
    Action.DRAFT_AND_FLAG: "SAVE DRAFT + FLAG for owner",
    Action.SEND: "SEND via SMTP",
    Action.ERROR: "ERROR (flag for owner)",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="inbox-assistant",
        description="Sorts a small business's email and drafts replies from its knowledge base.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="show detailed logs")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process new email for one client")
    run.add_argument("--client", required=True, help="client folder name under clients/")
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="change nothing in the mailbox; print what would have been done",
    )
    run.add_argument(
        "--eml-dir",
        type=Path,
        help=f"read .eml files from this folder, not a real inbox (default: {DEFAULT_EML_DIR})",
    )
    run.add_argument("--clients-dir", type=Path, default=Path("clients"))
    run.add_argument("--env-file", type=Path, help="path to .env (default: ./.env)")

    report = sub.add_parser("report", help="monthly statistics for one client")
    report.add_argument("--client", required=True)
    report.add_argument("--month", help="YYYY-MM (default: last month)")
    return parser


def _indent(text: str, prefix: str = "    │ ") -> str:
    return textwrap.indent(text.rstrip("\n"), prefix, predicate=lambda _line: True)


def format_outcome(outcome: Outcome, dry_run: bool) -> str:
    email = outcome.email
    verb = "WOULD " if dry_run else ""
    lines = [f"── {outcome.source} " + "─" * max(0, 60 - len(outcome.source))]
    if email:
        sender = f"{email.from_name} <{email.from_addr}>" if email.from_name else email.from_addr
        lines += [f"  From:      {sender}", f"  Subject:   {email.subject}"]
    cls = outcome.classification
    if cls:
        human = "yes" if cls.needs_human else "no"
        lines.append(
            f"  Category:  {cls.category}  (language={cls.language}, "
            f"confidence={cls.confidence:.2f}, needs_human={human})"
        )
    lines.append(f"  Action:    {verb}{_ACTION_TEXT[outcome.action]}")
    if outcome.reason:
        lines.append(f"  Reason:    {outcome.reason}")
    if outcome.reply is not None:
        reply = outcome.reply
        lines.append(f"  Reply ({outcome.reply_language}):")
        for header in ("From", "To", "Subject", "In-Reply-To", "References", "Auto-Submitted"):
            if reply[header]:
                lines.append(f"    {header}: {reply[header]}")
        lines.append(_indent(reply.get_content()))
    return "\n".join(lines)


def format_summary(outcomes: list[Outcome]) -> str:
    counts = Counter(o.action for o in outcomes)
    parts = [f"{_ACTION_TEXT[a].split(' (')[0].lower()}: {n}" for a, n in counts.items()]
    return f"{len(outcomes)} email(s) processed — " + (
        ", ".join(parts) if parts else "nothing to do"
    )


def cmd_run(args: argparse.Namespace) -> int:
    if not args.dry_run:
        if args.eml_dir:
            print("Error: an .eml folder is read-only. Add --dry-run.", file=sys.stderr)
        else:
            print(
                "Error: reading a real inbox is not built yet (Milestone 4).\n"
                "For now use: inbox-assistant run --client <name> --dry-run",
                file=sys.stderr,
            )
        return 2

    secrets = load_secrets(args.env_file)
    client = load_client(args.client, args.clients_dir)

    eml_dir = args.eml_dir or DEFAULT_EML_DIR
    try:
        source = EmlDirMailbox(eml_dir)
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    mailbox = DryRunMailbox(source)

    own = {secrets.email_user.lower()} if secrets.email_user else set()
    pipeline = Pipeline(
        client=client,
        mailbox=mailbox,
        classifier=StubClassifier(),
        responder=StubResponder(),
        store=MemoryStore(),
        own_addresses=frozenset(own),
        from_addr=secrets.email_user,
    )

    print(
        f"DRY RUN for '{client.config.business_name}' — reading {eml_dir}/ — nothing will be "
        "written to any mailbox."
    )
    print(
        "Milestone 1: AI calls are STUBBED (keyword rules + template replies), and the skip "
        "filters\n(newsletters, no-reply, auto-replies) are not active until Milestone 2.\n"
    )
    outcomes = pipeline.run()
    for outcome in outcomes:
        print(format_outcome(outcome, dry_run=True))
        print()
    print(format_summary(outcomes))
    print(f"Planned mailbox writes (not performed): {len(mailbox.planned)}")
    return 1 if any(o.action is Action.ERROR for o in outcomes) else 0


def cmd_report(args: argparse.Namespace) -> int:
    try:
        print(monthly_report(args.client, args.month))
    except NotImplementedError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    try:
        if args.command == "run":
            return cmd_run(args)
        return cmd_report(args)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
