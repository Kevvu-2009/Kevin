# Inbox Assistant

An email assistant for small businesses (cottage rentals, B&Bs, cleaning and repair companies,
driving schools, event venues…). It reads incoming email, sorts each message, and writes a reply
in the customer's language using **only** the business's own information. Replies are saved as
**drafts** for the owner to check and send. Anything unclear is **flagged** for the owner instead
of guessed at.

> **Status: Milestone 1 of 9.** The project skeleton works end to end on sample emails stored as
> files. The AI is **not connected yet** (simple keyword rules stand in for it), the skip filters
> are not active, and it cannot read a real mailbox yet. See [Roadmap](#roadmap).

---

## Setup (about 5 minutes)

You need **Python 3.11 or newer**. Check with:

```bash
python3 --version
```

Then, in a terminal, from this `inbox-assistant` folder:

```bash
# 1. Create an isolated Python environment (once)
python3 -m venv .venv

# 2. Activate it (every time you open a new terminal)
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install the assistant and its test tools
pip install -e ".[dev]"

# 4. Create your secrets file from the template
cp .env.example .env
```

Milestone 1 does not need anything in `.env` yet. Later milestones will need your email login
and an Anthropic API key there. `.env` is never committed to git.

## Try it

Run the assistant over the sample emails in `tests/fixtures/` without touching any mailbox:

```bash
inbox-assistant run --client demo-cottage --dry-run
```

For each email it prints the category, the language it detected, what it **would** do (save a
draft, flag for the owner, ignore spam), and the full draft reply with its threading headers.

Useful options:

| Option | What it does |
|---|---|
| `--client NAME` | Which business to run for (a folder under `clients/`) |
| `--dry-run` | Change nothing; only print what would happen. **Required in Milestone 1.** |
| `--eml-dir FOLDER` | Read `.eml` files from another folder (default `tests/fixtures`) |
| `-v` | Show detailed logs |

To test with your own email: in most mail apps you can save a message as an `.eml` file
("Download message" / "Save as"). Put it in a folder and run with `--eml-dir that-folder`.

## Run the tests

```bash
pytest
```

The tests use only the local sample emails. They make no network calls and need no API key.

## Setting up a business ("client")

Each business has its own folder under `clients/`. Copy `clients/demo-cottage` to start a new one.

**`config.yaml`**: settings:

| Setting | Meaning |
|---|---|
| `business_name` | Shown as the sender name on replies |
| `languages` | Languages the business answers in (ISO codes like `fi`, `en`, `sv`). Customers writing in another language get an English reply. |
| `mode` | `draft` (default): replies go to Drafts for the owner to send. `auto`: replies in `auto_send_categories` are sent automatically (Milestone 6). |
| `auto_send_categories` | Which categories may be auto-sent. Only `faq`, `booking`, `quote_request` are allowed. |
| `drafts_folder` / `sent_folder` | Mailbox folder names. Gmail: `[Gmail]/Drafts` and `[Gmail]/Sent Mail`. |
| `quote_required_fields` | What the reply asks for when someone wants a quote |
| `booking_link` | Where customers are sent to book. The assistant never confirms bookings itself. |
| `min_confidence` | 0–1. If the AI is less sure than this, the email is flagged for the owner. Default 0.7. |
| `signature` | Added to the end of every reply |
| `models` | Which Claude models classify and write replies |

**`knowledge.md`**: the business's facts: services, prices, opening hours, policies, FAQs.
The assistant may **only** use what is written here. If an answer isn't in this file, the reply
says the owner will follow up and the email is flagged. Keep it short, factual and up to date.

## How it decides

| Email is… | What happens |
|---|---|
| A question, booking request or quote request | Reply drafted in the customer's language |
| A complaint, or anything else ("other") | Flagged for the owner, no reply |
| Something the AI is unsure about | Flagged for the owner, no reply |
| Spam | Ignored (logged only) |
| Newsletter, no-reply sender, auto-reply, or a thread the bot already answered | Skipped before any AI call *(Milestone 2)* |

Safety rules:

- Email content is treated as untrusted. The AI is told to ignore any instructions inside an
  email, and it can only produce text. It cannot trigger actions.
- It never invents prices, availability or policies, and never confirms bookings or payments.
- At most one bot reply per thread and one per sender per 24 hours, to prevent bot-to-bot loops
  *(Milestones 2 and 5)*.
- `--dry-run` never writes to the mailbox.
- Email bodies are never stored; the log keeps only metadata.

## Project layout

```
src/inbox_assistant/
  main.py          command line (run / report)
  config.py        loads .env secrets and clients/<name>/ settings
  models.py        shared data types
  pipeline.py      per-email steps: filter → classify → decide → reply → deliver → log
  mail_client.py   reading .eml / IMAP, building threaded replies, dry-run mailbox
  filters.py       skip rules applied before any AI call        (Milestone 2)
  classifier.py    sorts emails; validates AI JSON output        (AI: Milestone 3)
  responder.py     writes replies from knowledge.md              (AI: Milestone 3)
  store.py         processed messages + action log               (SQLite: Milestone 5)
  report.py        monthly statistics                            (Milestone 7)
  prompts/         AI instructions (drafts)
clients/demo-cottage/   example business
tests/                  automated tests; tests/fixtures/ has the sample emails
```

## Roadmap

1. ✅ Skeleton: config, CLI, dry-run over `.eml` files, stubbed AI
2. Skip filters (no-reply, auto-replies, mailing lists, loop protection)
3. Real AI classifier and reply writer (Anthropic API)
4. Read a real inbox over IMAP and save drafts to it
5. SQLite state: never process twice, per-thread/per-sender limits, action log
6. Auto-send mode via SMTP for allowed categories
7. Monthly report: emails handled per category, estimated time saved
8. Deployment guide: Linux server, cron, log rotation, backups
9. Later: Microsoft 365 (OAuth), several businesses per server

Note: Microsoft 365 / Outlook generally no longer allows plain password login over IMAP, so it
needs OAuth (milestone 9). Start with a test Gmail account and a Gmail **app password**.
