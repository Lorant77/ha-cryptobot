"""External data: CoinGecko rankings, Bitvavo daily candles, optional risk signal."""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

CG_URL = "https://api.coingecko.com/api/v3/coins/markets"
DAY_MS = 86_400_000


def _cg_get(params: dict, api_key: str = "") -> list[dict]:
    headers = {"accept": "application/json"}
    if api_key:
        headers["x-cg-demo-api-key"] = api_key
    for attempt in range(3):
        r = requests.get(CG_URL, params=params, headers=headers, timeout=30)
        if r.status_code == 429:
            time.sleep(20 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("CoinGecko rate limit – try again later, or set coingecko_api_key")


def ranked_coins(api_key: str = "", category: str | None = None, per_page: int = 100) -> list[tuple[str, float]]:
    """List of (SYMBOL, market_cap_eur), sorted by market cap descending."""
    params = {"vs_currency": "eur", "order": "market_cap_desc", "per_page": per_page, "page": 1}
    if category:
        params["category"] = category
    rows = _cg_get(params, api_key)
    return [(row["symbol"].upper(), float(row.get("market_cap") or 0)) for row in rows]


def eur_bases(exchange) -> set[str]:
    """Coins actively tradable on Bitvavo with an EUR pair."""
    markets = exchange.load_markets()
    return {m["base"] for m in markets.values()
            if m.get("quote") == "EUR" and m.get("active", True) and m.get("spot", True)}


def daily_closes(exchange, base: str, days: int, since_ms: int | None = None) -> list[tuple[int, float]]:
    """Closing prices of closed daily candles (timestamp_ms, close). Drops today's still-open candle."""
    symbol = f"{base}/EUR"
    if since_ms is None:
        since_ms = int(time.time() * 1000) - (days + 3) * DAY_MS
    out: list[tuple[int, float]] = []
    cursor = since_ms
    now_ms = int(time.time() * 1000)
    while True:
        batch = exchange.fetch_ohlcv(symbol, "1d", since=cursor, limit=1000)
        if not batch:
            break
        for ts, _o, _h, _l, c, _v in batch:
            if not out or ts > out[-1][0]:
                out.append((int(ts), float(c)))
        nxt = batch[-1][0] + DAY_MS
        if nxt >= now_ms or len(batch) < 2 or nxt <= cursor:
            break
        cursor = nxt
    today_start = now_ms - now_ms % DAY_MS
    return [(ts, c) for ts, c in out if ts < today_start]


def fetch_risk_signal(url: str, max_age_hours: float = 36) -> dict[str, str]:
    """Optional external signal (e.g. from an AI agent). Falls back to 'normal' if invalid or stale."""
    default = {"top3": "normal", "meme": "normal"}
    if not url:
        return default
    try:
        r = requests.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        ts = datetime.fromisoformat(str(data["generated_at"]).replace("Z", "+00:00"))
        age_h = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
        if age_h > max_age_hours:
            log.warning("Risk signal is too old (%.1f hours) – using 'normal' mode", age_h)
            return default
        out = {}
        for k in ("top3", "meme"):
            v = str(data.get(k, "normal")).lower()
            out[k] = v if v in ("normal", "defensive") else "normal"
        return out
    except Exception as exc:  # the signal must never stop the bot
        log.warning("Could not read risk signal (%s) – using 'normal' mode", exc)
        return default
