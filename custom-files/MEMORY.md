# Niggvis — Crypto Trading Knowledge Base

## CRITICAL — File Locations & Tool Commands

### Where everything lives
- Config: `~/.hermes/memories/trading-config.yaml`
- Trade journal: `~/.hermes/memories/trade-journal.json`
- Trade learnings: `~/.hermes/memories/trade-learnings.json`
- Wallet keypair: `~/.hermes/secrets/trading-wallet.json`
- Guardian log: `~/.hermes/cron/guardian.log`
- Skills directory: `~/.hermes/skills/`
- Python with solders: configured as `python_bin` in trading-config.yaml
  (currently `~/projects/hermes-agent-niggvis-crypto/.venv/bin/python3`)

### Important: Python venv
Scripts that need `solders` (jupiter_swap.py) auto-detect the venv python
from `python_bin` in trading-config.yaml. executor.py and guardian.py also
read this setting when calling jupiter_swap as subprocess. You do NOT need
to specify the python path manually — just use `python3 ~/.hermes/skills/...`
and the scripts handle it internally.

### How to run tools (ALWAYS use full paths)
```bash
# Trade Executor — buy, sell, check exits, portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <address> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <N> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <N> --pct 50 --reason "partial TP"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py check-exits
python3 ~/.hermes/skills/trade-executor/scripts/executor.py portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose --key <key> --value <val> --reason "why"

# Jupiter Swap — direct on-chain (low-level)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py balance --token <address>
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <address>
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <address> --amount-sol 0.05
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py sell --token <address>

# Crypto Scanner — trending, new pairs
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 10
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py new-pairs --limit 10
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py token <address>
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py metas

# On-chain Analyzer — safety score
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py safety <address>
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py holders <address>

# Trade Journal — show, stats, export
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show --status open
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats --days 7
python3 ~/.hermes/skills/trade-journal/scripts/journal.py close --id <N> --reason "why"

# Risk Manager — check, status, kill switch
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py check --token <address> --amount 0.05
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py status
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py kill --reason "why"

# Learning — self-improvement
python3 ~/.hermes/skills/trade-journal/scripts/learning.py update
python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns

# Guardian — price monitor (usually runs separately, but can check)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --dry-run
```

### Trading pipeline (follow this order)
1. `scanner.py trending` → find candidates (liquidity > $10K)
2. `executor.py buy --token <addr> --reason "..."` → does EVERYTHING internally:
   - Runs `analyzer.py analyze` (full 0-100 safety score, NOT `safety` which is only 45/45 max)
   - Runs `risk_manager.py check` (position limits, daily P&L, duplicate check)
   - Calculates position size from config
   - Executes Jupiter swap if approved
   - Logs trade to journal
3. `guardian.py` monitors prices every 10-120s (adaptive) → auto SL/TP
4. `executor.py sell --id <N> --reason "..."` → manual sell when needed

**IMPORTANT: Do NOT run `analyzer.py safety` manually — it returns max 45/45 (contract-only)
which will always get BLOCKED by risk-manager (min_safety_score: 60). Use `executor.py buy`
which runs the full `analyze` command internally (0-100 score).**

---

## Environment

- Agent: Niggvis (Hermes Agent instance)
- Owner: Damian
- Blockchain: Solana
- Execution: Jupiter V2 Meta-Aggregator (on-chain swaps)
- Models: NVIDIA NIM (primary), Mistral Large (fallback)
- Platform: WSL → VPS (Contabo) docelowo
- Language: polski (crypto terms po angielsku)
- Config: ~/.hermes/memories/trading-config.yaml

---

## Trading Rules (from trading-config.yaml)

All hard limits are now in `~/.hermes/memories/trading-config.yaml`.
Agent reads config dynamically — no need to duplicate here.

Key principles:
- Position size is auto-calculated: % of available wallet balance
- Stop-loss and take-profit are enforced by Guardian (adaptive 10-120s interval)
- Kill switch stops all trading instantly
- Config changes require Damian's approval via Telegram
- NIGDY nie edytuj trading-config.yaml bezpośrednio — zawsze config-propose
- NIGDY nie edytuj skryptów Python w ~/.hermes/skills/ — agent nie może modyfikować własnego kodu

