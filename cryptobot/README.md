# Crypto Bot (Bitvavo): Home Assistant add-on

A self-hosted, rule-based trading bot for Bitvavo. It uses a three-sleeve setup:

| Sleeve | Share | How it works |
|---|---|---|
| **Top 10 Index** | 52% | The 10 largest coins by market cap (excluding stablecoins and wrapped tokens, and only coins with an EUR pair on Bitvavo). Each coin is capped at 30%. Rebalanced monthly. |
| **Top 3 Trend** | 28% | The 3 largest coins, equally weighted. Each is held only while its price is above the 50-day moving average (with ±2% hysteresis); otherwise the bot waits in EUR. |
| **Meme Trend** | 21% | The 5 largest meme coins (CoinGecko "meme-token" category), with the same trend filter. |

**When it trades:** it runs once a day (by default at 00:10 UTC, after the daily candle closes). It only trades when (1) a new month has started, (2) the trend of one of the trend-sleeve coins has flipped, (3) this is the first run, (4) you have just switched from dry-run to live, or (5) the allocation percentages have changed. In those cases it rebalances the whole portfolio to the target weights.

**Safety limits:**
- `dry_run: true` is the default; in this mode no orders are placed.
- `max_turnover_pct`: if a run would turn over a larger share of the portfolio than this, the bot stops and notifies you.
- Coins listed in `exclude_coins` are never touched and are not counted as part of the managed portfolio.
- On an authentication error (e.g. a changed IP address) the bot does not trade and notifies you.

> This is not financial advice. Trading crypto assets is risky.

---

## 1. Prerequisites

- Home Assistant OS (e.g. on a Raspberry Pi) with the Settings → Add-ons menu.
- The Home Assistant Companion app on your phone, for notifications. Set your phone's notify service in the `notify_service` option.
- A Bitvavo account.

## 2. Bitvavo API key (for the dry-run period)

For the dry-run period, create a **read-only** key. That way, if anything goes wrong or the key leaks, nobody can trade with it.

1. Look up your home public IP address, e.g. in a browser: `https://api.ipify.org`
2. Bitvavo → account → Settings → **API** → **Create new API key**. Name: `HA Crypto Bot (read-only)`.
3. Permissions: **only "View information"**. Leave "Trade digital assets" and "Withdraw digital assets" disabled.
4. **IP whitelist:** enter the IP address from step 1.
5. Copy the API key and secret, and confirm the email approval.

If another bot or service currently manages the account, leave its key alone; it keeps running in the meantime.

## 3. Getting the add-on onto Home Assistant

**Recommended: directly from the GitHub repository.** Settings → Add-ons → Add-on Store → ⋮ → **Repositories** → add `https://github.com/Lorant77/ha-cryptobot` → Add. Then skip to step 4.3 (Install). Updates: bump `version` in `config.yaml` and push; Home Assistant will offer the update.

**Without the repository**, the easiest way is the **Samba share** add-on:

1. Settings → Add-ons → **Add-on Store** → search for **Samba share** → Install.
2. On the Configuration tab, set a username and password → Save → Start.
3. In Windows Explorer: `\\homeassistant.local\addons` (on a Mac: Finder → Go → Connect to Server: `smb://homeassistant.local/addons`).
4. Create a `cryptobot` folder there and copy the **contents** of this folder into it, so it looks like this:

```
addons/
└── cryptobot/
    ├── config.yaml
    ├── Dockerfile
    ├── requirements.txt
    ├── README.md
    ├── app/cryptobot/*.py
    └── tests/
```

(Instead of Samba, the "Studio Code Server" or "Advanced SSH & Web Terminal" add-on also works; upload to `/addons/cryptobot`.)

## 4. Installing the add-on

1. Settings → Add-ons → **Add-on Store**.
2. Top right **⋮** menu → **Check for updates** (this re-reads local add-ons).
3. The **Crypto Bot (Bitvavo)** add-on appears (under **Local add-ons** if you copied the files manually) → **Install**.
   - The first install on a Raspberry Pi can take **5–15 minutes**, because the Docker image (Python and the `ccxt` library) is built then. This is normal.

## 5. Configuration (Configuration tab)

The most important options:

| Option | Starting value | Notes |
|---|---|---|
| `api_key`, `api_secret` | the key from step 2 | |
| `operator_id` | `1001` | Required by Bitvavo for orders. Any number you choose, but keep it constant. |
| `dry_run` | **`true`** | Keep it this way for the first few weeks. |
| `run_on_start` | `true` | Runs once immediately on start. |
| `run_time_utc` | `00:10` | That is 01:10 CET in winter and 02:10 CEST in summer. |
| `allocation_*` | 52 / 28 / 21 | The bot normalizes them, so the sum does not have to be exactly 100. |
| `exclude_coins` | e.g. `["ADA"]` | Coins the bot never touches. |
| `min_trade_eur` | `10` | Deviations smaller than this are not traded. |
| `max_turnover_pct` | `60` | Safety brake. |
| `notify_service` | e.g. `notify.mobile_app_<your_phone>` | Pick from the `notify.mobile_app…` entries under Developer tools → Actions. |
| `signal_url` | empty | Optional external risk signal (see section 11). |
| `coingecko_api_key` | empty | Only needed if CoinGecko rate-limits you (free "Demo" key). |

