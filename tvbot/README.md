# TradingView → Webhook → Bybit Perps Execution Bot

A production-shaped automated trading system. TradingView generates signals; a
FastAPI server on your own VPS does every piece of execution, sizing and risk
management against the Bybit USDT-perpetual API.

```
┌──────────────┐   alert webhook    ┌─────────────────┐   ccxt/REST   ┌────────┐
│ TradingView  │ ─────────────────► │  Your VPS       │ ────────────► │ Bybit  │
│ Pine v6      │   HTTPS POST JSON  │  FastAPI + SQLite│              │ perps  │
│ strategy     │                    │  sizing / risk   │ ◄──────────  │        │
└──────────────┘                    └─────────────────┘  reconcile    └────────┘
```

## The architectural constraint that shapes everything

**TradingView has no order-execution API.** There is no `tradingview.place_order()`.
The only outbound channel is an alert webhook that POSTs a JSON body to a URL you
control. Every order, every size, every stop is placed by your server against the
exchange. TradingView is a signal generator and nothing more.

This has a direct consequence for security: TradingView cannot sign its requests.
The shared secret in the payload is a bearer token that traverses the wire in
plaintext inside the POST body. TLS and the IP allowlist are the real perimeter,
and the server treats every payload as hostile — it re-derives sizing, re-validates
the reward:risk ratio, re-checks the volatility regime, and refuses stale bars.

---

## Contents