### Execution rules
- ZAWSZE sprawdź kontrakt przed kupnem (checklist poniżej)
- NIGDY nie kupuj tokena bez liquidity > $5K
- NIGDY nie kupuj tokena ze 100% unlocked LP
- NIGDY nie kupuj tokena z aktywnym mint authority (chyba że trusted project)
- NIGDY nie wchodź w token który jest już +500% w ciągu godziny (za późno)
- W paper mode: loguj trade'y ale NIE wykonuj on-chain
- W real mode: Jupiter wykonuje swap, transakcja nieodwracalna

---

## Token Analysis Checklist

Przed KAŻDYM buy sprawdź te punkty (w tej kolejności):

### 1. Contract Security (deal-breakers)
- [ ] Mint authority: REVOKED (jeśli active → NIE KUP)
- [ ] Freeze authority: REVOKED (jeśli active → NIE KUP)
- [ ] LP status: burned lub locked >30 dni (jeśli unlocked → NIE KUP)
- [ ] Nie jest honeypot (sprawdź czy można sprzedać)

### 2. Liquidity & Trading
- [ ] Liquidity: > $5K (ideally >$20K)
- [ ] Volume 24h: > $10K
- [ ] Buy/sell ratio: nie jest ekstremalnie jednokierunkowy (>90% buy = FOMO red flag)
- [ ] Spread: < 5%

### 3. Holder Distribution
- [ ] Top holder: < 15% supply (wyłączając LP pool i DEX contracts)
- [ ] Liczba holders: > 100 (im więcej, tym lepiej)
- [ ] Brak concentrated holdings wśród top 10 walletów (whale dump risk)
- [ ] Smart money presence: znane wallety kupują? (bullish signal)

### 4. Social & Project
- [ ] Twitter/X: aktywne konto (nie stworzone dziś)
- [ ] Telegram: aktywna grupa (nie boty)
- [ ] Website: istnieje i nie jest template
- [ ] Wiek tokena: > 30 minut (unikaj ultra-fresh tokenów bez historii)

### 5. Market Context
- [ ] SOL price trend: w jakim trendzie jest SOL (bear market = wyższe ryzyko dla memecoins)
- [ ] Narrative fit: czy token wpasowuje się w aktualny trend/narrację
- [ ] Konkurencja: czy istnieją podobne tokeny które już wyrosły

---

## Memecoin Lifecycle (typowe fazy)

```
Phase 1: LAUNCH (0-30 min)
├── Deployer tworzy token + LP pool
├── Sniper bots wchodzą w sekundy
├── RYZYKO: najwyższe (rug pull, honeypot)
├── STRATEGIA: unikaj chyba że masz pewny sygnał z smart money
└── Max allocation: 0.02 SOL
 
Phase 2: DISCOVERY (30 min - 4h)
├── Token pojawia się na DEXScreener trending
├── Pierwsi "real" buyerzy (nie boty)
├── Volume rośnie organicznie
├── STRATEGIA: tu szukamy entry — po weryfikacji kontraktu
└── Max allocation: 0.05-0.1 SOL
 
Phase 3: VIRAL (4h - 24h)
├── Twitter/TG viral, KOL mentions
├── Volume peak, nowi holders napływają
├── Price 5-50x od launch
├── STRATEGIA: jeśli mamy pozycję — częściowy sell (50%)
├── NOWE wejście: ryzykowne, ale trend following może działać z tight SL
└── Max allocation: 0.05 SOL (z -20% SL)
 
Phase 4: PEAK & DISTRIBUTION (24h - 72h)
├── Insiders/early buyers zaczynają sell
├── Volume spada, price konsolidacja lub spadek
├── "Buy the dip" crowd wchodzi (later losers)
├── STRATEGIA: SELL resztę pozycji jeśli jeszcze mamy
└── NIE kupuj w tej fazie
 
Phase 5: AFTERMATH (72h+)
├── 90% tokenów → -80% od peak i dalej spadają
├── 10% tokenów → stabilizacja, community, utility
├── STRATEGIA: obserwuj survivorów, potencjalny re-entry jeśli fundamentals
└── Tylko swing trade z clear setup
```

---

## Smart Money Tracking

