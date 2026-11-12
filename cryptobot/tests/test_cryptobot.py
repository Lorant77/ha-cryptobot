import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "app"))

from cryptobot import market_data as md  # noqa: E402
from cryptobot.backtest import simulate  # noqa: E402
from cryptobot.bot import Bot  # noqa: E402
from cryptobot.config import Config  # noqa: E402
from cryptobot.store import Store  # noqa: E402
from cryptobot.strategy import (SleeveInputs, build_targets, capped_weights, plan_orders,  # noqa: E402
                                select_universe, sma, trend_state)


# ---------------------------------------------------------------- strategy
def test_capped_weights_sum_and_cap():
    w = capped_weights({"BTC": 1000, "ETH": 300, "XRP": 100, "SOL": 80, "BNB": 70}, 0.30)
    assert math.isclose(sum(w.values()), 1.0)
    assert w["BTC"] == pytest.approx(0.30)
    assert all(v <= 0.30 + 1e-9 for v in w.values())
    assert w["ETH"] > w["XRP"] > w["SOL"] > w["BNB"]


def test_capped_weights_cap_too_low_falls_back_to_equal():
    w = capped_weights({"A": 10, "B": 1}, 0.1)
    assert w == pytest.approx({"A": 0.5, "B": 0.5})


def test_trend_hysteresis():
    assert trend_state(105, 100, None, 2) is True
    assert trend_state(97, 100, None, 2) is False
    assert trend_state(101, 100, False, 2) is False   # sávon belül marad az előző
    assert trend_state(99, 100, True, 2) is True
    assert trend_state(99, 100, True, 2, defensive=True) is False
    assert trend_state(103, 100, False, 2, defensive=True) is False  # belépéshez 4% kell
    assert trend_state(50, None, True, 2) is False


def test_sma():
    assert sma([1, 2, 3, 4], 2) == 3.5
    assert sma([1], 2) is None


def test_select_universe_skips_stables_and_unavailable():
    ranked = [("BTC", 9), ("USDT", 8), ("ETH", 7), ("FOO", 6), ("XRP", 5), ("btc", 4)]
    out = select_universe(ranked, {"BTC", "ETH", "XRP", "USDT"}, 3, set())
    assert [s for s, _ in out] == ["BTC", "ETH", "XRP"]
    out = select_universe(ranked, {"BTC", "ETH", "XRP"}, 3, {"ETH"})
    assert [s for s, _ in out] == ["BTC", "XRP"]


def test_build_targets_protect_off_goes_to_eur():
    alloc = {"index": 0.5, "top3": 0.3, "meme": 0.2}
    s = SleeveInputs({"BTC": 0.6, "ETH": 0.4}, ["BTC", "ETH", "XRP"],
                     {"BTC": True, "ETH": False, "XRP": True}, ["DOGE", "PEPE"],
                     {"DOGE": False, "PEPE": False})
    t = build_targets(1000, alloc, s)
    assert t["BTC"] == pytest.approx(300 + 100)
    assert t["ETH"] == pytest.approx(200)
    assert t["XRP"] == pytest.approx(100)
    assert "DOGE" not in t
    assert sum(t.values()) == pytest.approx(700)  # ETH-rész (100) + meme (200) EUR-ban marad


def test_plan_orders_sells_first_and_thresholds():
    orders = plan_orders({"BTC": 500, "OLD": 50, "ETH": 100, "DUST": 3},
                         {"BTC": 400, "ETH": 300, "SOL": 8}, 10)
    sides = [(o.side, o.base) for o in orders]
    assert sides == [("sell", "BTC"), ("sell", "OLD"), ("buy", "ETH")]
    assert orders[1].sell_all


# ---------------------------------------------------------------- bot (fake exchange)
class FakeExchange:
    def __init__(self, prices, balances):
        self.prices = prices
        self.balances = balances
        self.orders = []
        self.markets = {f"{b}/EUR": {"limits": {"cost": {"min": 5}}} for b in prices}

    def load_markets(self):
        return {f"{b}/EUR": {"base": b, "quote": "EUR", "active": True, "spot": True} for b in self.prices}

    def fetch_balance(self):
        return {"total": dict(self.balances), "free": dict(self.balances)}

    def fetch_tickers(self, symbols):
        return {s: {"last": self.prices[s.split("/")[0]]} for s in symbols}

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.8f}"

    def create_order(self, symbol, type_, side, amount, price=None, params=None):
        self.orders.append((symbol, side, amount, (params or {}).get("cost")))
        return {"id": str(len(self.orders)), "status": "closed"}


