# Hermes Agent Niggvis Crypto — Codzienny Cheatsheet

## Szybki start

```bash
cd ~/projects/hermes-agent-niggvis-crypto
hermes                         # Start rozmowy
```

Hermes pamięta sesję — po wyjściu możesz wrócić:
```bash
hermes --continue              # Wznów ostatnią sesję
hermes -c                      # Skrócona forma
```

Restart gateway przez sudo:
```bash
sudo systemctl restart hermes-gateway
```

Uruchomienie guardiana:
```bash
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --history 5 --interval 60
```

---

## Kluczowe komendy CLI

| Komenda | Co robi |
|---------|---------|
| `hermes` | Start interaktywnej rozmowy |
| `hermes model` | Wybór providera i modelu (interaktywny) |
| `hermes tools` | Konfiguracja narzędzi per platforma |
| `hermes setup` | Pełny wizard konfiguracji |
| `hermes config` | Podgląd konfiguracji |
| `hermes config edit` | Otwórz config.yaml w edytorze |
| `hermes config set KEY VAL` | Ustaw wartość |
| `hermes doctor` | Diagnostyka instalacji |
| `hermes status` | Status konfiguracji |
| `hermes update` | Aktualizacja do najnowszej wersji |
| `hermes --continue` | Wznów ostatnią sesję |
| `hermes gateway` | Start messaging gateway |
| `hermes gateway setup` | Konfiguracja platform (Telegram) |

---

## Slash commands (w sesji hermes)

| Komenda | Co robi |
|---------|---------|
| `/help` | Pokaż wszystkie komendy |
| `/model [provider:model]` | Zmień model w locie |
| `/tools` | Lista dostępnych narzędzi |
| `/personality [nazwa]` | Zmień osobowość |
| `/skills` | Lista skillów |
| `/new` lub `/reset` | Nowa rozmowa |
| `/save` | Zapisz rozmowę |
| `/compress` | Kompresuj kontekst |
| `/usage` | Użycie tokenów |
| `/verbose` | Przełącz poziom logowania narzędzi |
| `/reasoning [level]` | Ustaw effort: xhigh/high/medium/low/none |
| `Ctrl+C` | Przerwij bieżące zadanie |
| `Alt+Enter` | Nowa linia (wieloliniowy input) |

---

## Konfiguracja modeli

### Aktualny setup: Mistral AI (primary)

```yaml
# ~/.hermes/config.yaml
model:
  default: "mistral-large-latest"
  provider: "mistral"
  base_url: "https://api.mistral.ai/v1"
```

### Alternatywa: NVIDIA NIM (backup, większy model)

```yaml
model:
  default: "meta/llama-3.3-70b-instruct"
  provider: "custom"
  base_url: "https://integrate.api.nvidia.com/v1"
```

### Alternatywa: Ollama (dev, lokalny)

```yaml
model:
  default: "gemma4:e4b"
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
```

### Przełączanie w runtime

```
/model mistral:mistral-large-latest    # Mistral (primary)
/model ollama:gemma4:e4b               # Lokalne (dev)
```

Lub: `hermes model` (interaktywne menu).

---

## Pliki konfiguracyjne

| Plik | Lokalizacja | Rola |
|------|-------------|------|
| `config.yaml` | `~/.hermes/config.yaml` | Główna konfiguracja (model, terminal, narzędzia) |
| `.env` | `~/.hermes/.env` | Klucze API (sekrety) |
| `SOUL.md` | `~/.hermes/SOUL.md` | Persona Niggvisa (crypto trader) |
| `MEMORY.md` | `~/.hermes/memories/MEMORY.md` | Wiedza crypto + trade rules |
| `USER.md` | `~/.hermes/memories/USER.md` | Profil Damiana (agent aktualizuje) |
| `trading-config.yaml` | `~/.hermes/memories/trading-config.yaml` | Trading config (SL, TP, sizing, Jupiter) |
| `trading-wallet.json` | `~/.hermes/secrets/trading-wallet.json` | Keypair dedykowanego walleta |

**Priorytet**: CLI args > config.yaml > .env > domyślne wartości.
**Zasada**: Sekrety (klucze API) → `.env`. Reszta → `config.yaml`.

