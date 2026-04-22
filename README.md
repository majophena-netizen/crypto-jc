# Crypto Trader — BTC/USDT

Une application **de détection et de trading automatisé** BTC/USDT qui combine
indicateurs techniques classiques (RSI, MACD, Moyennes Mobiles, Bollinger) et
**confirmation par IA Claude** (Anthropic). Trois modes :

1. **Signals** — détection pure, aucun ordre exécuté.
2. **Paper** — portefeuille virtuel (10 000 USDT par défaut), simulation de trades.
3. **Live** — ordres réels sur Binance (testnet par défaut, **mainnet sur
   activation explicite**).

> ⚠️ **Avertissement** — Aucun bot de trading ne garantit un profit. Ce projet
> est un outil éducatif et un point de départ. Commencez en `signals` ou
> `paper`, puis en `live` sur **Binance Testnet**. N'activez le mainnet que
> quand vous comprenez la stratégie et en acceptez les pertes possibles.

## Stack

- **Backend** : Python 3.11+, FastAPI, SQLAlchemy async (SQLite), `ccxt`
  (Binance + fallback Kraken/Coinbase pour les données publiques), Claude 4.5
  pour la confirmation IA.
- **Frontend** : Next.js 16 (App Router, React 19), Tailwind v4, Recharts,
  design moderne minimaliste (sombre/clair auto via `prefers-color-scheme`).
- **Persistance** : SQLite (`trader.db`) — signaux, trades, PnL.
- **Scheduler** : boucle d'analyse toutes les `SCAN_INTERVAL_SECONDS` secondes.

## Démarrage rapide

### 1. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env         # renseignez vos clés (voir plus bas)
uvicorn app.main:app --reload --port 8000
```

L'API est sur [http://localhost:8000](http://localhost:8000), avec les docs
OpenAPI sur [http://localhost:8000/docs](http://localhost:8000/docs).

### 2. Frontend

```bash
cd frontend
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE=http://localhost:8000
pnpm install
pnpm dev                     # http://localhost:3000
```

## Variables d'environnement (backend)

Toutes les clés vivent dans `backend/.env` (jamais commité — voir `.gitignore`).
Voir `backend/.env.example` pour la liste complète.

| Variable | Rôle |
| --- | --- |
| `BINANCE_API_KEY` / `BINANCE_API_SECRET` | clés Binance (testnet **ou** mainnet). |
| `BINANCE_TESTNET` | `true` par défaut. Passez à `false` **uniquement** pour trader avec du vrai argent. |
| `MARKET_DATA_EXCHANGE` | source des données publiques : `binance` (défaut), `kraken`, `coinbase`. Utile si Binance est géo-bloqué. |
| `ANTHROPIC_API_KEY` | clé Claude. Sans elle, la décision se base uniquement sur les indicateurs. |
| `ANTHROPIC_MODEL` | modèle Claude (`claude-sonnet-4-5` par défaut). |
| `DEFAULT_MODE` | mode de démarrage : `signals` \| `paper` \| `live`. |
| `PAPER_STARTING_USDT` | capital virtuel de départ. |
| `LIVE_MAX_ORDER_USDT` | plafond dur par ordre en mode live. |
| `SCAN_INTERVAL_SECONDS` | fréquence de la boucle d'analyse. |
| `RSI_*`, `MACD_*`, `MA_*` | paramètres stratégie. |

### Obtenir des clés Binance Testnet

1. Allez sur [https://testnet.binance.vision/](https://testnet.binance.vision/).
2. Connectez-vous avec GitHub.
3. Cliquez **Generate HMAC_SHA256 Key** → copiez la clé et le secret dans
   `.env` et laissez `BINANCE_TESTNET=true`.

### Obtenir une clé Claude

[https://console.anthropic.com/](https://console.anthropic.com/) → API Keys.

## Stratégie

Pour chaque scan :

1. `fetch_ohlcv` récupère N bougies 15m (configurable).
2. Les indicateurs RSI(14), MACD(12,26,9), MA(20)/MA(50), Bollinger(20,2)
   sont calculés.
3. Chaque indicateur vote `+1` / `0` / `-1`. La moyenne donne un score
   dans `[-1, 1]` → action technique `buy` / `hold` / `sell`.
4. Claude reçoit le snapshot et renvoie sa propre action + confidence + rationale.
5. **Décision finale** :
   - ambiance : si technique et IA sont d'accord → on agit ;
   - désaccord → `hold` ;
   - l'un des deux est `hold` alors que l'autre est fort (|score| ≥ 0.75
     ou confidence IA ≥ 0.7) → on suit le fort.
6. Le signal est enregistré en DB. En mode `paper` ou `live`, un ordre est
   passé automatiquement.

## Architecture

```
backend/
  app/
    main.py            FastAPI app + lifespan (init DB, démarre le scanner)
    config.py          Settings Pydantic chargées depuis .env
    db.py              SQLAlchemy async (SQLite) — tables Signal / Trade
    exchange.py        Wrapper ccxt (Binance + fallback public)
    indicators.py      Calcul RSI/MACD/MA/Bollinger + votes
    ai.py              Intégration Claude (confirmation IA)
    signals.py         Pipeline complet indicateurs → IA → décision → DB
    paper.py           Portefeuille virtuel (avg-cost, PnL réalisé)
    live.py            Exécution Binance (testnet ou mainnet)
    scheduler.py       Boucle de scan périodique
    state.py           État runtime partagé (mode courant, dernière exécution)
    routers/
      market.py        /api/market/{ticker, candles, indicators}
      signals.py       /api/signals (POST scan, GET historique)
      trades.py        /api/trades, /portfolio, /pnl/daily, /execute, /paper/reset
      control.py       /api/control/{status, mode}
