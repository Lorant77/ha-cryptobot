# Crypto Bot (Bitvavo): Home Assistant add-on

Saját kereskedő bot a Diamond Pigs kiváltására. Ugyanazt a háromrészes felállást követi, amit most használsz:

| Rész | Arány | Működés |
|---|---|---|
| **Top 10 Index** | 52% | A 10 legnagyobb coin piaci kapitalizáció szerint (stablecoin és becsomagolt tokenek nélkül, csak ami Bitvavón EUR-párral elérhető). Egy coin súlya legfeljebb 30%. Havonta újrasúlyoz. |
| **Top 3 Protect** | 28% | A 3 legnagyobb coin, egyenlő súllyal. Mindegyiket csak akkor tartja, ha az ára az 50 napos mozgóátlag felett van (±2% hiszterézissel), különben EUR-ban vár. |
| **Meme Protect** | 21% | Az 5 legnagyobb meme coin (CoinGecko „meme-token” kategória), ugyanilyen trendszűrővel. |

**Mikor kereskedik:** naponta egyszer fut (alapból 00:10 UTC-kor, a napi gyertya zárása után). Csak akkor kereskedik, ha (1) új hónap kezdődött, (2) valamelyik Protect-coin trendje megfordult, (3) ez az első futás, vagy (4) most váltottál dry-runról élesre. Ilyenkor a teljes portfóliót a célarányokra állítja.

**Biztonsági korlátok:**
- `dry_run: true` az alapértelmezés, ilyenkor nem ad le megbízást.
- `max_turnover_pct`: ha egy futás a portfólió ennél nagyobb részét forgatná meg, leáll és értesít.
- A `exclude_coins` listában szereplő coinokhoz a bot nem nyúl, és nem is számolja bele őket a portfólióba.
- Hitelesítési hibánál (pl. megváltozott IP) nem kereskedik, és értesít.

> Ez nem pénzügyi tanács. A stratégia a Diamond Pigs nyilvános leírásainak közelítése, nem a zárt algoritmusuk másolata. Kriptóval kereskedni kockázatos.

---

## 1. Előfeltételek

- Home Assistant OS a Raspberry Pi-n (Settings → Add-ons menüvel).
- A Home Assistant Companion app a telefonodon (értesítésekhez). A `notify_service` mezőben kell megadni a telefonod értesítési szolgáltatását.
- Bitvavo-fiók.

## 2. Bitvavo API-kulcs (dry-run időszakra)

A dry-run időszakra **csak olvasási jogú** kulcsot készíts. Így ha bármi elromlik vagy a kulcs kiszivárog, akkor sem tud kereskedni vele senki.

1. Nézd meg az otthoni publikus IP-címedet, pl. a böngészőben: `https://api.ipify.org`
2. Bitvavo → fiók → Settings → **API** → **Create new API key**. Név: `HA Crypto Bot (read-only)`.
3. Jogosultság: **csak „View information”**. A „Trade digital assets” és a „Withdraw digital assets” maradjon kikapcsolva.
4. **IP-whitelist:** add meg az 1. pontban kapott IP-címet.
5. Másold ki az API Key-t és a Secretet, és erősítsd meg az e-mailes jóváhagyást.

A Diamond Pigs kulcsához ne nyúlj, az közben tovább működik.

## 3. A fájlok felmásolása a Pi-re

*(Ha a kód publikus GitHub-repóban van, ez a lépés kiváltható: Add-on Store → ⋮ → **Repositories** → a repó URL-je. Privát repóval ez nem működik.)*

A legegyszerűbb a **Samba share** add-onnal:

1. Settings → Add-ons → **Add-on Store** → keresd: **Samba share** → Install.
2. A Configuration fülön adj meg felhasználónevet és jelszót → Save → Start.
3. Windows Fájlkezelőben: `\\homeassistant.local\addons` (Macen Finder → Go → Connect to Server: `smb://homeassistant.local/addons`).
4. Hozz létre benne egy `cryptobot` mappát, és másold bele a zip **tartalmát**, hogy így nézzen ki:

```
addons/
└── cryptobot/
    ├── config.yaml
    ├── Dockerfile
    ├── requirements.txt
    ├── README.md
    ├── app/cryptobot/*.py
    └── tests/
```

(Samba helyett a „Studio Code Server” vagy az „Advanced SSH & Web Terminal” add-on is jó: ilyenkor a `/addons/cryptobot` mappába kell feltölteni.)

## 4. Az add-on telepítése

1. Settings → Add-ons → **Add-on Store**.
2. Jobb felül a **⋮** menü → **Check for updates** (ez újraolvassa a helyi add-onokat).
3. Lent megjelenik a **Local add-ons** szakasz, benne a **Crypto Bot (Bitvavo)** → **Install**.
   - Az első telepítés a Pi-n **5–15 percig** is eltarthat, mert ilyenkor épül a Docker image (Python és a `ccxt` könyvtár). Ez normális.

