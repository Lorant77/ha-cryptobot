"""Egyszerű visszateszt Bitvavo napi záróárakon.

Fontos korlát: a coin-univerzum a MAI toplista (survivorship bias) – a múltbeli
top 10 / meme összetétel nem ingyenesen elérhető. Az eredmény tehát a stratégia
viselkedését mutatja (kilépések, drawdown), nem pontos múltbeli hozamot.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from . import market_data as md
from .config import Config
from .strategy import SleeveInputs, build_targets, capped_weights, select_universe, sma, trend_state

log = logging.getLogger(__name__)
FEE = 0.0025  # Bitvavo taker díj kis forgalomnál (ellenőrizd a saját díjszinted)
DAY_MS = 86_400_000


@dataclass
class Result:
    name: str
    total_return: float
    cagr: float
    max_dd: float
    rebalances: int
    fees: float

    def line(self) -> str:
        return (f"{self.name:<34} hozam {self.total_return:8.1f}%  CAGR {self.cagr:6.1f}%  "
                f"max DD {self.max_dd:6.1f}%  újrasúly. {self.rebalances:4d}  díj {self.fees:8.2f} EUR")


def _metrics(name: str, equity: list[float], days: int, rebalances: int, fees: float) -> Result:
    start, end = equity[0], equity[-1]
    years = max(days / 365.0, 1e-9)
    peak, max_dd = equity[0], 0.0
    for v in equity:
        peak = max(peak, v)
        max_dd = min(max_dd, v / peak - 1)
    return Result(name, (end / start - 1) * 100, ((end / start) ** (1 / years) - 1) * 100,
                  max_dd * 100, rebalances, fees)


def simulate(closes: dict[str, dict[int, float]], days: list[int], alloc: dict[str, float],
             index_weights: dict[str, float], top3: list[str], meme: list[str],
             top3_sma: int, meme_sma: int, band: float, capital: float = 10_000.0,
             protect: bool = True) -> tuple[list[float], int, float]:
    units: dict[str, float] = {}
    eur = capital
    states: dict[str, bool] = {}
    hist: dict[str, list[float]] = {b: [] for b in closes}
    last_px: dict[str, float] = {}
    equity, rebalances, fees, month = [], 0, 0.0, None
    warmup = max(top3_sma, meme_sma)

    for i, d in enumerate(days):
        for b, series in closes.items():
            if d in series:
                last_px[b] = series[d]
                hist[b].append(series[d])
        value = eur + sum(u * last_px.get(b, 0) for b, u in units.items())
        if i < warmup:
            equity.append(value)
            continue

        new_states = {}
        for lst, n in ((top3, top3_sma), (meme, meme_sma)):
            for b in lst:
                if not protect:
                    new_states[b] = b in last_px
                elif b in last_px:
                    new_states[b] = trend_state(last_px[b], sma(hist[b], n), states.get(b), band)
                else:
                    new_states[b] = False
        cur_month = datetime.fromtimestamp(d / 1000, tz=timezone.utc).strftime("%Y-%m")
        trigger = cur_month != month or new_states != states
        states, month = new_states, cur_month
        if trigger:
            avail_w = {b: w for b, w in index_weights.items() if b in last_px}
            s = sum(avail_w.values())
            avail_w = {b: w / s for b, w in avail_w.items()} if s else {}
            targets = build_targets(value, alloc, SleeveInputs(avail_w, top3, states, meme, states))
            traded = sum(abs(targets.get(b, 0) - units.get(b, 0) * last_px.get(b, 0))
                         for b in set(targets) | set(units))
            fee = traded * FEE
            fees += fee
            value -= fee
            units = {b: v / last_px[b] for b, v in targets.items() if last_px.get(b)}
            eur = value - sum(targets.values())
            rebalances += 1
        equity.append(eur + sum(u * last_px.get(b, 0) for b, u in units.items()))
    return equity, rebalances, fees


def run_backtest(cfg: Config, exchange, out_dir: str) -> str:
    available = md.eur_bases(exchange)
    idx = select_universe(md.ranked_coins(cfg.coingecko_api_key), available, cfg.index_size, cfg.excluded)
    memes = select_universe(md.ranked_coins(cfg.coingecko_api_key, category="meme-token", per_page=50),
                            available, cfg.meme_count, cfg.excluded)
    weights = capped_weights(dict(idx), cfg.index_max_weight_pct / 100.0)
    top3 = [s for s, _ in idx[:3]]
    meme = [s for s, _ in memes]

    since = int(datetime.fromisoformat(cfg.backtest_start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    since -= (max(cfg.top3_sma_days, cfg.meme_sma_days, 200) + 5) * DAY_MS
    closes = {}
    for b in sorted(set(weights) | set(top3) | set(meme)):
        try:
            closes[b] = dict(md.daily_closes(exchange, b, 0, since_ms=since))
        except Exception as exc:
            log.warning("Nincs adat: %s (%s)", b, exc)
    days = sorted(closes.get("BTC", {}).keys())
    if not days:
        raise RuntimeError("Nem sikerült BTC adatot letölteni")
    n_days = len(days)
    alloc = cfg.allocations

    lines = [f"Visszateszt {datetime.fromtimestamp(days[0]/1000, tz=timezone.utc):%Y-%m-%d} – "
             f"{datetime.fromtimestamp(days[-1]/1000, tz=timezone.utc):%Y-%m-%d} (bemelegítéssel), díj {FEE*100:.2f}%",
             f"Index: { {k: round(v, 3) for k, v in weights.items()} }",
             f"Top3: {top3}  Meme: {meme}",
             "FIGYELEM: a coinlista a mai toplista (survivorship bias).", ""]

    eq, rb, fe = simulate(closes, days, alloc, weights, top3, meme, cfg.top3_sma_days,
                          cfg.meme_sma_days, cfg.hysteresis_pct)
    lines.append(_metrics(f"Beállított (SMA {cfg.top3_sma_days}/{cfg.meme_sma_days})", eq, n_days, rb, fe).line())
    eq, rb, fe = simulate(closes, days, alloc, weights, top3, meme, cfg.top3_sma_days,
                          cfg.meme_sma_days, cfg.hysteresis_pct, protect=False)
    lines.append(_metrics("Ugyanez védelem nélkül (HODL)", eq, n_days, rb, fe).line())
    btc = [closes["BTC"][d] for d in days]
    lines.append(_metrics("BTC vedd és tartsd", btc, n_days, 0, 0).line())
    lines.append("")
    lines.append("Érzékenység (SMA napok mindkét Protect részre):")
    for n in (20, 30, 50, 100, 200):
        eq, rb, fe = simulate(closes, days, alloc, weights, top3, meme, n, n, cfg.hysteresis_pct)
        lines.append(_metrics(f"  SMA {n}", eq, n_days, rb, fe).line())

    report = "\n".join(lines)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"backtest_{datetime.now(timezone.utc):%Y%m%d_%H%M}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(report + "\n")
    return report