class FakeHA:
    def __init__(self):
        self.notes, self.sensors = [], {}

    def notify(self, title, msg):
        self.notes.append((title, msg))

    def sensor(self, name, state, attrs=None):
        self.sensors[name] = state


@pytest.fixture
def env(tmp_path, monkeypatch):
    prices = {"BTC": 80000.0, "ETH": 3000.0, "XRP": 2.0, "DOGE": 0.2, "PEPE": 0.00001, "ADA": 0.5}
    ranked = [("BTC", 1e12), ("ETH", 4e11), ("XRP", 1e11), ("ADA", 3e10), ("DOGE", 2e10)]
    memes = [("DOGE", 2e10), ("PEPE", 4e9)]
    monkeypatch.setattr(md, "ranked_coins",
                        lambda key="", category=None, per_page=100: memes if category else ranked)
    trend = {"BTC": 1.2, "ETH": 0.8, "XRP": 1.2, "DOGE": 1.2, "PEPE": 0.8}  # ár / SMA

    def closes(ex, base, days, since_ms=None):
        p = prices[base]
        hist = [p / trend[base]] * 60
        hist[-1] = p
        return list(enumerate(hist))
    monkeypatch.setattr(md, "daily_closes", closes)
    monkeypatch.setattr(md, "fetch_risk_signal", lambda url: {"top3": "normal", "meme": "normal"})
    store = Store(str(tmp_path / "data"), str(tmp_path / "share"))
    return prices, store


def make_bot(env, dry_run, balances):
    prices, store = env
    cfg = Config(api_key="k", api_secret="s", dry_run=dry_run, index_size=4, meme_count=2,
                 max_turnover_pct=100)
    ex = FakeExchange(prices, balances)
    ha = FakeHA()
    return Bot(cfg, store, ha, exchange=ex), ex, ha


def test_dry_run_places_no_orders(env):
    bot, ex, ha = make_bot(env, True, {"EUR": 6000.0})
    out = bot.run_once()
    assert ex.orders == []
    assert "DRY-RUN" in out and "első futás" in out
    assert ha.sensors["portfolio_eur"] == 6000.0
    # második futás ugyanazon a napon: nincs teendő
    assert bot.run_once().startswith("Nincs teendő")


def test_live_run_buys_targets_and_respects_trend(env):
    bot, ex, ha = make_bot(env, False, {"EUR": 6000.0})
    bot.run_once()
    bought = {s.split("/")[0]: cost for s, side, _, cost in ex.orders if side == "buy"}
    assert "PEPE" not in bought            # meme trend lefelé -> EUR
    assert "BTC" in bought and "DOGE" in bought
    assert sum(bought.values()) <= 6000 * 0.995 + 1e-6


def test_turnover_limit_blocks(env):
    bot, ex, ha = make_bot(env, False, {"EUR": 6000.0})
    bot.cfg.max_turnover_pct = 10
    out = bot.run_once()
    assert "LEÁLLÍTVA" in out and ex.orders == []


def test_switch_from_dry_to_live_forces_rebalance(env):
    bot, ex, ha = make_bot(env, True, {"EUR": 6000.0})
    bot.run_once()
    bot.cfg.dry_run = False
    out = bot.run_once()
    assert "átállás élesre" in out
    assert ex.orders


def test_excluded_coin_is_untouched(env):
    bot, ex, ha = make_bot(env, False, {"EUR": 1000.0, "ADA": 1000.0})
    bot.cfg.exclude_coins = ["ADA"]
    bot.run_once()
    assert not any(s.startswith("ADA") for s, *_ in ex.orders)


# ---------------------------------------------------------------- backtest
def test_simulate_protect_reduces_drawdown_in_crash():
    days = list(range(0, 400 * 86_400_000, 86_400_000))
    up = [100 * (1.01 ** i) for i in range(200)]
    down = [up[-1] * (0.985 ** i) for i in range(1, 201)]
    series = {d: p for d, p in zip(days, up + down)}
    closes = {"BTC": series}
    alloc = {"index": 0.0, "top3": 1.0, "meme": 0.0}
    eq_p, _, _ = simulate(closes, days, alloc, {}, ["BTC"], [], 50, 50, 2)
    eq_h, _, _ = simulate(closes, days, alloc, {}, ["BTC"], [], 50, 50, 2, protect=False)
    assert eq_p[-1] > eq_h[-1]