---

## Crypto Trading — Quick Reference

### Solana Blockchain Skill

```bash
# Cena SOL
python3 ~/.hermes/skills/solana/scripts/solana_client.py price SOL
 
# Portfolio walleta
python3 ~/.hermes/skills/solana/scripts/solana_client.py wallet <ADDRESS>
 
# Info o tokenie
python3 ~/.hermes/skills/solana/scripts/solana_client.py token <MINT_ADDRESS>
 
# Whale detector
python3 ~/.hermes/skills/solana/scripts/solana_client.py whales --min-sol 500
 
# Network stats
python3 ~/.hermes/skills/solana/scripts/solana_client.py stats
```

### Jupiter Swap — On-chain Execution

```bash
# Wallet info (adres, balance, auto-sizing)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
 
# Balance konkretnego tokena
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py balance --token <ADDR>
 
# Buy (auto-sized z trading-config.yaml)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <ADDR>
 
# Buy (manual size)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <ADDR> --amount-sol 0.05
 
# Sell 100%
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py sell --token <ADDR>
 
# Quote only (no execution)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py quote --input-mint SOL_MINT --output-mint <ADDR> --amount 50000000
```

> Agent zarządza keypairem w ~/.hermes/secrets/trading-wallet.json
> Jupiter API routuje przez Metis, JupiterZ, Dflow, OKX — best price.
> Config: trading-config.yaml (slippage, priority fee)

### Darmowe API do skanowania

| Źródło | Endpoint | Co daje |
|--------|----------|---------|
| DEXScreener | `api.dexscreener.com` | Nowe pary, volume, liquidity, price |
| Jupiter | `api.jup.ag/swap/v2` | On-chain swaps, best price routing |
| Birdeye | `public-api.birdeye.so` | Token analytics, trending, OHLCV |
| CoinGecko | `api.coingecko.com/api/v3` | Ceny, trending, market cap |
| pump.fun | `frontend-api.pump.fun` | Nowe memecoiny na Solanie |
| Solana RPC | `api.mainnet-beta.solana.com` | On-chain data |

### DEXScreener — endpointy (v1, April 2026)

```bash
# Token data po adresie (300 rpm)
curl "https://api.dexscreener.com/tokens/v1/solana/<TOKEN_ADDRESS>"
 
# Para po adresie (300 rpm)
curl "https://api.dexscreener.com/token-pairs/v1/solana/<TOKEN_ADDRESS>"
 
# Szukaj po nazwie/symbolu (300 rpm)
curl "https://api.dexscreener.com/latest/dex/search?q=<QUERY>"
 
# Nowe token profiles (60 rpm)
curl "https://api.dexscreener.com/token-profiles/latest/v1"
 
# Top boosty — trending (60 rpm)
curl "https://api.dexscreener.com/token-boosts/top/v1"
 
# Trending meta categories (60 rpm)
curl "https://api.dexscreener.com/metas/trending/v1"
```

> **Uwaga**: Stary endpoint `/latest/dex/pairs/solana/` już nie istnieje.
> Zawsze dodawaj header `User-Agent` — bez niego Python urllib dostaje 403.

### Custom Skills — Quick Reference

Instalacja custom skills:

```bash
cd ~/projects/hermes-agent-niggvis-crypto
bash custom-files/install-skills.sh           # Menu — domyślnie opcja 2 (skills only)
bash custom-files/install-skills.sh --skills  # Skrypty + config (bez SOUL/MEMORY)
bash custom-files/install-skills.sh --full    # Wszystko (reset agenta)
bash custom-files/install-skills.sh --config  # Tylko trading-config.yaml
```

Używanie custom skills:

