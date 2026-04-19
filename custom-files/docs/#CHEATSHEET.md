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

Znane symbole: SOL, USDC, USDT, BONK, JUP, WETH, JTO, mSOL, WIF, MEW, BOME, PENGU.

### Trojan on Solana — Komendy (przez Telegram)

```
/buy <TOKEN_ADDRESS> <AMOUNT_SOL>      # Kup token za X SOL
/sell <TOKEN_ADDRESS> <PERCENTAGE>      # Sprzedaj X% pozycji
/positions                              # Pokaż otwarte pozycje
/wallet                                 # Saldo walleta
/settings                               # Ustawienia bota
/referral                               # Referral info
```

> Hermes wysyła te komendy do Trojan bota przez Telegram API.
> Agent NIE zarządza private keys — Trojan to robi.

### Darmowe API do skanowania

| Źródło | Endpoint | Co daje |
|--------|----------|---------|
| DEXScreener | `api.dexscreener.com/latest/dex` | Nowe pary, volume, liquidity, price |
| Birdeye | `public-api.birdeye.so` | Token analytics, trending, OHLCV |
| CoinGecko | `api.coingecko.com/api/v3` | Ceny, trending, market cap |
| pump.fun | `frontend-api.pump.fun` | Nowe memecoiny na Solanie |
| Solana RPC | `api.mainnet-beta.solana.com` | On-chain data (w Solana skill) |

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
 
# Trade Executor: buy, sell, check-exits, portfolio, mode
python3 ~/.hermes/skills/trade-executor/scripts/executor.py portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <ADDR> --amount 0.05 --reason "trending"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id 1 --reason "take profit"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py check-exits
python3 ~/.hermes/skills/trade-executor/scripts/executor.py mode paper
 
# Trade Journal: add, close, show, stats, export
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats --days 7
python3 ~/.hermes/skills/trade-journal/scripts/journal.py export
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
| `position-check` | co 1h | Backup check stop-loss/take-profit (guardian robi to co 2 min) |
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

### Position Guardian (real-time SL/TP)

Guardian to lekki monitor cen (BEZ LLM). Sprawdza co 2 min czy otwarty trade
nie przekroczył stop-loss lub take-profit. Jeśli tak — zamyka trade natychmiast.

```bash
# Start (w tle, screen/tmux)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
 
# Co 3 min zamiast 2
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --interval 180
 
# Dry run (sprawdza ale nie zamyka)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --dry-run
 
# Jednorazowy check
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py
 
# Guardian log
tail -f ~/.hermes/cron/guardian.log
```

Guardian blokuje drugie uruchomienie (file lock) — bezpieczne dla cron.

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

### Limity (w MEMORY.md + config)

| Limit | Wartość | Opis |
|-------|---------|------|
| Max trade size | $5-10 | Na start, zwiększ po udanym paper trading |
| Daily loss limit | -20% | Jeśli portfel -20% dziennie → stop |
| Max open positions | 5 | Nie więcej niż 5 tokenów naraz |
| Min liquidity | $10K | Nie kupuj tokenów z liquidity < $10K |
| Rugpull check | ZAWSZE | Sprawdź kontrakt przed każdym buy |

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
 
# Jeśli SOUL.md lub MEMORY.md się zmienił:
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
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
| Solana RPC rate limit | Ustaw prywatny RPC: `export SOLANA_RPC_URL=...` |
| Trojan nie odpowiada | Sprawdź sesję Trojana na TG, sprawdź chat ID w `.env` |
| Kontekst za długi | `/compress` lub zmniejsz `compression.threshold` |
| Tool calls nie działają | Upewnij się że model wspiera function calling |
| Agent nie skanuje | Sprawdź cron: `/cron list` |

---
