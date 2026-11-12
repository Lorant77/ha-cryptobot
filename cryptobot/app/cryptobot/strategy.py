"""Pure strategy logic (no network access, easy to test).

Three sleeves:
  index – top N coins by market cap, with a per-coin weight cap, rebalanced monthly
  top3  – the 3 largest coins, per-coin trend filter (SMA + hysteresis), otherwise EUR
  meme  – the largest meme coins, same trend filter, otherwise EUR
"""
from __future__ import annotations

from dataclasses import dataclass

# Stablecoins, wrapped / liquid staking tokens: never part of the index.
EXCLUDED_FROM_UNIVERSE = {
    "USDT", "USDC", "DAI", "FDUSD", "USDE", "USDS", "PYUSD", "TUSD", "BUSD", "USDD",
    "USD1", "RLUSD", "FRAX", "GHO", "USDT0", "SUSDE", "SUSDS", "BUIDL", "USDTB", "USDY",
    "EURC", "EUROP", "EURR", "USDR", "EURS", "EURT", "EURCV", "AEUR",
    "WBTC", "WETH", "STETH", "WSTETH", "WEETH", "CBBTC", "CBETH", "RETH", "BTCB",
    "LBTC", "SOLVBTC", "JITOSOL", "MSOL", "BNSOL", "WBETH", "XAUT", "PAXG",
}

QUOTE = "EUR"


def sma(values: list[float], n: int) -> float | None:
    if n <= 0 or len(values) < n:
        return None
    return sum(values[-n:]) / n


def trend_state(close: float, sma_value: float | None, previous: bool | None,
                band_pct: float, defensive: bool = False) -> bool:
    """True = hold the coin, False = wait in EUR.

    Hysteresis: enter if price > SMA*(1+band); exit if price < SMA*(1-band);
    in between, keep the previous state. In defensive mode the exit happens
    as soon as the price is below the SMA, and entry requires twice the band.
    """
    if sma_value is None:
        return False  # not enough data -> stay cautious
    band = band_pct / 100.0
    upper = sma_value * (1 + (2 * band if defensive else band))
    lower = sma_value * (1 - (0 if defensive else band))
    if close > upper:
        return True
    if close < lower:
        return False
    if previous is None:
        return close > sma_value
    if defensive and previous and close < sma_value:
        return False
    return previous


def capped_weights(caps: dict[str, float], max_weight: float) -> dict[str, float]:
    """Market-cap weights with an upper cap; the excess is redistributed proportionally."""
    caps = {k: v for k, v in caps.items() if v and v > 0}
    if not caps:
        return {}
    n = len(caps)
    max_weight = max(max_weight, 1.0 / n)  # otherwise 100% cannot be allocated
    weights: dict[str, float] = {}
    free = dict(caps)
    remaining = 1.0
    while free:
        total = sum(free.values())
        over = {k for k, v in free.items() if v / total * remaining > max_weight + 1e-12}
        if not over:
            for k, v in free.items():
                weights[k] = v / total * remaining
            break
        for k in over:
            weights[k] = max_weight
            remaining -= max_weight
            del free[k]
    return weights


@dataclass
class SleeveInputs:
    index_weights: dict[str, float]   # base -> weight (sums to 1)
    top3: list[str]                   # base-ek
    top3_states: dict[str, bool]
    meme: list[str]
    meme_states: dict[str, bool]


def build_targets(total_eur: float, alloc: dict[str, float], s: SleeveInputs) -> dict[str, float]:
    """Target EUR value per coin. Anything not allocated stays in EUR."""
    targets: dict[str, float] = {}

    def add(base: str, eur: float) -> None:
        if eur > 0:
            targets[base] = targets.get(base, 0.0) + eur

    for base, w in s.index_weights.items():
        add(base, total_eur * alloc["index"] * w)
    if s.top3:
        per = total_eur * alloc["top3"] / len(s.top3)
        for base in s.top3:
            if s.top3_states.get(base):
                add(base, per)
    if s.meme:
        per = total_eur * alloc["meme"] / len(s.meme)
        for base in s.meme:
            if s.meme_states.get(base):
                add(base, per)
    return targets


@dataclass
class PlannedOrder:
    base: str
    side: str          # "sell" | "buy"
    eur: float         # estimated EUR value
    sell_all: bool = False

    def __str__(self) -> str:
        tail = " (teljes)" if self.sell_all else ""
        return f"{self.side.upper():4} {self.base:<6} {self.eur:10.2f} EUR{tail}"


def plan_orders(current: dict[str, float], targets: dict[str, float],
                min_trade_eur: float) -> list[PlannedOrder]:
    """Sells first, then buys. Deviations below min_trade_eur are ignored."""
    sells: list[PlannedOrder] = []
    buys: list[PlannedOrder] = []
    for base in sorted(set(current) | set(targets)):
        cur = current.get(base, 0.0)
        tgt = targets.get(base, 0.0)
        diff = tgt - cur
        if tgt == 0 and cur >= min_trade_eur:
            sells.append(PlannedOrder(base, "sell", cur, sell_all=True))
        elif diff <= -min_trade_eur:
            sells.append(PlannedOrder(base, "sell", -diff))
        elif diff >= min_trade_eur:
            buys.append(PlannedOrder(base, "buy", diff))
    sells.sort(key=lambda o: -o.eur)
    buys.sort(key=lambda o: -o.eur)
    return sells + buys


def turnover_pct(orders: list[PlannedOrder], total_eur: float) -> float:
    if total_eur <= 0:
        return 0.0
    return sum(o.eur for o in orders) / 2 / total_eur * 100


def select_universe(ranked: list[tuple[str, float]], available: set[str], n: int,
                    excluded: set[str]) -> list[tuple[str, float]]:
    """The first n coins of the market-cap ranking that have an EUR pair on Bitvavo."""
    out: list[tuple[str, float]] = []
    seen: set[str] = set()
    for sym, cap in ranked:
        s = sym.upper()
        if s in seen or s in EXCLUDED_FROM_UNIVERSE or s in excluded or s not in available:
            continue
        seen.add(s)
        out.append((s, cap))
        if len(out) >= n:
            break
    return out