```bash
# Scanner: trending, scan, search, metas
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 5
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py scan --min-liq 10000 --max-age 24
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py search "pepe"
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py metas
 
# Analyzer: analyze, safety, holders, liquidity
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze <ADDRESS> --full
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py safety <ADDRESS>
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py holders <ADDRESS> --top 10
 
# Risk Manager: check, status, kill, resume, config, limits
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py status
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py limits
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py check --amount 0.05 --token <ADDR>
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py kill --reason "suspicious"
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py resume
 
# Trade Executor: buy, sell, check-exits, portfolio, mode, config-propose
python3 ~/.hermes/skills/trade-executor/scripts/executor.py portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <ADDR> --reason "trending"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <ADDR> --amount 0.05 --reason "trending"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id 1 --reason "take profit"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id 1 --pct 50 --reason "partial TP"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py check-exits
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode paper
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode real
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose --key stop_loss_pct --value -25 --reason "tighter SL"
 
# Jupiter Swap: buy, sell, quote, balance, wallet
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py balance --token <ADDR>
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py buy --token <ADDR> --amount-sol 0.05
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py sell --token <ADDR> --pct 100
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py quote --input-mint SOL_MINT --output-mint <ADDR> --amount 50000000
 
# Trade Journal: add, close, show, stats, export
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats --days 7
python3 ~/.hermes/skills/trade-journal/scripts/journal.py export
 
# Learning Engine: analyze, update, patterns
python3 ~/.hermes/skills/trade-journal/scripts/learning.py analyze
python3 ~/.hermes/skills/trade-journal/scripts/learning.py update
python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns
```

### Birdeye — przydatne endpointy

```bash
# Trending tokeny na Solanie
curl -H "X-API-KEY: public" "https://public-api.birdeye.so/defi/tokenlist?sort_by=v24hUSD&sort_type=desc&chain=solana"
 
# Token overview
curl -H "X-API-KEY: public" "https://public-api.birdeye.so/defi/token_overview?address=<TOKEN_ADDRESS>&chain=solana"
```

---

## Memory system

Hermes automatycznie zarządza pamięcią:
- **MEMORY.md** — wiedza agenta (crypto analysis, trade rules, learned patterns)
- **USER.md** — profil Damiana (preferencje, styl, tolerancja ryzyka)

Agent **samodzielnie aktualizuje** te pliki co ~10 wiadomości.

---

## Skills system

```bash
# Przeglądaj i instaluj skille
hermes skills search crypto
hermes skills search blockchain
hermes skills install official/blockchain/solana
 
# W sesji:
/skills                        # Lista zainstalowanych
```

Agent tworzy nowe skille automatycznie po złożonych zadaniach (~15 tool calls).
Custom skills do crypto tradingu powstają z promptów — patrz sekcja Cron.

---

## Cron — Scheduled Trading Jobs

Hermes ma wbudowany cron scheduler. Konfiguracja przez naturalny język:

### Zainstalowane cron jobs

| Job | Schedule | Co robi |
|-----|----------|--------|
| `token-scan` | co 15 min | Skanuje trending, sprawdza safety, paper buy jeśli ok |
| `position-check` | co 30 min | Backup check stop-loss/take-profit (guardian robi to co 2 min) |
| `trend-analysis` | co 4h | Analiza trendów (metas, kategorie, porównanie z portfolio) |
| `morning-report` | 8:00 UTC | Raport portfolio + risk status + wczorajsze P&L |
| `daily-summary` | 23:00 UTC | Podsumowanie dnia + self-learning (learning.py update) |
| `weekly-recap` | Niedziela 10:00 | Tygodniowa analiza + deep learning review + strategy update |

### Setup cron

```bash
# Usuń stary jobs.json (jeśli był zepsuty)
rm -f ~/.hermes/cron/jobs.json
 
# Wgraj joby
python3 custom-files/setup-cron.py
 
# Zainstaluj croniter (potrzebny do daily/weekly)
uv pip install croniter
```

### Position Guardian (real-time SL/TP/BE)

Guardian to lekki monitor cen (BEZ LLM). Sprawdza pozycje w pętli z adaptacyjnym
interwałem (idle/active/hot). Funkcje:
- **Stop-loss** — zamyka gdy P&L ≤ SL%
- **Take-profit** — zamyka powyżej TP% (z trailing stop opcjonalnie)
- **Break-even SL** — przesuwa SL na 0% gdy pozycja osiągnie +50% (konfigurowalny)
- **Trailing stop** — po osiągnięciu TP%, śledzi peak i zamyka na pullbacku
- **Wallet sync** — co 10 cykli sprawdza on-chain balanse, zamyka orphany
- **Telegram** — powiadamia o każdym sell (SL/TP/trailing/BE/kill)
- **Kill switch** — awaryjne zamknięcie wszystkiego

