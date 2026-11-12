"""Egy futás: adatok -> jelek -> célportfólió -> megbízások (vagy dry-run napló)."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import ccxt

from . import market_data as md
from .config import Config
from .ha import HomeAssistant
from .store import Store
from .strategy import (SleeveInputs, build_targets, capped_weights, plan_orders,
                       select_universe, sma, trend_state, turnover_pct)

log = logging.getLogger(__name__)
DUST_EUR = 1.0
ALLOC_ENTITIES = {
    "index": "input_number.cryptobot_allocation_index",
    "top3": "input_number.cryptobot_allocation_top3",
    "meme": "input_number.cryptobot_allocation_meme",
}


def make_exchange(cfg: Config) -> ccxt.bitvavo:
    return ccxt.bitvavo({
        "apiKey": cfg.api_key or None,
        "secret": cfg.api_secret or None,
        "enableRateLimit": True,
        "options": {"operatorId": int(cfg.operator_id)},
    })


class Bot:
    def __init__(self, cfg: Config, store: Store, ha: HomeAssistant, exchange=None):
        self.cfg = cfg
        self.store = store
        self.ha = ha
        self.ex = exchange or make_exchange(cfg)

    # ------------------------------------------------------------------ univerzum
    def refresh_universe(self, available: set[str]) -> dict:
        ranked = md.ranked_coins(self.cfg.coingecko_api_key, per_page=100)
        idx = select_universe(ranked, available, self.cfg.index_size, self.cfg.excluded)
        memes_ranked = md.ranked_coins(self.cfg.coingecko_api_key, category="meme-token", per_page=50)
        memes = select_universe(memes_ranked, available, self.cfg.meme_count, self.cfg.excluded)
        weights = capped_weights(dict(idx), self.cfg.index_max_weight_pct / 100.0)
        uni = {
            "month": datetime.now(timezone.utc).strftime("%Y-%m"),
            "index_weights": weights,
            "top3": [s for s, _ in idx[:3]],
            "meme": [s for s, _ in memes],
        }
        log.info("Új univerzum: index=%s top3=%s meme=%s",
                 {k: round(v, 3) for k, v in weights.items()}, uni["top3"], uni["meme"])
        return uni

    # ------------------------------------------------------------------ arányok
    def effective_allocations(self) -> tuple[dict[str, float], str]:
        """A HA csúszkák (input_number) értékei, ha mindhárom létezik; különben az add-on beállítás."""
        values = {k: self.ha.number(e) for k, e in ALLOC_ENTITIES.items()}
        if all(v is not None and v >= 0 for v in values.values()) and sum(values.values()) > 0:
            total = sum(values.values())
            return {k: v / total for k, v in values.items()}, "home_assistant"
        return self.cfg.allocations, "addon_config"

    # ------------------------------------------------------------------ trend
    def trend_states(self, bases: list[str], sma_days: int, mode: str, prev: dict) -> tuple[dict, dict]:
        states, info = {}, {}
        for base in bases:
            closes = [c for _, c in md.daily_closes(self.ex, base, sma_days + 5)]
            s = sma(closes, sma_days)
            close = closes[-1] if closes else 0.0
            states[base] = trend_state(close, s, prev.get(base), self.cfg.hysteresis_pct,
                                       defensive=(mode == "defensive"))
            info[base] = {"close": close, "sma": s, "hold": states[base]}
        return states, info

    # ------------------------------------------------------------------ fő futás
    def run_once(self) -> str:
        cfg = self.cfg
        if not cfg.api_key or not cfg.api_secret:
            raise RuntimeError("Hiányzó API kulcs. Dry-runhoz elég egy csak 'View information' jogú kulcs.")

        now = datetime.now(timezone.utc)
        month = now.strftime("%Y-%m")
        mode_label = "dry" if cfg.dry_run else "live"

        available = md.eur_bases(self.ex)
        uni = self.store.get("universe")
        new_month = not uni or uni.get("month") != month
        if new_month:
            uni = self.refresh_universe(available)

        signal = md.fetch_risk_signal(cfg.signal_url)
        prev_states = self.store.get("states", {})
        top3_states, top3_info = self.trend_states(uni["top3"], cfg.top3_sma_days, signal["top3"], prev_states)
        meme_states, meme_info = self.trend_states(uni["meme"], cfg.meme_sma_days, signal["meme"], prev_states)
        new_states = {**top3_states, **meme_states}
        changed = sorted(b for b, v in new_states.items() if prev_states.get(b) != v and b in prev_states)

        # --- jelenlegi portfólió (csak a kezelt eszközök) ---
        balance = self.ex.fetch_balance()
        totals = {k: float(v) for k, v in (balance.get("total") or {}).items() if v}
        free = {k: float(v) for k, v in (balance.get("free") or {}).items() if v}
        wanted = set(uni["index_weights"]) | set(uni["top3"]) | set(uni["meme"])
        held = {b for b in totals if b != "EUR" and b in available and b not in cfg.excluded}
        symbols = [f"{b}/EUR" for b in sorted(held | wanted)]
        tickers = self.ex.fetch_tickers(symbols) if symbols else {}
        prices = {s.split("/")[0]: float(t.get("last") or t.get("close") or 0) for s, t in tickers.items()}

        current = {b: totals.get(b, 0.0) * prices.get(b, 0.0) for b in held}
        current = {b: v for b, v in current.items() if v >= DUST_EUR}
        eur = totals.get("EUR", 0.0)
        total = eur + sum(current.values())

        alloc, alloc_source = self.effective_allocations()
        prev_alloc = self.store.get("last_alloc")
        alloc_changed = bool(prev_alloc) and any(abs(alloc[k] - prev_alloc.get(k, 0)) > 0.005 for k in alloc)

        last_mode = self.store.get("last_mode")
        first_run = self.store.get("last_rebalance") is None
        switched_live = last_mode == "dry" and mode_label == "live"
        reasons = []
        if first_run:
            reasons.append("első futás")
        if new_month:
            reasons.append(f"havi újrasúlyozás ({month})")
        if changed:
            reasons.append("trendváltás: " + ", ".join(f"{b}->{'tart' if new_states[b] else 'EUR'}" for b in changed))
        if switched_live:
            reasons.append("átállás élesre")
        if alloc_changed:
            reasons.append("arányváltozás: " + "/".join(f"{alloc[k]*100:.0f}" for k in ("index", "top3", "meme")))

        inputs = SleeveInputs(uni["index_weights"], uni["top3"], top3_states, uni["meme"], meme_states)
        targets = build_targets(total, alloc, inputs)
        self._publish_sensors(total, signal, top3_info, meme_info, targets, uni, alloc, alloc_source)

        if not reasons:
            self.store.set("states", new_states)
            self.store.set("last_mode", mode_label)
            self.store.set("universe", uni)
            self.store.record_run(cfg.dry_run, total, False, "nincs teendő")
            return f"Nincs teendő. Portfólió: {total:,.2f} EUR"

        orders = plan_orders(current, targets, cfg.min_trade_eur)
        turnover = turnover_pct(orders, total)
        header = (f"{'[DRY-RUN] ' if cfg.dry_run else ''}Ok: {'; '.join(reasons)}\n"
                  f"Portfólió: {total:,.2f} EUR, forgalom: {turnover:.1f}%")

        if turnover > cfg.max_turnover_pct:
            msg = (f"{header}\nLEÁLLÍTVA: a tervezett forgalom ({turnover:.1f}%) nagyobb, mint a "
                   f"max_turnover_pct ({cfg.max_turnover_pct}%). Ha ez szándékos (pl. átállás), "
                   f"emeld meg ideiglenesen.\n" + "\n".join(map(str, orders)))
            self.ha.notify("Crypto Bot – leállítva", msg)
            self.store.record_run(cfg.dry_run, total, False, "turnover limit")
            return msg

        results = self._execute(orders, prices, free) if orders else []
        self.store.set("states", new_states)
        self.store.set("universe", uni)
        self.store.set("last_mode", mode_label)
        self.store.set("last_rebalance", now.isoformat(timespec="seconds"))
        self.store.set("last_alloc", alloc)
        self.store.record_run(cfg.dry_run, total, True, "; ".join(reasons))

        body = header + "\n" + ("\n".join(results) if results else "Nincs küszöb feletti eltérés.")
        self.ha.notify("Crypto Bot – " + ("szimuláció" if cfg.dry_run else "kereskedés"), body)
        return body

    # ------------------------------------------------------------------ végrehajtás
    def _min_cost(self, base: str) -> float:
        m = self.ex.markets.get(f"{base}/EUR", {}) if self.ex.markets else {}
        mc = ((m.get("limits") or {}).get("cost") or {}).get("min")
        return max(float(mc or 0), self.cfg.min_trade_eur)

    def _execute(self, orders, prices, free) -> list[str]:
        out = []
        dry = self.cfg.dry_run
        for o in [x for x in orders if x.side == "sell"]:
            price = prices.get(o.base, 0)
            if price <= 0:
                out.append(f"KIHAGYVA {o.base}: nincs ár")
                continue
            amount = free.get(o.base, 0.0) if o.sell_all else min(free.get(o.base, 0.0), o.eur / price)
            if amount * price < self._min_cost(o.base):
                out.append(f"KIHAGYVA {o} (minimum alatt)")
                continue
            out.append(self._place(o, amount=amount, dry=dry))

        buys = [x for x in orders if x.side == "buy"]
        if buys:
            eur_free = free.get("EUR", 0.0) if dry else float((self.ex.fetch_balance().get("free") or {}).get("EUR", 0))
            if dry:  # szimulációban az eladások bevételét is számoljuk
                eur_free += sum(o.eur for o in orders if o.side == "sell")
            need = sum(o.eur for o in buys)
            scale = min(1.0, eur_free * 0.995 / need) if need > 0 else 0
            for o in buys:
                cost = o.eur * scale
                if cost < self._min_cost(o.base):
                    out.append(f"KIHAGYVA {o} (minimum alatt / kevés EUR)")
                    continue
                o.eur = cost
                out.append(self._place(o, cost=cost, dry=dry))
        return out

    def _place(self, o, amount: float | None = None, cost: float | None = None, dry: bool = True) -> str:
        symbol = f"{o.base}/EUR"
        if dry:
            self.store.record_trade(True, o.base, o.side, o.eur, amount, "", "dry-run")
            return f"(szim.) {o}"
        try:
            if o.side == "sell":
                amt = float(self.ex.amount_to_precision(symbol, amount))
                res = self.ex.create_order(symbol, "market", "sell", amt)
            else:
                res = self.ex.create_order(symbol, "market", "buy", None, None, {"cost": cost})
            oid = str(res.get("id", ""))
            self.store.record_trade(False, o.base, o.side, o.eur, amount, oid, str(res.get("status", "")))
            return f"OK {o}"
        except Exception as exc:
            self.store.record_trade(False, o.base, o.side, o.eur, amount, "", f"hiba: {exc}")
            log.exception("Megbízás hiba: %s", o)
            return f"HIBA {o}: {exc}"

    # ------------------------------------------------------------------ HA szenzorok
    def _publish_sensors(self, total, signal, top3_info, meme_info, targets, uni, alloc, alloc_source) -> None:
        def fmt(info):
            return {b: ("tart" if v["hold"] else "EUR") for b, v in info.items()}
        self.ha.sensor("portfolio_eur", round(total, 2),
                       {"unit_of_measurement": "EUR", "device_class": "monetary", "state_class": "total"})
        self.ha.sensor("top3", sum(v["hold"] for v in top3_info.values()),
                       {"coins": fmt(top3_info), "risk_mode": signal["top3"]})
        self.ha.sensor("meme", sum(v["hold"] for v in meme_info.values()),
                       {"coins": fmt(meme_info), "risk_mode": signal["meme"]})
        self.ha.sensor("last_run", datetime.now(timezone.utc).isoformat(timespec="seconds"),
                       {"device_class": "timestamp", "dry_run": self.cfg.dry_run,
                        "targets_eur": {k: round(v, 2) for k, v in sorted(targets.items())},
                        "index_weights": {k: round(v, 4) for k, v in uni["index_weights"].items()},
                        "allocation_pct": {k: round(v * 100, 1) for k, v in alloc.items()},
                        "allocation_source": alloc_source})
