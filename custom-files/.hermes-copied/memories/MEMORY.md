# Niggvis — Crypto Trading Knowledge Base

## Environment

- Agent: Niggvis (Hermes Agent instance)
- Owner: Damian
- Blockchain: Solana
- Execution: Trojan on Solana (Telegram bot)
- Models: Mistral Large (primary), NVIDIA NIM Llama 3.3 70B (backup)
- Platform: WSL → VPS (Contabo) docelowo
- Language: polski (crypto terms po angielsku)

---

## Trading Rules (HARD LIMITS — nie naruszaj)

### Position sizing
- Max trade size: 0.1 SOL per trade (na start — $5-10)
- Max open positions: 5 tokenów jednocześnie
- Max portfolio allocation per token: 25%
- Min remaining SOL balance: 0.05 SOL (na gas fees)

### Risk management
- Stop-loss: -30% od entry (domyślny, chyba że analiza mówi inaczej)
- Take-profit: minimum 2x entry (częściowy sell 50%, reszta trailing)
- Daily loss limit: -20% portfolio → STOP TRADING na resztę dnia
- Weekly loss limit: -40% portfolio → STOP TRADING + raport + czekaj na Damiana

### Execution rules
- ZAWSZE sprawdź kontrakt przed kupnem (checklist poniżej)
- NIGDY nie kupuj tokena bez liquidity > $5K
- NIGDY nie kupuj tokena ze 100% unlocked LP
- NIGDY nie kupuj tokena z aktywnym mint authority (chyba że trusted project)
- NIGDY nie wchodź w token który jest już +500% w ciągu godziny (za późno)
- Przy paper trading: loguj trade'y ale NIE wysyłaj komend do Trojana

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
 
# Szukaj token po adresie
GET /latest/dex/tokens/{tokenAddress}
 
# Szukaj po nazwie/symbolu
GET /latest/dex/search?q={query}
 
# Top boosty (trending/promoted)
GET /token-boosts/top/v1
 
# Nowe pary na Solanie
GET /latest/dex/pairs/solana
```

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

### Solana RPC (on-chain data — w Solana skill)
```
Default: https://api.mainnet-beta.solana.com
Override: SOLANA_RPC_URL env variable
 
Skill: ~/.hermes/skills/solana/scripts/solana_client.py
Commands: wallet, tx, token, activity, nft, whales, stats, price
```

---

## Trojan on Solana — Integration

### Bot info
- Bot: @solaboratorybot (Trojan on Solana) na Telegramie
- Wallet: osobny wallet z ograniczonym budżetem
- Komendy: przez Telegram (Hermes wysyła wiadomości do Trojana)

### Komendy buy/sell
```
/buy <TOKEN_ADDRESS> <AMOUNT_SOL>      # Kup token
/sell <TOKEN_ADDRESS> <PERCENTAGE>      # Sprzedaj % pozycji
/sell <TOKEN_ADDRESS> 100               # Sprzedaj 100% (close position)
```

### Komendy status
```
/positions                              # Otwarte pozycje
/wallet                                 # Saldo
/pnl                                    # Profit & Loss
/settings                               # Ustawienia
```

### Ustawienia Trojana (zalecane)
- Auto-buy: OFF (Niggvis decyduje, nie Trojan)
- Slippage: 15-20% (memecoiny mają wysoki slippage)
- Priority fee: medium (balans cost vs speed)
- MEV protection: ON (ochrona przed sandwich attacks)

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