## 5. Beállítás (Configuration fül)

A legfontosabb mezők:

| Mező | Érték a kezdéshez | Megjegyzés |
|---|---|---|
| `api_key`, `api_secret` | a 2. lépésben kapott kulcs | |
| `operator_id` | `1001` | A Bitvavo megköveteli a megbízásokhoz. Bármilyen általad választott szám lehet, de maradjon állandó. |
| `dry_run` | **`true`** | Az első hetekben mindenképp maradjon így. |
| `run_on_start` | `true` | Indításkor azonnal lefut egyszer. |
| `run_time_utc` | `00:10` | Télen ez 01:10, nyáron 02:10 holland/magyar idő szerint. |
| `allocation_*` | 52 / 28 / 21 | A bot normalizálja őket, az összegnek nem kell pontosan 100-nak lennie. |
| `exclude_coins` | pl. `["ADA"]` | Ezekhez a coinokhoz nem nyúl. |
| `min_trade_eur` | `10` | Ennél kisebb eltérésre nem kereskedik. |
| `max_turnover_pct` | `60` | Biztonsági fék. |
| `notify_service` | pl. `notify.mobile_app_<telefonod>` | Developer tools → Actions oldalon a „notify.mobile_app” kezdetű listából választhatsz. |
| `signal_url` | üres | Később ide jöhet az AI agent kockázati jele (lásd 11. pont). |
| `coingecko_api_key` | üres | Csak akkor kell, ha a CoinGecko korlátozást ad (ingyenes „Demo” kulcs). |

**Save** → **Info** fül → **Start**. Kapcsold be a **Start on boot** és a **Watchdog** opciót.

## 6. Az első futás ellenőrzése

- **Log** fül: ott kell lennie a `Crypto Bot indul – mód: DRY-RUN` sornak, utána a kiválasztott coinoknak, majd egy `[DRY-RUN] Ok: első futás …` blokknak a tervezett megbízásokkal.
- **Telefon:** jön egy „Crypto Bot – szimuláció” értesítés.
- **Szenzorok** (Developer tools → States, keresés: `cryptobot`):
  - `sensor.cryptobot_portfolio_eur`: a kezelt portfólió értéke
  - `sensor.cryptobot_top3`, `sensor.cryptobot_meme`: hány coin van „tart” állapotban (az attribútumokban coinonként)
  - `sensor.cryptobot_last_run`: az utolsó futás ideje, a célértékek és az index-súlyok

  Ezeket kiteheted a dashboardra. HA-újraindítás után a következő futásig „unknown” értéket mutatnak, ez normális.
- **Fájlok:** a Samba megosztás `share/cryptobot/` mappájában van az `equity.csv` (minden futás portfólióértéke) és a `trades.csv` (a szimulált vagy valódi megbízások).

## 7. Visszateszt

1. Configuration: `run_backtest_on_start: true`, `backtest_start: "2022-01-01"` → Save → Restart.
2. Pár perc múlva értesítést kapsz, a teljes riport pedig itt lesz: `share/cryptobot/backtest_ÉÉÉÉHHNN_ÓÓPP.txt`.
3. A riportban összehasonlítás van: a beállított stratégia, ugyanez védelem nélkül (HODL), BTC vedd-és-tartsd, plusz egy érzékenységi táblázat 20/30/50/100/200 napos mozgóátlaggal.
4. Utána állítsd vissza: `run_backtest_on_start: false`.

**Korlát:** a visszateszt a *mai* toplistát használja (survivorship bias), mert a múltbeli top 10 összetétel ingyen nem érhető el. A drawdown és a kilépések viselkedését jól mutatja, a pontos múltbeli hozamot nem. Összevetésnek futtasd le a Diamond Pigs Play Mode-ját ugyanarra az időszakra.

## 8. Dry-run időszak (javasolt: 2–4 hét)

Közben a Diamond Pigs tovább kezeli a számlát. Amit figyelj:

- Értelmesek-e a bot tervezett megbízásai? Nem akar-e túl gyakran ki-be lépni a meme részben?
- Hogyan viszonyulnak a döntései ahhoz, amit a Diamond Pigs csinál (a Bitvavo tranzakciós előzményeiben látod)?
- Hogyan viszonyulnak a reggeli AI-riport jelzéseihez?

Ha a meme rész túl ideges, emeld a `meme_sma_days` értékét (pl. 80–100-ra) vagy a `hysteresis_pct` értékét (pl. 3–4-re).

## 9. Élesítés

1. **Diamond Pigs leállítása:** a dashboardjukon kapcsold ki a *Portfolio Management*-et, majd a **Bitvavo-ban töröld a Diamond Pigs API-kulcsát**. Ez fontos, nehogy két bot kereskedjen egyszerre ugyanazon a számlán.
2. **Új Bitvavo kulcs:** „View information” + **„Trade digital assets”** jog, Withdraw **nélkül**, IP-whitelisttel. A read-only kulcsot töröld.
3. Configuration:
   - `api_key`, `api_secret` → az új kulcs
   - `dry_run: false`
   - `max_turnover_pct: 100`, **csak az első éles futásra**, mert az átálláskor a Diamond Pigs pozícióit nagyrészt át kell rendezni.
