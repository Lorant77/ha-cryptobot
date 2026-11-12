"""Entry point: scheduler loop. Runs once a day at the configured UTC time."""
from __future__ import annotations

import logging
import signal
import sys
import time
from datetime import datetime, timedelta, timezone

import ccxt

from .backtest import run_backtest
from .bot import Bot
from .config import DATA_DIR, SHARE_DIR, load_config
from .ha import HomeAssistant
from .store import Store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                    stream=sys.stdout)
log = logging.getLogger("cryptobot")
_stop = False
RUN_NOW_ENTITY = "input_button.cryptobot_run_now"


def _handle_stop(*_):
    global _stop
    _stop = True


def next_run(now: datetime, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    candidate = now.replace(hour=h, minute=m, second=0, microsecond=0)
    return candidate if candidate > now else candidate + timedelta(days=1)


def safe_run(bot: Bot, ha: HomeAssistant) -> None:
    try:
        result = bot.run_once()
        log.info("Run finished:\n%s", result)
    except (ccxt.AuthenticationError, ccxt.PermissionDenied) as exc:
        ha.notify("Crypto Bot – authentication error",
                  f"Bitvavo rejected the request: {exc}\n"
                  "Common cause: your home IP address changed (IP whitelist), or the API key is wrong/expired. "
                  "The bot did not trade.")
    except Exception as exc:
        log.exception("Run failed")
        ha.notify("Crypto Bot – error", f"{type(exc).__name__}: {exc}\nThe bot did not trade in this run.")


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    cfg = load_config()
    store = Store(DATA_DIR, SHARE_DIR)
    ha = HomeAssistant(cfg.notify_service)
    bot = Bot(cfg, store, ha)
    log.info("Crypto Bot starting – mode: %s, daily run at %s UTC, allocation: %s",
             "DRY-RUN" if cfg.dry_run else "LIVE", cfg.run_time_utc,
             {k: round(v * 100, 1) for k, v in cfg.allocations.items()})

    if cfg.run_backtest_on_start:
        try:
            report = run_backtest(cfg, bot.ex, SHARE_DIR)
            log.info("Backtest:\n%s", report)
            ha.notify("Crypto Bot – backtest finished", report[:3000])
        except Exception as exc:
            log.exception("Backtest failed")
            ha.notify("Crypto Bot – backtest error", str(exc))

    if cfg.run_on_start:
        safe_run(bot, ha)

    last_press = ha.state(RUN_NOW_ENTITY)
    while not _stop:
        target = next_run(datetime.now(timezone.utc), cfg.run_time_utc)
        log.info("Next run: %s UTC", target.strftime("%Y-%m-%d %H:%M"))
        while not _stop and datetime.now(timezone.utc) < target:
            time.sleep(min(60, max(1, (target - datetime.now(timezone.utc)).total_seconds())))
            press = ha.state(RUN_NOW_ENTITY)
            if press and press != last_press:
                last_press = press
                log.info("Manual run (Run now button)")
                safe_run(bot, ha)
        if not _stop and datetime.now(timezone.utc) >= target:
            safe_run(bot, ha)
    log.info("Shutting down.")


if __name__ == "__main__":
    main()
