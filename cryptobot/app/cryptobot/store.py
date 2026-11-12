"""Állapot (SQLite a /data-ban, benne van a HA mentésekben) + CSV export a /share-be."""
from __future__ import annotations

import csv
import json
import os
import sqlite3
from datetime import datetime, timezone


class Store:
    def __init__(self, data_dir: str, share_dir: str):
        os.makedirs(data_dir, exist_ok=True)
        self.share_dir = share_dir
        self.db = sqlite3.connect(os.path.join(data_dir, "cryptobot.db"))
        self.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS runs (
                ts TEXT, dry_run INTEGER, total_eur REAL, rebalanced INTEGER, note TEXT);
            CREATE TABLE IF NOT EXISTS trades (
                ts TEXT, dry_run INTEGER, base TEXT, side TEXT, eur REAL,
                amount REAL, order_id TEXT, status TEXT);
            """
        )
        self.db.commit()

    # --- kulcs-érték ---
    def get(self, key: str, default=None):
        row = self.db.execute("SELECT v FROM kv WHERE k=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def set(self, key: str, value) -> None:
        self.db.execute("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", (key, json.dumps(value)))
        self.db.commit()

    # --- napló ---
    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def record_run(self, dry_run: bool, total_eur: float, rebalanced: bool, note: str) -> None:
        ts = self._now()
        self.db.execute("INSERT INTO runs VALUES (?,?,?,?,?)", (ts, int(dry_run), total_eur, int(rebalanced), note))
        self.db.commit()
        self._append_csv("equity.csv", ["ts_utc", "dry_run", "total_eur", "rebalanced", "note"],
                         [ts, int(dry_run), f"{total_eur:.2f}", int(rebalanced), note])

    def record_trade(self, dry_run: bool, base: str, side: str, eur: float,
                     amount: float | None, order_id: str, status: str) -> None:
        ts = self._now()
        self.db.execute("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?)",
                        (ts, int(dry_run), base, side, eur, amount, order_id, status))
        self.db.commit()
        self._append_csv("trades.csv", ["ts_utc", "dry_run", "base", "side", "eur", "amount", "order_id", "status"],
                         [ts, int(dry_run), base, side, f"{eur:.2f}", "" if amount is None else amount, order_id, status])

    def _append_csv(self, name: str, header: list[str], row: list) -> None:
        try:
            os.makedirs(self.share_dir, exist_ok=True)
            path = os.path.join(self.share_dir, name)
            new = not os.path.exists(path)
            with open(path, "a", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(header)
                w.writerow(row)
        except OSError:
            pass  # a CSV csak kényelmi export; az SQLite a forrás