- [Quick start](#quick-start)
- [How a trade flows through the system](#how-a-trade-flows-through-the-system)
- [TradingView alert setup](#tradingview-alert-setup)
- [Exposing the webhook safely](#exposing-the-webhook-safely)
- [Environment variable reference](#environment-variable-reference)
- [Risk controls and kill switches](#risk-controls-and-kill-switches)
- [Operations](#operations)
- [Go-live checklist](#go-live-checklist)
- [Known limitations](#known-limitations)

---

## Quick start

```bash
cd tvbot
python3.11 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt

cp .env.example .env
# Edit .env: at minimum set WEBHOOK_SECRET. MODE=DRY_RUN needs no credentials.
chmod 600 .env

.venv/bin/python -m pytest          # 91 tests, no network required
MODE=DRY_RUN .venv/bin/python -m app.main
```

Then in another shell:

```bash
curl -s localhost:8000/healthz | python3 -m json.tool
```

`DRY_RUN` wires the app to an in-memory simulated exchange. Nothing reaches a
venue, but the entire pipeline — validation, sizing, risk gates, order flow,
reconciliation — runs exactly as it does in production.

### File layout

```
tvbot/
├── pine/strategy.pine          # signal generator (Pine v6)
├── app/
│   ├── config.py               # settings + startup validation
│   ├── models.py               # webhook schema, enums, timeframe maths
│   ├── sizing.py               # position sizing, lot rounding, RR validation
│   ├── state.py                # SQLite: signals, orders, positions, fills
│   ├── risk.py                 # pre-trade gates and kill switches
│   ├── exchange.py             # ccxt Bybit client + paper simulator
│   ├── engine.py               # entry pipeline
│   ├── reconcile.py            # startup + 30s repair loop, OCO
│   ├── notify.py               # Telegram
│   └── main.py                 # FastAPI, webhook ingress, logging
├── tests/
├── systemd/tradingbot.service
├── .env.example
└── requirements.txt
```

`config.py` and `engine.py` are additions to the originally specified tree:
configuration was pulled out so `sizing`/`risk`/`state` stay importable without
pydantic or ccxt, and the entry pipeline was separated from the HTTP layer so it
can be tested without a running server.

---

## How a trade flows through the system

1. **Bar closes on TradingView.** The Pine strategy evaluates once, on the
   confirmed close, and fires `alert()` with a JSON payload.
2. **POST arrives at `/webhook`.** Checks run cheapest-first: IP allowlist →
   JSON parse → schema validation → constant-time secret comparison →
   reconciliation gate → idempotency claim.
3. **The claim is committed synchronously**, then the server returns `200` and
   executes out of band. TradingView's client times out long before a 45-second
   limit-order wait completes, so acknowledging receipt and executing
   asynchronously is the only workable shape — and it is safe precisely because
   the duplicate-suppressing claim already landed in the database.
4. **Risk gates.** Halt switch, staleness, timeframe, RR band, stop-distance
   band, position caps, daily loss limit, consecutive losses.
5. **Sizing, server-side.** `qty = (equity × risk_pct) / |entry − stop|`,
   floored to the lot step, checked against exchange minimums and the leverage cap.
   Equity is fetched live from the exchange on every signal, never cached.
6. **Entry order.** A limit order priced at most `MAX_SLIPPAGE_PCT` through the
   signal price — it fills at the touch or better, and simply does not fill if
   the market has already run. Unfilled after the timeout → cancelled, not chased.
7. **Protection.** Reduce-only stop-market first, then reduce-only take-profit
   limit, both sized from the position the **exchange** reports.
8. **Reconcile loop, every 30s.** Verifies the invariant that every open position
   has a live stop, resizes drifted exits, cancels OCO siblings, and closes out
   local state when the venue is flat.

---

## TradingView alert setup

### 1. Add the strategy to a chart

1. Open a **Bybit** chart at the resolution you configured — `BYBIT:BTCUSDT.P`
   on the **1H** timeframe.
2. Pine Editor → paste `pine/strategy.pine` → **Save** → **Add to chart**.
3. Open the strategy settings and set **Webhook shared secret** to the same
   value as `WEBHOOK_SECRET` in your `.env`.

> Do not publish this script publicly while a real secret is in the input
> default. Anyone who can read the script can read the secret.

### 2. Sanity-check the backtest

Open **Strategy Tester**. Before trusting anything, confirm:

- Win rate is meaningfully **below 50%** — a fixed 1:3 target that wins half the
  time indicates lookahead bias somewhere.
- Trade count is high enough to mean anything (aim for 50+ over the sample).
- Commission is modelled (the script sets 0.055% per side for Bybit taker).

Read the repaint notes at the top of `strategy.pine` before drawing conclusions.

### 3. Create the alert

1. Click the **clock icon** → **Create Alert**.
2. **Condition**: select the strategy, then choose **`alert()` function calls only**.
   This is the important one. Do *not* use "Order fills only" — the payload is
   built by the script's own `alert()` calls.
3. **Expiration**: set **Open-ended** (requires a paid TradingView plan).
4. **Alert name**: anything.
5. **Message**: leave it completely **empty**. The script generates the full JSON.
   Anything you type here would replace the payload and break the integration.
6. **Notifications** tab → tick **Webhook URL** → enter your endpoint:

   ```
   https://bot.yourdomain.com/webhook
   ```

7. **Create**.

Repeat per symbol. Each chart needs its own alert.

### 4. Verify

Watch the log while the next bar closes:

```bash
tail -f logs/tradingbot.jsonl | grep -E 'webhook_accepted|signal_rejected'
```

A `webhook_ip_rejected` entry means the allowlist needs updating. A
`webhook_bad_secret` means the Pine input and `.env` disagree.

### Payload schema

The Pine script emits exactly this. Paste it into TradingView's message box only
if you are testing by hand:

```json
{
  "secret": "<shared secret>",
  "signal_id": "BTCUSDT.P-60-1730812800000",
  "action": "entry",
  "side": "long",
  "symbol": "BTCUSDT.P",
  "entry": 64210.5,
  "stop": 63500.0,
  "target": 66341.5,
  "timeframe": "60",
  "bar_time": 1730809200000,
  "bar_close_time": 1730812800000
}
```

| Field | Notes |
|---|---|
| `secret` | Must equal `WEBHOOK_SECRET`. Compared with `hmac.compare_digest`. |
| `signal_id` | Unique per alert. Duplicates are acknowledged and ignored. |
| `action` | Only `entry` is accepted. Exits are managed server-side. |
| `side` | `long` or `short`. Must agree with the price geometry. |
| `symbol` | TradingView ticker, mapped to a ccxt symbol via `SYMBOL_MAP`. |
| `entry`/`stop`/`target` | Long needs `stop < entry < target`; short mirrors. Implied RR must land in `[RR_MIN, RR_MAX]`. |
| `bar_time` | Bar **open** time in ms — this is what TradingView's `{{time}}` gives you. |
| `bar_close_time` | Bar **close** time in ms. Optional; derived as `bar_time + timeframe` when absent. |

**Why both timestamps exist.** `bar_time` is the bar's *open*. On a 1H chart a
freshly closed bar carries a `bar_time` that is already 3,600,000 ms old, so
comparing it against a 90-second freshness window rejects 100% of signals.
Widening the window to an hour to "fix" that is worse: it happily accepts an
hour-old signal replayed after a VPS restart. The server prefers the explicit
close time and derives it when absent. See
`tests/test_validation.py::test_bar_time_alone_is_the_bar_open_and_must_not_be_used_directly`.

---

## Exposing the webhook safely

The app binds to `127.0.0.1` by design. **Never expose the port directly, and
never serve this over plain HTTP** — the shared secret is in the request body.

### Option A: Cloudflare Tunnel (recommended)

No inbound ports, no certificate management, and the origin stays unreachable
from the internet.

```bash
# Install cloudflared, then:
cloudflared tunnel login
cloudflared tunnel create tradingbot
cloudflared tunnel route dns tradingbot bot.yourdomain.com
```

`/etc/cloudflared/config.yml`:

```yaml
tunnel: tradingbot
credentials-file: /root/.cloudflared/<TUNNEL-ID>.json

ingress:
  - hostname: bot.yourdomain.com
    path: ^/webhook$
    service: http://127.0.0.1:8000
  - service: http_status:404
```

```bash
cloudflared service install
systemctl enable --now cloudflared
```

The `path` restriction means `/status` and `/healthz` are not reachable from the
internet — query them over SSH instead.

Because traffic arrives from Cloudflare rather than TradingView directly, set:

```
TRUST_PROXY_HEADERS=true
```

and add a [Cloudflare WAF rule](https://developers.cloudflare.com/waf/) limiting
`/webhook` to TradingView's source addresses, so the allowlist is enforced at the
edge where the client IP is trustworthy.

### Option B: nginx + Let's Encrypt

```nginx
server {
    listen 443 ssl http2;
    server_name bot.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/bot.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/bot.yourdomain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # Enforce the allowlist here too - nginx sees the true peer address.
    location /webhook {
        allow 52.89.214.238;
        allow 34.212.75.30;
        allow 54.218.53.128;
        allow 52.32.178.7;
        deny  all;

        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_read_timeout 30s;
    }

    location / { return 404; }
}

server {
    listen 80;
    server_name bot.yourdomain.com;
    return 301 https://$host$request_uri;
}
```

```bash
certbot --nginx -d bot.yourdomain.com
```

With nginx in front, set `TRUST_PROXY_HEADERS=true`.

> TradingView's published source addresses change from time to time. Verify
> against <https://www.tradingview.com/support/solutions/43000529348/> and keep
> `IP_ALLOWLIST` in sync — a silently stale allowlist looks exactly like a dead
> strategy.

---

## Environment variable reference

### Mode and credentials

| Variable | Default | Meaning |
|---|---|---|
| `MODE` | `TESTNET` | `DRY_RUN`, `TESTNET`, or `LIVE`. |
| `LIVE_CONFIRM` | — | Must equal `I_UNDERSTAND_THIS_TRADES_REAL_MONEY` when `MODE=LIVE`. |
| `BYBIT_API_KEY` / `BYBIT_API_SECRET` | — | Required for `TESTNET` and `LIVE`. Never grant withdrawal permission. |

### Webhook security

| Variable | Default | Meaning |
|---|---|---|
| `WEBHOOK_SECRET` | — | Required, minimum 16 chars. `openssl rand -hex 32`. |
| `IP_ALLOWLIST_ENABLED` | `true` | Enforce the source-address allowlist. |
| `IP_ALLOWLIST` | TradingView IPs | Comma-separated. |
| `TRUST_PROXY_HEADERS` | `false` | Honour `X-Forwarded-For`. Only enable behind a proxy you control — otherwise it is trivially spoofable. |

### Instruments

| Variable | Default | Meaning |
|---|---|---|
| `SYMBOL_MAP` | `BTCUSDT.P=BTC/USDT:USDT,ETHUSDT.P=ETH/USDT:USDT` | TradingView ticker → ccxt symbol. |
| `EXPECTED_TIMEFRAME` | `60` | Signals on other resolutions are refused. |

### Sizing and risk

| Variable | Default | Meaning |
|---|---|---|
| `RISK_PCT` | `0.005` | Fraction of equity risked per trade. |
| `MAX_LEVERAGE` | `3.0` | Notional cap as a multiple of equity. |
| `MAX_POSITIONS_TOTAL` | `2` | Across all symbols. |
| `MAX_POSITIONS_PER_SYMBOL` | `1` | Also enforced by a partial unique index in SQLite. |
| `RR_MIN` / `RR_MAX` | `2.9` / `3.1` | Accepted reward:risk band. |
| `STOP_DIST_MIN_PCT` / `STOP_DIST_MAX_PCT` | `0.004` / `0.03` | Volatility-regime gate, re-validated server-side. |

### Kill switches

| Variable | Default | Meaning |
|---|---|---|
| `DAILY_LOSS_LIMIT_PCT` | `0.03` | Halt new entries for the UTC day at −3% from the day's opening equity. |
| `MAX_CONSECUTIVE_LOSSES` | `5` | Halt after this many losing trades in a row. |
| `HALT_FILE` | `./HALT` | Presence of this file stops new entries immediately. |
| `HALT` | `false` | Environment equivalent. |

### Execution and resilience

| Variable | Default | Meaning |
|---|---|---|
| `MAX_SIGNAL_AGE_SEC` | `90` | Measured from the bar **close**. |
| `ENTRY_FILL_TIMEOUT_SEC` | `45` | Then cancel; never chase. |
| `MAX_SLIPPAGE_PCT` | `0.0015` | Worst-price bound on entry. |
| `RECONCILE_INTERVAL_SEC` | `30` | Background repair cadence. |
| `RETRY_ATTEMPTS` | `5` | Per exchange call, exponential backoff with jitter. |

### Persistence, logging, notifications

| Variable | Default | Meaning |
|---|---|---|
| `DB_PATH` | `./data/tradingbot.sqlite3` | SQLite state. Back this up. |
| `LOG_FILE` | `./logs/tradingbot.jsonl` | Rotating structured JSON, 25 MB × 10. |
| `LOG_LEVEL` | `INFO` | |
| `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` | — | Optional but strongly recommended. |
| `NOTIFY_DEDUP_SEC` | `300` | Suppression window per alert key. |

---

## Risk controls and kill switches

**Stopping new entries never touches existing positions or their stops.** A
kill switch that flattened your book would turn a risk limit into a liquidation
event.

| Control | Trigger | Effect |
|---|---|---|
| Manual halt | `touch HALT` or `HALT=true` | New entries refused immediately, no restart needed. |
| Daily loss limit | Equity ≤ −3% from the day's UTC-midnight anchor | New entries refused until 00:00 UTC. The anchor is written once per day and survives restarts, so a mid-drawdown restart does not hand the bot a fresh budget. |
| Consecutive losses | 5 losing trades in a row | New entries refused until a winner or manual DB edit. |
| Position caps | 1 per symbol, 2 total | Enforced in the risk gate *and* by a SQLite partial unique index. |
| RR sanity band | Implied RR outside 2.9–3.1 | Signal rejected — the alert is malformed or the Pine was edited. |
| Stop-distance band | Outside 0.4%–3.0% | Signal rejected. This is what bounds implied leverage. |
| Staleness | Bar closed > 90s ago | Signal rejected. |
| Reconciliation gate | Startup reconcile failed | **All** webhooks refused with `503`. |

To halt immediately:

```bash
touch /opt/tradingbot/HALT     # stop new entries; open positions keep their stops
```

To resume:

```bash
rm /opt/tradingbot/HALT
```

---

## Operations

### Deploying to a VPS

```bash
sudo useradd -r -s /usr/sbin/nologin -d /opt/tradingbot tradingbot
sudo mkdir -p /opt/tradingbot/{data,logs}
sudo rsync -a tvbot/ /opt/tradingbot/
cd /opt/tradingbot
sudo -u tradingbot python3.11 -m venv .venv
sudo -u tradingbot .venv/bin/pip install -r requirements.txt

sudo cp .env.example .env && sudo nano .env
sudo chown -R tradingbot:tradingbot /opt/tradingbot
sudo chmod 600 /opt/tradingbot/.env

sudo cp systemd/tradingbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tradingbot
sudo systemctl status tradingbot
```

**Set the VPS clock properly.** The staleness check compares against local time;
a host drifting by more than 90 seconds rejects every signal (or, drifting the
other way, trips the `future_signal` guard).

```bash
sudo timedatectl set-ntp true && timedatectl status
```

### Monitoring

```bash
journalctl -u tradingbot -f                          # live
curl -s localhost:8000/status | python3 -m json.tool # positions + risk snapshot
tail -f /opt/tradingbot/logs/tradingbot.jsonl | grep -i critical
```

Telegram messages are sent for: entry filled, exit filled, stop missing, position
adopted, kill switch triggered, and any unhandled exception.

### Backups

```bash
sqlite3 /opt/tradingbot/data/tradingbot.sqlite3 ".backup '/backup/bot-$(date +%F).sqlite3'"
```

Losing the database loses idempotency history and open-position records. The
reconcile loop will re-adopt live positions and re-protect them, but with
synthesised stop levels rather than your strategy's — so keep backups.

### Tests

```bash
cd tvbot && .venv/bin/python -m pytest -v
```

91 tests, no network, no credentials. Covers sizing edges and lot-rounding
traps, RR and staleness validation, idempotency under concurrency, the full
mocked-exchange lifecycle (entry → stop/TP → stop fill → sibling cancellation),
crash recovery, and webhook authentication.

---

## Go-live checklist

Work down this list. Do not skip to the end.

**Configuration**

- [ ] `WEBHOOK_SECRET` is a fresh 32-byte random value, identical in `.env` and the Pine input
- [ ] `.env` is `chmod 600` and owned by the service user
- [ ] `.env` is **not** in git (`git check-ignore .env` should print the path)
- [ ] API key has Contract (orders + positions) and wallet-read permission, **no withdrawal**
- [ ] API key is IP-bound to the VPS
- [ ] `SYMBOL_MAP` matches the charts your alerts run on
- [ ] `EXPECTED_TIMEFRAME` matches the chart resolution

**Infrastructure**

- [ ] Webhook reachable over **HTTPS only**; plain HTTP returns a redirect or 404
- [ ] `IP_ALLOWLIST` verified against TradingView's current published addresses
- [ ] `TRUST_PROXY_HEADERS` is `true` **only** if a proxy you control sits in front
- [ ] NTP is synchronised (`timedatectl status`)
- [ ] systemd unit enabled; `systemctl restart tradingbot` recovers cleanly
- [ ] Telegram delivers a startup message

**Validation, in order**

- [ ] `pytest` passes
- [ ] `MODE=DRY_RUN` — fire a hand-crafted `curl` payload, confirm sizing in the log
- [ ] `MODE=TESTNET` — run for **at least a week** and confirm real fills
- [ ] On testnet, confirm every one of these by observation, not by reading code:
  - [ ] Entry fills and the stop appears within seconds
  - [ ] The take-profit appears at exactly 3× the stop distance
  - [ ] Killing the process mid-position and restarting restores state, and the log shows a clean reconcile
  - [ ] Manually cancelling the stop on the Bybit UI produces a `STOP WAS MISSING` alert and a replacement within 30s
  - [ ] `touch HALT` blocks the next signal; open positions keep their stops
  - [ ] A duplicate webhook produces `"status": "duplicate"` and no second order
- [ ] Backtest reviewed with commission modelled and the repaint notes read

**Going live**

- [ ] Database backed up and a restore tested
- [ ] `MODE=LIVE` and `LIVE_CONFIRM=I_UNDERSTAND_THIS_TRADES_REAL_MONEY`
- [ ] Start with a **small** account — size the account so a total loss is survivable
- [ ] Consider `RISK_PCT=0.0025` for the first month
- [ ] Watch the first live entry end to end, with the Bybit UI open beside the log

---

## Known limitations

Stated plainly, because each one can cost money:

1. **Fees and funding are not modelled in realised PnL.** The reconciler computes
   gross PnL from entry and exit prices. Consecutive-loss and daily-loss counters
   are therefore slightly optimistic. Bybit's own PnL is authoritative.
2. **The 30-second reconcile interval is the OCO window.** If the take-profit
   fills, the sibling stop can survive for up to 30 seconds. It is reduce-only,
   so the venue will normally reject it against a flat position, but a new
   position opened inside that window on the same symbol is theoretically
   exposed. The per-symbol position cap makes this very unlikely.
3. **Adopted positions get synthesised levels.** A position found with no local
   record is protected at `STOP_DIST_MAX_PCT` with a matching 1:3 target. That is
   a guess about your intent, which is why it raises a `CRITICAL` alert.
4. **Backtest fills are optimistic.** `process_orders_on_close=true` fills at the
   signal bar's close; live, a bounded-slippage limit is sent moments later and
   abandons the signal if price has already moved. Expect fewer live trades than
   the Strategy Tester shows.
5. **Single-process, single-VPS.** No HA. If the box dies mid-position, the stop
   still lives on the exchange — this is exactly why stops are exchange-resident
   rather than simulated locally — but nothing will manage the trade until the
   process returns.
6. **SQLite writes block the event loop.** Fine at 1H cadence (a handful of writes
   per hour); revisit before moving to sub-minute timeframes.
7. **The shared secret is a bearer token.** TradingView cannot sign requests.
   Anyone who can read your Pine script or intercept a plaintext POST can forge a
   signal. The server-side sizing, RR band and position caps bound the damage; TLS
   and the IP allowlist prevent it.

---

## Disclaimer

This software places real orders with real money when configured to do so.
Perpetual futures are leveraged instruments and you can lose more than your
intended risk during gaps, liquidity holes and exchange outages. The strategy
here is a reasonable starting point, not a validated edge — a fixed 1:3 target
with no trailing produces long losing streaks by construction. Test on testnet
until you are bored of it, then start smaller than feels worthwhile.
