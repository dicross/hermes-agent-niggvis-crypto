# Hermes Agent Niggvis Crypto — Instalacja

> Autonomiczny agent AI do crypto tradingu na Solanie.
> Bazuje na Hermes Agent (Nous Research) z personą Niggvis i integracją z Trojan on Solana.
> Customizacja przez pliki w `~/.hermes/` — bez modyfikacji kodu źródłowego.

---

## 1. Wymagania

| Komponent | Minimum | Uwagi |
|-----------|---------|-------|
| Git | 2.x | jedyny hard requirement |
| uv | latest | instalator go pobiera automatycznie |
| Python | 3.11 | uv pobiera sam, bez sudo |
| Ollama | latest | opcjonalnie, na dev (WSL) |

Nie potrzebujesz Node.js — browser tools nie są wymagane do tradingu.

---

## 2. Architektura repozytoriów

```
┌──────────────────────────────────────┐
│  PUBLIC REPO (upstream)              │
│  github.com/NousResearch/            │
│  hermes-agent                        │
│  ── silnik, nowe wersje ──           │
└──────────┬───────────────────────────┘
           │ fetch/merge (tylko WSL)
           ▼
┌──────────────────────────────────────┐
│  PRIVATE REPO (origin)               │
│  github.com/dicross/                 │
│  hermes-agent-niggvis-crypto         │
│  ── custom-files, SOUL, MEMORY ──    │
└──┬───────────┬───────────┬───────────┘
   │           │           │
   ▼           ▼           ▼
 WSL-PC     macbook       VPS
  (dev)    (Copilot)   (produkcja)
```

---

## 3. Utworzenie prywatnego repo (jednorazowo)

Na GitHub utwórz prywatne repo:
- Nazwa: `hermes-agent-niggvis-crypto`
- Właściciel: `dicross`
- **Puste** — bez README, .gitignore, licencji
- URL: `git@github.com:dicross/hermes-agent-niggvis-crypto.git`

---

## 4. Instalacja na WSL-PC (development)

### 4.1 Klonowanie

```bash
cd ~/projects
# Jeśli istnieje pusty katalog:
rmdir hermes-agent-niggvis-crypto 2>/dev/null
 
# Klonuj z publicznego repo Hermes Agent
git clone --recurse-submodules https://github.com/NousResearch/hermes-agent.git hermes-agent-niggvis-crypto
cd hermes-agent-niggvis-crypto
```

### 4.2 Konfiguracja remotes

```bash
# Zmień origin na prywatne repo
git remote set-url origin git@github.com:dicross/hermes-agent-niggvis-crypto.git
 
# Dodaj upstream (publiczne NousResearch)
git remote add upstream https://github.com/NousResearch/hermes-agent.git
 
# Weryfikacja
git remote -v
# origin    git@github.com:dicross/hermes-agent-niggvis-crypto.git (fetch)
# origin    git@github.com:dicross/hermes-agent-niggvis-crypto.git (push)
# upstream  https://github.com/NousResearch/hermes-agent.git (fetch)
# upstream  https://github.com/NousResearch/hermes-agent.git (push)
 
# Push do prywatnego repo (pierwszy raz)
git push -u origin main
```

### 4.3 Instalacja uv i venv

```bash
# Zainstaluj uv (jeśli nie masz)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
 
# Utwórz venv z Python 3.11
cd ~/projects/hermes-agent-niggvis-crypto
uv venv venv --python 3.11
export VIRTUAL_ENV="$(pwd)/venv"
 
# Zainstaluj wszystkie zależności
uv pip install -e ".[all]"
```

### 4.4 Konfiguracja ~/.hermes/

```bash
# Utwórz strukturę katalogów
mkdir -p ~/.hermes/{cron,sessions,logs,memories,skills,pairing,hooks,image_cache,audio_cache}
 
# Skopiuj nasze pliki konfiguracyjne
cp custom-files/config.example.yaml ~/.hermes/config.yaml
cp custom-files/.env.example ~/.hermes/.env
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
 
# WAŻNE: edytuj .env i uzupełnij klucze API
nano ~/.hermes/.env
```

### 4.5 Zainstaluj optional skill: Solana blockchain

```bash
# Skopiuj Solana blockchain skill do ~/.hermes/skills/
cp -r optional-skills/blockchain/solana ~/.hermes/skills/solana
 
# Weryfikacja
python3 ~/.hermes/skills/solana/scripts/solana_client.py stats
```

### 4.6 (Opcjonalnie) Zainstaluj Ollama dla dev

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma4:e4b
```

> Na WSL dev Ollama jest opcjonalna — primary model to Mistral/NIM przez API.
> Ollama przydaje się do testów offline i background processing.

### 4.7 Globalny dostęp do komendy hermes

```bash
mkdir -p ~/.local/bin
ln -sf "$(pwd)/venv/bin/hermes" ~/.local/bin/hermes
 