```bash
# Start (w tle, screen/tmux) — adaptacyjny interwał
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
 
# Z większą historią TUI
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --history 5
 
# Dry run (sprawdza ale nie zamyka)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --dry-run
 
# Jednorazowy check (+ wallet sync)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py
 
# Bez TUI (np. do logowania)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --no-tui
 
# Guardian log
tail -f ~/.hermes/cron/guardian.log
```

Adaptacyjny interwał (z trading-config.yaml → guardian):
- **idle** (120s): brak otwartych pozycji
- **active** (20s): pozycje w normalnym zakresie
- **hot** (10s): pozycja blisko SL lub TP (w strefie hot_zone_pct)

Guardian blokuje drugie uruchomienie (file lock) — bezpieczne dla cron.

### Notyfikacje Telegram — konfiguracja

Guardian wysyła powiadomienia bezpośrednio przez Telegram Bot API.
Każdy typ eventu można włączyć/wyłączyć osobno w `trading-config.yaml`:

```yaml
notifications:
  on_stop_loss: true              # 🚨 Stop loss triggered
  on_take_profit: true            # 🎯 Take profit hit
  on_trailing_stop: true          # 📉 Trailing stop triggered
  on_breakeven_activated: true    # 🔒 SL przesunięty na break-even
  on_kill_switch: true            # 🔴 Kill switch — emergency close
  on_wallet_sync: true            # 🔄 Orphan position closed
  on_buy: true                    # ✅ New trade executed
  require_config_approval: true   # Agent musi prosić o OK przed zmianą config
```

Ustaw `false` aby wyciszyć konkretny typ. Token bota i chat_id czytane z `~/.hermes/gateway.json`.

### Session Analyzer

Skrypt do analizy sesji Hermes — wyciąga trades, bloki, błędy, zmiany config.
Output w formacie Markdown — nadaje się do wklejenia do AI assistanta lub git commit.

```bash
# Analiza wszystkich sesji (WSL) — wypisuje na stdout
python3 custom-files/analyze-sessions.py ~/.hermes/sessions/
 
# Zapisz raport do pliku MD
python3 custom-files/analyze-sessions.py ~/.hermes/sessions/ -o custom-files/.hermes-copied/sessions/session-report.md
 
# Analiza skopiowanych sesji (macOS)
python3 custom-files/analyze-sessions.py custom-files/.hermes-copied/sessions/
 
# Zapisz raport skopiowanych sesji
python3 custom-files/analyze-sessions.py custom-files/.hermes-copied/sessions/ -o session-report.md
```

**Quick copy (WSL)**:
```bash
python3 ~/projects/hermes-agent-niggvis-crypto/custom-files/analyze-sessions.py ~/.hermes/sessions/ -o ~/session-report.md && cat ~/session-report.md
```

Raport zawiera: wallet balance, trades, blocked trades, config changes, agent responses, position checks, listę sesji.

### Self-Learning Engine

Agent uczy się na zamkniętych trade'ach. Learning.py analizuje wzorce
(statystycznie, bez LLM) i dopisuje je do MEMORY.md.

```bash
# Pokaż analizę
python3 ~/.hermes/skills/trade-journal/scripts/learning.py analyze
 
# Analizuj + zapisz do MEMORY.md
python3 ~/.hermes/skills/trade-journal/scripts/learning.py update
 
# Ostatnie 7 dni
python3 ~/.hermes/skills/trade-journal/scripts/learning.py update --days 7
 
# Pokaż odkryte wzorce
python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns
```

Daily-summary i weekly-recap automatycznie wywołują learning.py update.

### Cron Viewer

