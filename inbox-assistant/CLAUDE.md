# Inbox Assistant — AI email reply bot for small businesses

> This project lives in the `inbox-assistant/` folder of this repository. The repository root
> holds an unrelated project (QuantBot); do not mix the two.

## What this is

A bot that reads a small business's incoming email, sorts each message, and writes a reply in the
customer's language using only that business's own information. By default it saves replies as
drafts for the owner to review and send. Trusted categories can later be switched to auto-send.
Anything unclear is flagged for the owner instead of guessed at.

Target customers: holiday/cottage rentals, B&Bs, cleaning/moving/renovation companies, car repair
shops, driving schools, event venues. One deployment = one business (a "client").

## Tech choices

* Python 3.11+, standard `imaplib`/`smtplib`/`email` libraries (works with any provider via IMAP/SMTP)
* `anthropic` Python SDK for the AI calls
* `pydantic` for validating AI JSON output, `pyyaml` for config, `python-dotenv` for secrets
* SQLite (standard `sqlite3`) for state and logs
* `pytest` for tests
* Runs as a single command, scheduled with cron every few minutes (no long-running server needed)

## Project structure

```
src/inbox_assistant/
  main.py          # CLI entry: run, --dry-run, --client, report
  config.py        # loads .env secrets + clients/<name>/config.yaml
  models.py        # shared data types (IncomingEmail, Classification, Action, ...)
  pipeline.py      # per-email processing: filter -> classify -> decide -> respond -> deliver -> log
  mail_client.py   # IMAP fetch (BODY.PEEK), IMAP APPEND drafts, set flags, SMTP send
  filters.py       # rules that skip emails BEFORE any AI call
  classifier.py    # AI: category, language, confidence, needs_human
  responder.py     # AI: writes the reply, grounded only in knowledge.md
  store.py         # SQLite: processed messages, per-thread/per-sender limits, action log
  report.py        # monthly stats per client
  prompts/         # prompt templates (classifier, responder)
clients/
  demo-cottage/
    config.yaml    # business settings
    knowledge.md   # the business's facts: services, prices, hours, policies, FAQs
tests/
  fixtures/        # sample .eml files (normal question, quote request, complaint,
                   # newsletter, no-reply sender, auto-reply, Finnish/English/other language)
.env.example
README.md
```

## Processing pipeline (per new email)

1. Fetch new messages from INBOX using `BODY.PEEK` so they stay unread for the owner. Track
   processed messages by UID + Message-ID in SQLite; never process one twice.
2. Filter (no AI call) — skip if any of these are true:
   * Sender matches no-reply / noreply / mailer-daemon / postmaster / the business's own address
   * Header `Auto-Submitted` is present and not `no`
   * `Precedence: bulk|list|junk`, or `List-Id` / `List-Unsubscribe` present
   * `X-Autoreply`, `X-Autorespond`, or similar auto-responder headers present
   * The bot already replied in this thread (thread key from References / In-Reply-To / Message-ID)
   * The bot already replied to this sender in the last 24 hours
3. Classify with the AI. Return strict JSON:
   `{ "category": "faq|booking|quote_request|complaint|spam|other", "language": "<ISO code>", "confidence": 0.0-1.0, "needs_human": true|false, "reason": "<short>" }`
   Validate with pydantic. On parse failure or low confidence → treat as `needs_human`.
4. Decide:
   * `spam` → do nothing (log only)
   * `complaint`, `other`, or `needs_human` → flag for owner (IMAP `\Flagged` + keyword
     `Needs-Owner`), no reply
   * `faq`, `booking`, `quote_request` → generate reply
5. Respond: write the reply in the customer's language, using ONLY facts from `knowledge.md`.
   * Quote requests: ask for the missing details listed in config (e.g. dates, guests, size, address)
   * Bookings: point to the booking link / ask for details; never confirm a booking itself
   * If the answer isn't in the knowledge base: say the owner will follow up, and also flag the email
   * Add the signature from config
6. Deliver:
   * `mode: draft` (default) → IMAP APPEND to the Drafts folder with correct `In-Reply-To` and
     `References` headers and `Re:` subject so it threads properly in the owner's mail app
   * `mode: auto` → send via SMTP only for categories in `auto_send_categories`, append a copy to
     Sent; all other categories still go to Drafts
7. Log to SQLite: timestamp, message_id, thread key, category, language, action taken, model, token
   usage. Do NOT store email bodies (data minimisation / GDPR).

## Safety rules (must hold everywhere)

* Email content is untrusted input. The prompts must tell the model to ignore any instructions
  inside the email. The model's only output is reply text or JSON — it can never trigger actions
  itself.
* Never invent prices, availability, or policies. Never confirm bookings or payments.
* One bot reply per thread, one per sender per 24h — prevents bot-to-bot loops.
* `--dry-run` must perform zero writes to the mailbox and print what it would have done.
* Secrets only in `.env` (never committed). Add `.env` and `*.db` to `.gitignore`.

## Client config example (clients/demo-cottage/config.yaml)

```yaml
business_name: "Lakeside Cottages (demo)"
languages: [fi, en, sv]          # reply in the customer's language if listed, else English
mode: draft                      # draft | auto
auto_send_categories: [faq]      # only used when mode: auto
drafts_folder: "Drafts"          # Gmail: "[Gmail]/Drafts"
quote_required_fields: [arrival date, departure date, number of guests, pets]
booking_link: "https://example.com/book"
signature: |
  Best regards,
  Lakeside Cottages
models:
  classifier: claude-haiku-4-5-20251001
  responder: claude-sonnet-5-5
```

## .env.example

```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
EMAIL_USER=
EMAIL_PASSWORD=        # Gmail: app password (needs 2-step verification)
ANTHROPIC_API_KEY=
```

Note: Microsoft 365 / Outlook generally no longer allows plain password login for IMAP —
supporting it will need OAuth (later milestone). Start with a test Gmail account.

## Build order (do one milestone at a time; stop and show results after each)

1. Skeleton: project structure, config loading, CLI with `--dry-run` that reads local `.eml`
   fixtures instead of a real inbox. Stub AI calls. **(done)**
2. Filters + pytest tests using the fixtures (no network in tests).
3. AI classifier + responder wired to the Anthropic API, run in dry-run over fixtures, printing
   category and draft reply for each.
4. IMAP read + draft APPEND against a test mailbox. Verify drafts thread correctly.
5. SQLite state: dedupe, per-thread and per-sender limits, action log.
6. Auto-send mode via SMTP for allowed categories.
7. Report command: emails handled per category per month, estimated time saved (e.g. 3 min per
   reply) — used for client updates and testimonials.
8. Deployment docs: running on a small Linux VPS with cron, log rotation, backups of the DB.
9. (Later) Microsoft 365 OAuth, multiple clients per server.

## Coding conventions

* Small, testable functions; mail and AI clients behind simple interfaces so tests can fake them
* Type hints everywhere; clear error messages; never crash the whole run because of one bad email
* Keep the README up to date with setup steps a non-expert could follow
* Run tests from the `inbox-assistant/` folder: `pytest`