**Save** → **Info** tab → **Start**. Enable **Start on boot** and **Watchdog**.

## 5a. Adjusting the allocation from a dashboard (optional)

Instead of editing `allocation_*` in the add-on configuration (which needs a restart), you can control the three percentages with sliders on a Home Assistant dashboard, plus a **Run now** button.

**1. Create the helpers.** Add this to `configuration.yaml` (or to a package), then restart Home Assistant (or Developer tools → YAML → reload *Input numbers* and *Input buttons*):

```yaml
input_number:
  cryptobot_allocation_index:
    name: "Crypto Bot – Top 10 Index"
    min: 0
    max: 100
    step: 1
    unit_of_measurement: "%"
    mode: slider
    icon: mdi:chart-pie
  cryptobot_allocation_top3:
    name: "Crypto Bot – Top 3 Trend"
    min: 0
    max: 100
    step: 1
    unit_of_measurement: "%"
    mode: slider
    icon: mdi:trending-up
  cryptobot_allocation_meme:
    name: "Crypto Bot – Meme Trend"
    min: 0
    max: 100
    step: 1
    unit_of_measurement: "%"
    mode: slider
    icon: mdi:dog

input_button:
  cryptobot_run_now:
    name: "Crypto Bot – Run now"
    icon: mdi:play
```

The entity IDs must be exactly `input_number.cryptobot_allocation_index`, `input_number.cryptobot_allocation_top3`, `input_number.cryptobot_allocation_meme` and `input_button.cryptobot_run_now`. (You can also create them in the UI under Settings → Devices & services → Helpers, as long as the entity IDs match.)

**2. Add a dashboard card** (Edit dashboard → Add card → Manual):

```yaml
type: entities
title: Crypto Bot
entities:
  - input_number.cryptobot_allocation_index
  - input_number.cryptobot_allocation_top3
  - input_number.cryptobot_allocation_meme
  - input_button.cryptobot_run_now
  - type: attribute
    entity: sensor.cryptobot_last_run
    attribute: allocation_pct
    name: Active allocation (%)
  - type: attribute
    entity: sensor.cryptobot_last_run
    attribute: allocation_source
    name: Allocation source
  - sensor.cryptobot_portfolio_eur
  - sensor.cryptobot_last_run
```

**How it works:**
- If **all three** sliders exist and their sum is above 0, they override the `allocation_*` options. Otherwise the add-on configuration is used. The `allocation_source` attribute shows which one is active (`home_assistant` or `addon_config`).
- The values are normalized, so they do not need to add up to exactly 100 (e.g. 50/30/20 and 5/3/2 are the same).
- Changes take effect on the **next run**: the daily run, or immediately when you press **Run now**. A change of more than 0.5 percentage points triggers a full rebalance.
- Set all three sliders first, then press **Run now**. The bot reads the sliders only when it runs, so moving them one at a time is fine, as long as you don't press the button in between.
- **Run now in live mode places real orders.** The `max_turnover_pct` limit still applies.

## 6. Checking the first run

- **Log** tab: you should see the line `Crypto Bot starting – mode: DRY-RUN`, then the selected coins, then a `[DRY-RUN] Reason: first run …` block listing the planned orders.
- **Phone:** you get a "Crypto Bot – simulation" notification.
- **Sensors** (Developer tools → States, search for `cryptobot`):
  - `sensor.cryptobot_portfolio_eur`: value of the managed portfolio
  - `sensor.cryptobot_top3`, `sensor.cryptobot_meme`: number of coins currently held (per-coin state in the attributes)
  - `sensor.cryptobot_last_run`: time of the last run, target values and index weights

  You can add these to a dashboard. After a Home Assistant restart they show "unknown" until the next run; this is normal.
- **Files:** the `share/cryptobot/` folder contains `equity.csv` (portfolio value on every run) and `trades.csv` (simulated or real orders).

## 7. Backtest

1. Configuration: `run_backtest_on_start: true`, `backtest_start: "2022-01-01"` → Save → Restart.
2. After a few minutes you get a notification, and the full report is written to `share/cryptobot/backtest_YYYYMMDD_HHMM.txt`.
3. The report compares the configured strategy, the same portfolio without protection (HODL), BTC buy-and-hold, and a sensitivity table for 20/30/50/100/200-day moving averages.
4. Afterwards set `run_backtest_on_start: false` again.

