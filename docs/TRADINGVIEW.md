# Connecting TradingView to QuantBot

TradingView decides **when** to trade. QuantBot decides **how much** and
**whether it's allowed**: every alert passes the same risk gate, position
sizing, order retries and kill switch as the built-in strategies.

```
TradingView alert ──HTTPS POST──▶ /webhook/tradingview ──▶ risk checks ──▶ paper broker / Hyperliquid
```

## 1. Start the webhook server (paper trading)

```bash
# A long random secret; TradingView must send the same value.
export TRADINGVIEW_WEBHOOK_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(24))")
echo $TRADINGVIEW_WEBHOOK_SECRET          # copy this for step 3

PYTHONPATH=src python -m quantbot.cli webhook --venue paper --port 8080
```

Check it: `curl localhost:8080/health` and `curl localhost:8080/api/status`.

## 2. Make it reachable from the internet

TradingView only sends webhooks to **port 80 or 443** on a public URL. Options:

- **Quick test:** a tunnel such as `cloudflared tunnel --url http://localhost:8080`
  or `ngrok http 8080`, which gives you an `https://…` URL.
- **Always-on:** a small VPS behind Caddy/nginx with HTTPS, or a host like
  Railway or Fly.io. The bot has to run 24/7 or alerts are lost.

Your webhook URL is `https://<your-host>/webhook/tradingview`.

## 3. Create the alert in TradingView

Webhooks need a paid TradingView plan.

**Option A — use the included Pine strategy** (`docs/tradingview/quantbot_ema_atr.pine`):

1. Pine Editor → paste the file → *Add to chart*. Keep it **private**.
2. Strategy settings → *Webhook secret* → paste your secret.
3. Create alert → Condition: *QuantBot EMA/ATR* → *Order fills only*.
4. Message: `{{strategy.order.alert_message}}`
5. Notifications → tick *Webhook URL* → paste your URL.

**Option B — any indicator or your own strategy.** Put JSON like this in the
alert message:

```json
{
  "secret": "YOUR_SECRET",
  "action": "{{strategy.order.action}}",
  "symbol": "{{ticker}}",
  "price": {{close}},
  "stop": 61250.5,
  "take_profit": 66000,
  "strategy": "my_strategy",
  "id": "{{timenow}}"
}
```

| Field | Required | Notes |
|---|---|---|
| `secret` | yes | Must equal `TRADINGVIEW_WEBHOOK_SECRET` |
| `action` | yes | `buy`/`long` opens; `sell`/`close`/`exit`/`flat` closes |
| `symbol` | yes | `BTCUSDT`, `BINANCE:BTCUSDT`, `BTCUSDT.P`, `BTC/USDT` all work |
| `price` | paper: yes | Live mode fetches the price when omitted |
| `stop` | recommended | Below price. Position size = 0.75% of equity ÷ (price − stop). Without it a 5% safety stop is used |
| `take_profit` | no | Above price |
| `id` | recommended | Repeated `id`s are ignored, so a retried alert can't double-trade |

## 4. Going live (Hyperliquid)

Only after the paper results look right over a meaningful period:

```bash
export QUANTBOT_MODE=live            # explicit opt-in; refuses to start otherwise
export HYPERLIQUID_SECRET_KEY=...    # API (agent) wallet key – cannot withdraw
export HYPERLIQUID_ACCOUNT_ADDRESS=0x...
PYTHONPATH=src python -m quantbot.cli webhook --venue hyperliquid --port 8080
```

Try `HYPERLIQUID_TESTNET=true` first. In live mode the server also checks
stops and take-profits against live prices every 15 s (`--stop-poll`).

## Security settings

| Env var | Effect |
|---|---|
| `TRADINGVIEW_WEBHOOK_SECRET` | Required, 16+ characters. Wrong or missing secret → 401 |
| `TRADINGVIEW_ALLOWED_IPS` | `tradingview` = accept only TradingView's published IPs; or a comma list. Empty = any |
| `TRADINGVIEW_SYMBOLS` | Optional allowlist, e.g. `BTC/USDT,ETH/USDT` |

## Behaviour and limits

- **Long-only**, one position per symbol. A second `buy` while in a position is
  ignored (`already_open`), and `sell` with no position returns `no_position`.
- All portfolio limits apply: 5 positions max, 3% daily / 8% weekly loss limits,
  and a 20% drawdown kill switch that flattens everything.
- **Paper mode** only sees prices when alerts arrive, so a stop is only checked
  on the next alert for that symbol. Let TradingView send exits too (the Pine
  strategy does this with `strategy.exit`).
- Paper positions live in memory and are reset when the server restarts.
- The response to each alert explains what happened (`opened`, `closed`, `stop`,
  `daily_loss_limit`, …) and every decision is logged.

> ⚠️ Backtests and paper results do not guarantee live performance. Start with
> paper trading, then small size. This is software, not financial advice.