### Metoda
1. Zidentyfikuj wallety które konsekwentnie kupują wcześnie i sprzedają z zyskiem
2. Monitoruj ich aktywność (Birdeye wallet tracker, Solscan)
3. Gdy smart money wallet kupuje nowy token → to sygnał do analizy (nie automatyczny buy!)
4. Weryfikuj token przez pełny checklist zanim podejmiesz decyzję

### Znane smart money walletty
(Agent będzie tu dodawał wallety w miarę jak je zidentyfikuje)
- TODO: uzupełnij po pierwszym tygodniu skanowania

---

## Rugpull Red Flags (INSTANT NO-BUY)

| Red Flag | Powód | Sprawdzenie |
|----------|-------|-------------|
| Mint authority active | Dev może dodrukować tokeny i zdumpować | Solana skill: token info |
| Freeze authority active | Dev może zamrozić Twój wallet | Solana skill: token info |
| LP not locked/burned | Dev może wycofać LP = 0 liquidity | DEXScreener lub rugcheck |
| Top holder > 20% | Jeden sprzedaje = price crash | Solana skill: token info |
| No socials | Brak zespołu = brak odpowiedzialności | Ręczna weryfikacja |
| Copied contract | Fork znanego scam tokena | Porównaj bytecode |
| Age < 5 min + volume > $100K | Bot-driven pump, human dump | DEXScreener |
| Can buy, can't sell | Honeypot | Test transaction lub rugcheck.xyz |
| Dev wallet selling | Insider dumping | On-chain tracking |

---

## Data Sources & API Reference

### DEXScreener (primary — nowe tokeny, trending)
```
Base: https://api.dexscreener.com
 
# Token data po adresie (300 rpm)
GET /tokens/v1/solana/{tokenAddress}
 
# Para po adresie (300 rpm)
GET /token-pairs/v1/solana/{tokenAddress}
 
# Szukaj po nazwie/symbolu (300 rpm)
GET /latest/dex/search?q={query}
 
# Nowe token profiles (60 rpm)
GET /token-profiles/latest/v1
 
# Top boosty — trending (60 rpm)
GET /token-boosts/top/v1
 
# Trending meta categories (60 rpm)
GET /metas/trending/v1
```

> **Uwaga**: Zawsze dodawaj header `User-Agent` — bez niego Python urllib dostaje 403.

### Jupiter (execution — on-chain swaps)
```
Base: https://api.jup.ag/swap/v2
 
# Get quote + assembled transaction
GET /order?inputMint={mint}&outputMint={mint}&amount={raw}&taker={pubkey}
 
# Execute signed transaction
POST /execute {signedTransaction, requestId}
```

SOL mint: So11111111111111111111111111111111111111112
SOL decimals: 9 (1 SOL = 1,000,000,000 lamports)

### Birdeye (analytics, OHLCV, trending)
```
Base: https://public-api.birdeye.so
Headers: X-API-KEY: public (lub własny klucz)
 
# Trending tokeny
GET /defi/tokenlist?sort_by=v24hUSD&sort_type=desc&chain=solana
 
# Token overview
GET /defi/token_overview?address={addr}&chain=solana
 
# Price history (OHLCV)
GET /defi/ohlcv?address={addr}&type=15m&time_from={ts}&time_to={ts}&chain=solana
 
# Trades
GET /defi/txs/token?address={addr}&tx_type=swap&chain=solana
```

### CoinGecko (market cap, global trending)
```
Base: https://api.coingecko.com/api/v3
 
# Trending
GET /search/trending
 
# Cena tokena (po CoinGecko ID)
GET /simple/price?ids={id}&vs_currencies=usd
 
# Solana ecosystem
GET /coins/markets?vs_currency=usd&category=solana-ecosystem&order=volume_desc
```

### pump.fun (nowe memecoiny na Solanie)
```
Base: https://frontend-api.pump.fun
 
# Nowe tokeny
GET /coins?sort=created_timestamp&order=DESC&limit=50
 
# Token details
GET /coins/{mint_address}
 
# Trades
GET /trades/latest?mint={mint_address}
```

### Solana RPC (on-chain data)
```
Default: https://api.mainnet-beta.solana.com
Override: SOLANA_RPC_URL env variable or trading-config.yaml wallet.rpc_url
```

---

## Execution — Jupiter Integration

### Architecture
```
Hermes Agent → executor.py → jupiter_swap.py → Jupiter V2 API → Solana blockchain
                                                      ↑
                                         All routers compete (Metis, JupiterZ, Dflow, OKX)
```