**Limitation:** the backtest uses *today's* top lists (survivorship bias), because historical top-10 compositions are not freely available. It shows drawdowns and exit behaviour well, but not exact historical returns.

## 8. Dry-run period (recommended: 2–4 weeks)

Your existing setup keeps managing the account in the meantime. Things to watch:

- Do the bot's planned orders make sense? Does it switch in and out of the meme sleeve too often?
- How do its decisions compare with what your current service does (visible in the Bitvavo transaction history)?
- How do they compare with any external signals or reports you follow?

If the meme sleeve is too jumpy, increase `meme_sma_days` (e.g. to 80–100) or `hysteresis_pct` (e.g. to 3–4).

## 9. Going live

1. **Stop any other bot or service** that trades the account, and **delete its API key in Bitvavo**. This matters: two bots must never trade the same account at the same time.
2. **New Bitvavo key:** "View information" + **"Trade digital assets"**, **without** Withdraw, with IP whitelist. Delete the read-only key.
3. Configuration:
   - `api_key`, `api_secret` → the new key
   - `dry_run: false`
   - `max_turnover_pct: 100`, **for the first live run only**, because the switch-over usually means rearranging most positions.
4. Save → Restart. The first live run ("switched to live") sets up the target portfolio. Check the log and your Bitvavo order history.
5. Then set `max_turnover_pct: 60` again → Save → Restart.

**Fees:** Bitvavo's taker fee at low volume is about 0.25% per order. The one-off switch-over therefore costs roughly 0.1–0.25% of the portfolio, and monthly rebalancing typically much less.

## 10. Monitoring IP changes (recommended)

If your home IP address changes, Bitvavo rejects the bot's requests. The bot then does not trade and notifies you. To notice before the next run, add this to `configuration.yaml`:

```yaml
sensor:
  - platform: rest
    name: Public IP
    resource: https://api.ipify.org
    scan_interval: 900
```

Then create an automation (Settings → Automations → Create → ⋮ → Edit in YAML):

```yaml
alias: Public IP changed
triggers:
  - trigger: state
    entity_id: sensor.public_ip
conditions:
  - condition: template
    value_template: >
      {{ trigger.from_state.state not in ['unknown', 'unavailable']
         and trigger.to_state.state not in ['unknown', 'unavailable'] }}
actions:
  - action: notify.mobile_app_<your_phone>
    data:
      title: "Public IP changed"
      message: "New IP: {{ trigger.to_state.state }} – update the Bitvavo API key IP whitelist!"
```

When this fires, edit the key's whitelist on Bitvavo to the new IP. If the key's IP cannot be edited, create a new key and update the add-on configuration.

## 11. External risk signal (optional)

In `signal_url` you can set a URL that returns JSON like this:

```json
{"generated_at": "2026-11-20T06:50:00Z", "top3": "defensive", "meme": "normal"}
```

- In `defensive` mode the trend sleeves exit as soon as the price drops below the SMA, and re-entry requires twice the band.
- If the signal is missing, invalid or older than 36 hours, the bot falls back to `normal` mode.
- The signal can only make the bot more cautious: it never adds new coins or increases position sizes.

## 12. Troubleshooting

| Symptom | Fix |
|---|---|
| Does not appear under Local add-ons | Make sure `config.yaml` sits directly in `addons/cryptobot/`, not in a subfolder. Then ⋮ → Check for updates, or restart the host. |
| Install hangs or fails | Check the Supervisor log: Settings → System → Logs → Supervisor. Often the build is just slow; try again. |
| "Missing API key" | Fill in `api_key` and `api_secret`. |
| "authentication error" notification | IP whitelist (see section 10), or a wrong/deleted key. |
| "createOrder() requires an operatorId" | Set `operator_id` (e.g. 1001). |
| "CoinGecko rate limit" | Get a free Demo API key from CoinGecko and set `coingecko_api_key`. |
| "STOPPED … max_turnover_pct" | For an intentional switch-over raise it temporarily; otherwise investigate why the bot wants to trade so much. |

## 13. Security notes

- API keys are stored by the Supervisor in `/data/options.json`. This is included in Home Assistant backups, so keep your backups encrypted (Home Assistant has encrypted backups by default since 2025).
- As is usual for Home Assistant add-ons, the container runs as root, but without host networking, privileged mode or extra capabilities. It only sees `/data` and `/share`, and reaches the Home Assistant API with the Supervisor token.
- Never give the key Withdraw permission.

## 14. Tax reporting

`equity.csv` records the portfolio value on every run, so you can read off the value on a reference date (e.g. 1 January for the Dutch box 3 wealth tax) and compute yearly results. Check your own situation with a tax advisor.

## Development

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
