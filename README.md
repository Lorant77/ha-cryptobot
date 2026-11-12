# ha-cryptobot

Home Assistant add-on egy egyszerű, szabályalapú kripto-portfólió bothoz [Bitvavo](https://bitvavo.com) tőzsdére.

- **Top 10 Index**: piaci kapitalizáció szerinti súlyozás, felső korláttal, havi újrasúlyozás
- **Top 3 Protect** és **Meme Protect**: trendszűrő (SMA + hiszterézis), esésnél EUR-ba lép ki
- Dry-run mód, forgalmi limit, Home Assistant értesítések és szenzorok, visszateszt

## Telepítés Home Assistantba

A repó privát, ezért a HA Add-on Store nem tudja közvetlenül telepíteni.

1. A `cryptobot/` mappát másold fel a Pi `/addons/cryptobot/` könyvtárába (Samba share vagy SSH add-on).
2. Settings → Add-ons → Add-on Store → ⋮ → **Check for updates** → **Local add-ons** → **Crypto Bot (Bitvavo)** → Install.
3. A részletes beállítás és élesítés leírása: [`cryptobot/README.md`](cryptobot/README.md).

(Ha a repó egyszer publikus lesz, a gyökérben lévő `repository.yaml` miatt az Add-on Store → ⋮ → **Repositories** menüben közvetlenül is hozzáadható.)

## Fejlesztés

```bash
cd cryptobot
pip install -r requirements.txt pytest
python -m pytest -q
```

> **Figyelem:** ez nem pénzügyi tanács. Kriptóval kereskedni kockázatos, és a múltbeli eredmények nem garantálják a jövőbelieket. A kódot csak saját felelősségre használd.