frontend/
  src/
    app/               layout + page principale (dashboard temps réel)
    components/        cartes, charts Recharts, switcher de mode, badges
    lib/               client API typé + helpers de formatage
```

## Endpoints

- `GET  /api/health`
- `GET  /api/control/status`
- `POST /api/control/mode` — corps `{ "mode": "signals" | "paper" | "live" }`
- `GET  /api/market/ticker`
- `GET  /api/market/candles?limit=200`
- `GET  /api/market/indicators`
- `POST /api/signals/scan`
- `GET  /api/signals?limit=50`
- `GET  /api/trades?limit=100&mode=paper|live`
- `POST /api/trades/execute` — corps `{ "side": "buy"|"sell", "quote_amount": 100, "mode": "paper"|"live" }`
- `GET  /api/trades/portfolio`
- `GET  /api/trades/pnl/daily?days=14`
- `POST /api/trades/paper/reset`

## Sécurité

- Les clés API ne sortent **jamais** du backend — le frontend ne reçoit que
  des soldes et des ordres résumés.
- `.env` est listé dans `.gitignore` ; seul `.env.example` est committé.
- Le mode `live` refuse de s'activer sans clés Binance présentes.
- Un plafond dur `LIVE_MAX_ORDER_USDT` limite chaque ordre. Par défaut 50 USDT.
- **Binance testnet par défaut** (`BINANCE_TESTNET=true`). Passage en mainnet
  = action consciente dans `.env`.

## Limites connues / pistes d'amélioration

- La stratégie est volontairement simple (4 votes + confirmation IA). Un
  backtest rigoureux est **recommandé avant tout passage en mainnet**.
- Pas de gestion du risque (stop-loss, trailing stop) — à ajouter si vous
  passez en live sérieux.
- SQLite est parfait pour un usage perso ; pour du multi-user/HA, passez à
  Postgres (changez juste `DATABASE_URL`).
- Le trading réel ne calcule pas le PnL réalisé côté backend — fiez-vous
  aux relevés Binance.

## Licence

MIT.