# Upewnij się że ~/.local/bin jest w PATH
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
 
# Weryfikacja
hermes --version
```

### 4.8 Konfiguracja Telegram Gateway

```bash
# 1. Utwórz bota na Telegramie przez @BotFather
#    - /newbot → podaj nazwę → zapisz TOKEN
#    - Wpisz token do ~/.hermes/.env jako TELEGRAM_BOT_TOKEN
 
# 2. Konfiguracja gateway
hermes gateway setup
# → Wybierz Telegram
# → Podaj token bota
# → Podaj swoje Telegram user ID (lub /start do bota i sprawdź logi)
 
# 3. Start gateway
hermes gateway start
```

### 4.9 Konfiguracja Trojan on Solana

Trojan on Solana to osobny bot na Telegramie — Hermes będzie wysyłał mu komendy.

```
Konfiguracja:
1. Otwórz Trojan on Solana (@solaboratorybot) na Telegramie
2. Skonfiguruj wallet (import lub utwórz nowy)
3. Wpłać SOL na wallet Trojana (min. 0.5 SOL na start)
4. Zanotuj chat ID Trojana → wpisz do ~/.hermes/.env jako TROJAN_BOT_CHAT_ID
5. Ustaw w Trojanie:
   - Auto-buy: OFF (Hermes będzie decydował)
   - Slippage: 15-20%
   - Priority fee: medium
   - MEV protection: ON
```

> **BEZPIECZEŃSTWO**: Trojan wallet to osobny wallet z ograniczonym budżetem.
> NIE TRZYMAJ tu dużych kwot. Start: $100 w SOL + tokeny.

### 4.10 Weryfikacja instalacji

```bash
hermes doctor        # Pełna diagnostyka
hermes status        # Aktualna konfiguracja
hermes               # Start — test rozmowy
```

Test persona:
```
❯ Kim jesteś?
```
Agent powinien odpowiedzieć jako Niggvis — crypto trading assistant.

Test narzędzi:
```
❯ Sprawdź cenę SOL
```
Agent powinien użyć Solana skill lub web search.

---

## 5. Instalacja na macOS (Copilot — tracking only)

```bash
cd ~/projects
 
# Klonuj z prywatnego repo
git clone git@github.com:dicross/hermes-agent-niggvis-crypto.git
cd hermes-agent-niggvis-crypto
 
# Remote jest już ustawiony na origin
git remote -v
# origin  git@github.com:dicross/hermes-agent-niggvis-crypto.git
```

macOS służy do śledzenia zmian i pracy z Copilotem.
Opcjonalnie można zainstalować Hermesa lokalnie (jak w WSL), ale nie jest to wymagane.

Opcjonalna instalacja lokalna:
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
uv venv venv --python 3.11
export VIRTUAL_ENV="$(pwd)/venv"
uv pip install -e ".[all]"
mkdir -p ~/.hermes/{cron,sessions,logs,memories,skills,pairing,hooks}
cp custom-files/config.example.yaml ~/.hermes/config.yaml
cp custom-files/.env.example ~/.hermes/.env
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
mkdir -p ~/.local/bin
ln -sf "$(pwd)/venv/bin/hermes" ~/.local/bin/hermes
```

---

## 6. Instalacja na VPS (Contabo — produkcja) — TODO

VPS będzie korzystał wyłącznie z API (Mistral / NIM), bez Ollama.
Instrukcja zostanie uzupełniona po uruchomieniu na WSL.

Szkic:
```bash
# 1. SSH do VPS
ssh root@<contabo-ip>
 
# 2. Utwórz użytkownika (nie rób jako root)
adduser hermes
usermod -aG sudo hermes
su - hermes
 
# 3. Klonuj i zainstaluj
cd ~/projects
git clone git@github.com:dicross/hermes-agent-niggvis-crypto.git
cd hermes-agent-niggvis-crypto
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv venv venv --python 3.11
export VIRTUAL_ENV="$(pwd)/venv"
uv pip install -e ".[all]"
 
# 4. Konfiguracja (Mistral/NIM, Telegram gateway, Trojan)
mkdir -p ~/.hermes/{cron,sessions,logs,memories,skills,pairing,hooks}
cp custom-files/config.example.yaml ~/.hermes/config.yaml
cp custom-files/.env.example ~/.hermes/.env
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
# → edytuj .env z kluczami API
 
# 5. Konfiguracja systemd (24/7)
# TODO: plik .service do hermes gateway
 
# 6. Start
hermes gateway setup
hermes gateway start
```