4. Save → Restart. Az első éles futás („átállás élesre”) beállítja a célportfóliót. Ellenőrizd a naplót és a Bitvavo order-előzményeit.
5. Utána állítsd vissza: `max_turnover_pct: 60` → Save → Restart.

**Díjak:** a Bitvavo taker díja kis forgalomnál kb. 0,25% megbízásonként. Az átállás egyszeri költsége így a portfólió kb. 0,1–0,25%-a, utána havonta jellemzően jóval kevesebb.

## 10. IP-változás figyelése (ajánlott)

Ha az otthoni IP-címed megváltozik, a Bitvavo elutasítja a bot kéréseit. A bot ilyenkor nem kereskedik, és értesít. Hogy ezt még a futás előtt észrevedd, add hozzá a `configuration.yaml`-hoz:

```yaml
sensor:
  - platform: rest
    name: Publikus IP
    resource: https://api.ipify.org
    scan_interval: 900
```

Majd hozz létre egy automatizmust (Settings → Automations → Create → ⋮ → Edit in YAML):

```yaml
alias: Publikus IP megváltozott
triggers:
  - trigger: state
    entity_id: sensor.publikus_ip
conditions:
  - condition: template
    value_template: >
      {{ trigger.from_state.state not in ['unknown', 'unavailable']
         and trigger.to_state.state not in ['unknown', 'unavailable'] }}
actions:
  - action: notify.mobile_app_<telefonod>
    data:
      title: "Publikus IP megváltozott"
      message: "Új IP: {{ trigger.to_state.state }} – frissítsd a Bitvavo API-kulcs IP-whitelistjét!"
```

Ilyenkor a Bitvavón szerkeszd a kulcs whitelistjét az új IP-re. Ha a kulcs IP-je nem szerkeszthető, készíts új kulcsot, és írd át az add-on beállításaiban.

## 11. AI agent kockázati jele (később)

A `signal_url` mezőben megadhatsz egy URL-t, ami ilyen JSON-t ad vissza:

```json
{"generated_at": "2026-11-20T06:50:00Z", "top3": "defensive", "meme": "normal"}
```

- `defensive` módban a Protect-részek már az SMA alatt kilépnek, és a visszalépéshez dupla sáv kell.
- Ha a jel hiányzik, hibás vagy 36 óránál régebbi, a bot `normal` módban fut tovább.
- A jel csak szigoríthat: új coint nem vetet, és a pozícióméretet nem növeli.

## 12. Hibaelhárítás

| Tünet | Megoldás |
|---|---|
| Nem jelenik meg a Local add-ons között | Ellenőrizd, hogy a `config.yaml` közvetlenül az `addons/cryptobot/` mappában van-e, nem egy almappában. Utána ⋮ → Check for updates, vagy indítsd újra a Pi-t. |
| A telepítés elakad vagy hibát ad | Supervisor log: Settings → System → Logs → Supervisor. Gyakran csak lassú a build, próbáld újra. |
| „Hiányzó API kulcs” | Töltsd ki az `api_key` és az `api_secret` mezőt. |
| „hitelesítési hiba” értesítés | IP-whitelist (lásd 10. pont), vagy rossz / törölt kulcs. |
| „createOrder() requires an operatorId” | Az `operator_id` legyen kitöltve (pl. 1001). |
| „CoinGecko rate limit” | Kérj ingyenes Demo API-kulcsot a CoinGeckótól, és add meg a `coingecko_api_key` mezőben. |
| „LEÁLLÍTVA … max_turnover_pct” | Szándékos átállásnál emeld meg ideiglenesen, egyébként nézd meg, miért akar ennyit forgatni. |

## 13. Biztonsági megjegyzések

- A kulcsokat a Supervisor tárolja a `/data/options.json`-ban. Ez a HA-mentésekbe is bekerül, ezért a mentéseidet titkosítsd (a HA 2025 óta alapból titkosítja őket).
- A konténer a HA add-onoknál szokásos módon rootként fut, de nincs host-hálózata, privilegizált módja vagy plusz jogosultsága. Csak a `/data` és a `/share` könyvtárat látja, és a HA API-t a Supervisor tokenjével.
- Withdraw jogot soha ne adj a kulcsnak.

## 14. Adózás (Hollandia, box 3)

Az `equity.csv` minden futás portfólióértékét tartalmazza, ebből kiolvasható a január 1-jei érték. A tervezett 2028-as „werkelijk rendement” rendszerhez az éves eredményt is meg lehet belőle határozni. Ezt ellenőriztesd adótanácsadóval.

## Fejlesztőknek

```bash
pip install -r requirements.txt pytest
python -m pytest -q
```