### Wallet
- Dedykowany wallet TYLKO do tradingu (nie główny wallet Damiana)
- Keypair: ~/.hermes/secrets/trading-wallet.json
- Slippage: 15% (konfigurowalny w trading-config.yaml)
- Guardian sprawdza ceny co 2 min i auto-wykonuje SL/TP

### Mode switch
- paper: symulacja (journal + quotes, zero on-chain)
- real: Jupiter wykonuje swap, transakcja nieodwracalna
- Przełączanie: `executor.py mode paper` / `executor.py mode real`

---

## Trade Journal Format

Każdy trade loguj w tym formacie:

```
## Trade #[N] — [data] [czas]
 
Token: [nazwa] ([ticker])
Address: [mint address]
Direction: BUY / SELL
Amount: [X SOL]
Price at entry: [price]
Reason: [dlaczego wszedłem — konkretne sygnały]
 
### Analysis at entry
- Liquidity: [amount]
- Holders: [count]
- Volume 1h: [vol]
- Social signal: [co widziałem]
- Smart money: [tak/nie]
- Contract check: [PASS/FAIL — detale]
 
### Result (po zamknięciu)
- Exit price: [price]
- P&L: [+/- %] ([+/- SOL])
- Hold time: [duration]
- Reason for exit: [TP hit / SL hit / manual / rugpull]
 
### Lessons learned
- Co zadziałało: [X]
- Co nie zadziałało: [Y]
- Na przyszłość: [Z]
```

---

## Cron Schedule (docelowy — po paper trading)

| Częstotliwość | Job | Opis |
|---------------|-----|------|
| Co 15 min | Token scanner | DEXScreener new pairs, volume spikes, trending |
| Co godzinę | Position check | Otwarte pozycje vs. SL/TP levels |
| Co 4h | Trend analysis | X/Twitter, pump.fun, social sentiment |
| 08:00 daily | Morning report | Portfolio, PnL, plan na dzień → Telegram |
| 23:00 daily | Evening recap | Podsumowanie dnia, trade journal update → Telegram |
| Niedziela 10:00 | Weekly analysis | Win rate, patterns, strategy tuning → Telegram |

---

## Learning Framework

### Po każdym trade
1. Zapisz w trade journal (format powyżej)
2. Zaktualizuj MEMORY.md jeśli nauczyłeś się czegoś nowego
3. Jeśli pattern się powtarza — utwórz/ulepsz skill

### Po każdym dniu
1. Przejrzyj wszystkie trade'y z dnia
2. Oblicz: win rate, avg PnL, best/worst
3. Zidentyfikuj wzorce: jakie sygnały działały, jakie nie
4. Zaktualizuj filtry w skanerze jeśli trzeba

### Po każdym tygodniu
1. Pełna analiza performance
2. Porównanie z poprzednimi tygodniami (poprawa?)
3. Rewizja strategii: co zmienić, co zostawić
4. Aktualizacja smart money wallet list
5. Raport do Damiana na Telegram

### Kluczowe metryki do śledzenia
- Win rate (target: >50%)
- Average P&L per trade
- Risk-adjusted return (Sharpe-like)
- Max drawdown
- Best performing strategy/signal type
- Time to decision (szybkość reakcji)

---

## Known Patterns (agent uzupełnia w miarę nauki)

### Bullish Signals
- Smart money wallet kupuje fresh token → analizuj dalej
- Volume spike >300% w 1h + rosnąca liczba holders → momentum play
- KOL (Key Opinion Leader) mention na X + organic community growth
- Token survives first dump i odbudowuje → strong community
- Narrative fit (AI, gaming, meme trend) + timing

### Bearish Signals / Exit triggers
- Dev wallet starts selling → SELL natychmiast
- LP unlock approaching → SELL przed unlock
- Volume drops >50% przy stable/falling price → distribution phase
- Whale (top holder) selling large chunks → cascade risk
- Negative social sentiment shift → herd will follow

### Neutral / Wait
- New token <30 min old → zbyt wcześnie, czekaj na discovery phase
- High volume but flat price → accumulation OR distribution — potrzeba więcej danych
- Mixed signals (bullish on-chain, bearish social) → skip lub micro position

---
