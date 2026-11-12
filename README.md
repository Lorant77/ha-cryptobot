# ha-cryptobot

A Home Assistant add-on for a simple, rule-based crypto portfolio bot on the [Bitvavo](https://bitvavo.com) exchange.

- **Top 10 Index**: market-cap weighted with a per-coin cap, rebalanced monthly
- **Top 3 Trend** and **Meme Trend**: trend filter (SMA + hysteresis) that moves to EUR in downtrends
- Allocation sliders and a Run now button on your Home Assistant dashboard
- Dry-run mode, turnover limit, Home Assistant notifications and sensors, backtest

## Installing in Home Assistant

1. Settings → Add-ons → Add-on Store → ⋮ → **Repositories** → add `https://github.com/Lorant77/ha-cryptobot` → Add.
2. The **Crypto Bot (Bitvavo)** add-on appears → Install.
3. For detailed configuration and going live, see [`cryptobot/README.md`](cryptobot/README.md).

Updates: bump `version` in `cryptobot/config.yaml` and push; Home Assistant will offer the update.

## Development

```bash
cd cryptobot
pip install -r requirements.txt pytest
python -m pytest -q
```

> **Disclaimer:** this is not financial advice. Trading crypto assets is risky and past performance does not guarantee future results. Use this code at your own risk.
