"""Belépési pont: ütemező ciklus. Naponta egyszer fut a beállított UTC időpontban."""
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
        log.info("Futás kész:\n%s", result)
    except (ccxt.AuthenticationError, ccxt.PermissionDenied) as exc:
        ha.notify("Crypto Bot – hitelesítési hiba",
                  f"A Bitvavo elutasította a kérést: {exc}\n"
                  "Gyakori ok: megváltozott az otthoni IP-cím (IP-whitelist), vagy rossz / lejárt API-kulcs. "
                  "A bot nem kereskedett.")
    except Exception as exc:
        log.exception("Futás hiba")
        ha.notify("Crypto Bot – hiba", f"{type(exc).__name__}: {exc}\nA bot ebben a körben nem kereskedett.")


def main() -> None:
    signal.signal(signal.SIGTERM, _handle_stop)
    cfg = load_config()
    store = Store(DATA_DIR, SHARE_DIR)
    ha = HomeAssistant(cfg.notify_service)
    bot = Bot(cfg, store, ha)
    log.info("Crypto Bot indul – mód: %s, napi futás %s UTC, arányok: %s",
             "DRY-RUN" if cfg.dry_run else "ÉLES", cfg.run_time_utc,
             {k: round(v * 100, 1) for k, v in cfg.allocations.items()})

    if cfg.run_backtest_on_start:
        try:
            report = run_backtest(cfg, bot.ex, SHARE_DIR)
            log.info("Visszateszt:\n%s", report)
            ha.notify("Crypto Bot – visszateszt kész", report[:3000])
        except Exception as exc:
            log.exception("Visszateszt hiba")
            ha.notify("Crypto Bot – visszateszt hiba", str(exc))

    if cfg.run_on_start:
        safe_run(bot, ha)

    while not _stop:
        target = next_run(datetime.now(timezone.utc), cfg.run_time_utc)
        log.info("Következő futás: %s UTC", target.strftime("%Y-%m-%d %H:%M"))
        while not _stop and datetime.now(timezone.utc) < target:
            time.sleep(min(60, max(1, (target - datetime.now(timezone.utc)).total_seconds())))
        if not _stop:
            safe_run(bot, ha)
    log.info("Leállás.")


if __name__ == "__main__":
    main()
