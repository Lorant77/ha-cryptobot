"""Beállítások betöltése a Home Assistant add-on options.json fájlból."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields

OPTIONS_PATH = os.environ.get("CRYPTOBOT_OPTIONS", "/data/options.json")
DATA_DIR = os.environ.get("CRYPTOBOT_DATA", "/data")
SHARE_DIR = os.environ.get("CRYPTOBOT_SHARE", "/share/cryptobot")


@dataclass
class Config:
    api_key: str = ""
    api_secret: str = ""
    operator_id: int = 1001
    dry_run: bool = True
    run_on_start: bool = True
    run_time_utc: str = "00:10"
    allocation_index: int = 52
    allocation_top3: int = 28
    allocation_meme: int = 21
    index_size: int = 10
    index_max_weight_pct: int = 30
    top3_sma_days: int = 50
    meme_sma_days: int = 50
    meme_count: int = 5
    hysteresis_pct: float = 2.0
    exclude_coins: list[str] = field(default_factory=list)
    min_trade_eur: float = 10.0
    max_turnover_pct: int = 60
    notify_service: str = ""
    signal_url: str = ""
    coingecko_api_key: str = ""
    run_backtest_on_start: bool = False
    backtest_start: str = "2022-01-01"

    @property
    def allocations(self) -> dict[str, float]:
        """Normalizált arányok (pl. 52+28+21=101 kerekítés miatt)."""
        raw = {
            "index": float(self.allocation_index),
            "top3": float(self.allocation_top3),
            "meme": float(self.allocation_meme),
        }
        total = sum(raw.values())
        if total <= 0:
            raise ValueError("Az allocation_* értékek összege nem lehet 0")
        return {k: v / total for k, v in raw.items()}

    @property
    def excluded(self) -> set[str]:
        return {c.strip().upper() for c in self.exclude_coins if c.strip()}


def load_config(path: str = OPTIONS_PATH) -> Config:
    data: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    known = {f.name for f in fields(Config)}
    return Config(**{k: v for k, v in data.items() if k in known and v is not None})