---

## 7. Konfiguracja modeli LLM

### Mistral AI (primary — szybki, EU datacenter)

```yaml
# ~/.hermes/config.yaml
model:
  default: "mistral-large-latest"
  provider: "mistral"
  base_url: "https://api.mistral.ai/v1"
```

W `~/.hermes/.env`:
```env
MISTRAL_API_KEY=twoj-klucz-mistral
```

### NVIDIA NIM (backup — większy model)

```yaml
model:
  default: "meta/llama-3.3-70b-instruct"
  provider: "custom"
  base_url: "https://integrate.api.nvidia.com/v1"
```

W `~/.hermes/.env`:
```env
OPENAI_API_KEY=nvapi-twoj-klucz
```

### Ollama (dev — lokalne, opcjonalnie)

```yaml
model:
  default: "gemma4:e4b"
  provider: "ollama"
  base_url: "http://localhost:11434/v1"
```

### Przełączanie modeli w runtime

```bash
hermes model                                   # Interaktywny wybór
/model mistral:mistral-large-latest            # W sesji: Mistral
/model custom:meta/llama-3.3-70b-instruct      # W sesji: NIM
/model ollama:gemma4:e4b                       # W sesji: lokalny
```

---

## 8. Struktura projektu (po instalacji)

```
~/projects/hermes-agent-niggvis-crypto/
├── custom-files/                      ← NASZE pliki (commitujemy)
│   ├── docs/
│   │   ├── #INSTALLATION.md          ← ten plik
│   │   ├── #CHEATSHEET.md            ← codzienny cheatsheet
│   │   └── #GIT-WORKFLOW.md          ← git workflow
│   ├── config.example.yaml            ← szablon config
│   ├── .env.example                   ← szablon kluczy API
│   ├── SOUL.md                        ← persona Niggvis crypto
│   └── MEMORY.md                      ← profesjonalna wiedza crypto
├── agent/                             ← kod źródłowy Hermes (upstream)
├── tools/                             ← narzędzia agenta
├── skills/                            ← wbudowane skille
├── optional-skills/blockchain/        ← Solana + Base skills
├── cli.py                             ← główne CLI
├── run_agent.py                       ← runner agenta
├── pyproject.toml                     ← zależności Python
├── venv/                              ← nie commituj
└── ...
 
~/.hermes/                             ← PER MASZYNA (nie commituj)
├── config.yaml                        ← konfiguracja (z config.example.yaml)
├── .env                               ← klucze API
├── SOUL.md                            ← persona Niggvis (z custom-files)
├── memories/
│   ├── MEMORY.md                      ← wiedza crypto (z custom-files)
│   └── USER.md                        ← profil Damiana (agent tworzy/aktualizuje)
├── skills/
│   ├── solana/                        ← Solana blockchain skill
│   ├── crypto-scanner/                ← agent stworzy
│   ├── trade-executor/                ← agent stworzy
│   ├── trade-journal/                 ← agent stworzy
│   └── risk-manager/                  ← agent stworzy
├── sessions/                          ← historia sesji
├── logs/                              ← logi
└── cron/                              ← scheduled jobs (skanowanie, raporty)
```

---

## 9. Troubleshooting

### "hermes: command not found"
```bash
source ~/.bashrc
ls -la ~/.local/bin/hermes
```

### "uv: command not found"
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### "API key not set" / "401 Unauthorized"
```bash
cat ~/.hermes/.env
# Sprawdź czy klucze są poprawne i nie mają spacji/nowych linii
```

### "hermes doctor" zgłasza błędy
```bash
python --version           # >= 3.11?
cat ~/.hermes/config.yaml  # provider/model poprawne?
cat ~/.hermes/.env         # klucze API uzupełnione?
hermes doctor              # pełna diagnostyka
```

### "Tool calls nie działają"
Model musi wspierać function calling. Mistral Large i NIM Llama 3.3 wspierają natywnie.
Jeśli używasz Ollama — gemma4 wspiera, inne modele mogą nie.

### "Solana skill: connection refused"
```bash
# Publiczny RPC ma limity. Sprawdź:
python3 ~/.hermes/skills/solana/scripts/solana_client.py stats
 
# Jeśli rate-limited, ustaw prywatny RPC:
export SOLANA_RPC_URL="https://your-helius-or-quicknode-url"
```

### "Trojan bot nie odpowiada"
```bash
# Sprawdź czy Trojan bot jest aktywny na Telegramie
# Sprawdź czy TROJAN_BOT_CHAT_ID jest poprawny w ~/.hermes/.env
# Trojan wymaga aktywnej sesji — otwórz bota ręcznie na telefonie
```

---