```bash
# Overview wszystkich jobów + ostatni output
python3 ~/projects/hermes-agent-niggvis-crypto/custom-files/scripts/cron_viewer.py
 
# Szczegóły jednego joba
python3 custom-files/scripts/cron_viewer.py --job token-scan
 
# Czytaj ostatni output
python3 custom-files/scripts/cron_viewer.py --job token-scan --read last
 
# Guardian log
python3 custom-files/scripts/cron_viewer.py --tail 50
```

### Zarządzanie cron (w sesji hermes)

```
/cron list                     # Lista aktywnych jobów
/cron pause <id>               # Wstrzymaj job
/cron resume <id>              # Wznów job
/cron run <id>                 # Uruchom ręcznie
/cron remove <id>              # Usuń job
/cron add "every 2h" "Check server status" --skill crypto-scanner
```

---

## Safety & Kill Switch

### Zatrzymanie tradingu

```
❯ /stop                        # Na Telegramie — natychmiast wstrzymaj trading
❯ Wstrzymaj trading            # Naturalny język — agent zatrzyma wszystkie cron jobs
```

### Limity (w trading-config.yaml)

| Limit | Wartość | Opis |
|-------|---------|------|
| Max trade size | 0.5 SOL | `position_sizing.max_trade_sol` |
| Position sizing | 5% | `position_sizing.position_pct` — % walleta na trade |
| Max open positions | 5 | `position_sizing.max_positions` |
| Stop-loss | -30% | `risk.stop_loss_pct` — per trade, nie portfolio |
| Take-profit | +100% | `risk.take_profit_pct` — min % zysku do zamknięcia |
| Trailing stop | 15% | `risk.trailing_stop_pct` — pullback od peaku |
| Break-even trigger | +50% | `risk.breakeven_trigger_pct` — SL→0% po osiągnięciu |
| Daily loss limit | -20% | `risk.daily_loss_limit_pct` — suma P&L zamkniętych |
| Min safety score | 60 | `filters.min_safety_score` |
| Min liquidity | $10K | `filters.min_liquidity_usd` |

### Rugpull Red Flags (agent sprawdza automatycznie)

- ❌ Mint authority NOT revoked
- ❌ Freeze authority active
- ❌ LP not locked/burned
- ❌ Top holder > 20% supply
- ❌ No social media / website
- ❌ Age < 1 hour + sudden volume spike
- ❌ Honeypot (can buy, can't sell)

---

## Telegram Gateway

```bash
hermes gateway setup           # Konfiguracja Telegram bota
hermes gateway start           # Start gateway
```

Po uruchomieniu — rozmawiaj z agentem przez Telegram.
Agent wysyła alerty, raporty i prosi o potwierdzenie transakcji.

---

## Przed git pull

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git pull origin main
 
# Jeśli pyproject.toml się zmienił:
uv pip install -e ".[all]"
 
# Zainstaluj/aktualizuj skills i trading-config:
bash custom-files/install-skills.sh --skills
 
# Jeśli chcesz też nadpisać SOUL.md/MEMORY.md (reset agenta):
bash custom-files/install-skills.sh --full
 
# Restart guardiana (tmux):
# Ctrl+C w oknie guardiana, potem:
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --history 5
```

Merge z upstream (tylko WSL): Zob. `custom-files/docs/#GIT-WORKFLOW.md`.

---

## Rozwiązywanie problemów

| Problem | Rozwiązanie |
|---------|-------------|
| `hermes: command not found` | `source ~/.bashrc` lub sprawdź `~/.local/bin/hermes` |
| `uv: command not found` | `curl -LsSf https://astral.sh/uv/install.sh \| sh && source ~/.bashrc` |
| `API key not set` | Uzupełnij `~/.hermes/.env` |
| Model za wolny | Przełącz na Mistral/NIM (API) zamiast Ollama |
| Solana RPC rate limit | Ustaw prywatny RPC w trading-config.yaml lub `export SOLANA_RPC_URL=...` |
| Jupiter swap failed | Sprawdź balance: `jupiter_swap.py wallet`, sprawdź slippage w trading-config.yaml |
| Kontekst za długi | `/compress` lub zmniejsz `compression.threshold` |
| Tool calls nie działają | Upewnij się że model wspiera function calling |
| Agent nie skanuje | Sprawdź cron: `/cron list` |

---
