# Hermes Agent Niggvis Crypto — Instalacja

> Autonomiczny agent AI do crypto tradingu na Solanie.
> Bazuje na Hermes Agent (Nous Research) z personą Niggvis i Jupiter API (on-chain swaps).
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

### 4.9 Konfiguracja Jupiter Wallet (trading)

Hermes wykonuje swapy on-chain przez Jupiter V2 Meta-Aggregator.
Potrzebny jest dedykowany wallet z keypairem.

```bash
# 1. Utwórz katalog na sekrety
mkdir -p ~/.hermes/secrets
chmod 700 ~/.hermes/secrets
 
# 2. Wygeneruj nowy keypair (lub skopiuj istniejący)
# Format: JSON array of bytes, np. [174,52,3,...]
# Możesz użyć solana-keygen:
solana-keygen new --outfile ~/.hermes/secrets/trading-wallet.json --no-bip39-passphrase
 
# Lub skopiuj istniejący keypair:
# cp /sciezka/do/keypair.json ~/.hermes/secrets/trading-wallet.json
chmod 600 ~/.hermes/secrets/trading-wallet.json
 
# 3. Skopiuj trading config
cp custom-files/trading-config.yaml ~/.hermes/memories/trading-config.yaml
 
# 4. Zainstaluj solders (do podpisywania transakcji)
pip install solders
 
# 5. Wpłać SOL na adres walleta
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
# → Pokaże adres i balance. Wyślij min. 0.1 SOL na start.
 
# 6. (Opcjonalnie) Ustaw Jupiter API key w .env
# JUPITER_API_KEY=twoj-klucz   # bez klucza działa, ale z limitem
```

> **BEZPIECZEŃSTWO**: Trading wallet to osobny wallet z ograniczonym budżetem.
> NIE TRZYMAJ tu dużych kwot. Keypair nigdy nie opuszcza maszyny.
> Agent podpisuje transakcje lokalnie — prywatny klucz nie jest wysyłany do API.

### 4.10 Zainstaluj custom skills

```bash
bash custom-files/install-skills.sh
```

Skrypt kopiuje 5 skilli + trading-config.yaml do `~/.hermes/`.

### 4.11 Weryfikacja instalacji

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

## 6. Instalacja na VPS (Contabo — produkcja)

VPS korzysta wyłącznie z API (Mistral / NIM / Qwen), bez Ollama.

### 6.1 Podstawowa instalacja

```bash
# 1. SSH do VPS
ssh root@<contabo-ip>
 
# 2. Utwórz użytkownika (nie rób jako root)
adduser niggvis
usermod -aG sudo niggvis
su - niggvis
 
# 3. Zainstaluj tmux (jeśli nie ma)
sudo apt update && sudo apt install -y tmux
 
# 4. Klonuj i zainstaluj
mkdir -p ~/projects && cd ~/projects
git clone git@github.com:dicross/hermes-agent-niggvis-crypto.git
cd hermes-agent-niggvis-crypto
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
uv venv venv --python 3.11
export VIRTUAL_ENV="$(pwd)/venv"
uv pip install -e ".[all]"
pip install solders   # do Jupiter swapów
 
# 5. Konfiguracja
mkdir -p ~/.hermes/{cron,sessions,logs,memories,skills,pairing,hooks,secrets}
cp custom-files/config.example.yaml ~/.hermes/config.yaml
cp custom-files/.env.example ~/.hermes/.env
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
bash custom-files/install-skills.sh
# → edytuj ~/.hermes/.env z kluczami API
nano ~/.hermes/.env
 
# 6. Skopiuj keypair walleta (z dev maszyny)
# scp niggvis@dev-machine:~/.hermes/secrets/trading-wallet.json ~/.hermes/secrets/
chmod 600 ~/.hermes/secrets/trading-wallet.json
 
# 7. Globalny dostęp
mkdir -p ~/.local/bin
ln -sf "$(pwd)/venv/bin/hermes" ~/.local/bin/hermes
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
 
# 8. Telegram gateway
hermes gateway setup
```

### 6.2 Uruchamianie w tmux (zalecane)

tmux utrzymuje procesy po rozłączeniu SSH.

```bash
# Utwórz sesję z dwoma oknami: gateway + guardian
tmux new-session -d -s hermes
 
# Okno 0: Hermes gateway (Telegram bot + cron)
tmux send-keys -t hermes:0 'hermes gateway start' Enter
 
# Okno 1: Guardian (fast price monitor)
tmux new-window -t hermes:1 -n guardian
tmux send-keys -t hermes:1 'python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --history 5' Enter
 
# Attach — podgląd na żywo
tmux attach -t hermes
 
# Nawigacja w tmux:
#   Ctrl+B, 0    — przejdź do okna gateway
#   Ctrl+B, 1    — przejdź do okna guardian
#   Ctrl+B, D    — detach (procesy działają dalej)
#   Ctrl+B, [    — scroll mode (q aby wyjść)
```

Po rozłączeniu SSH:
```bash
# Reattach do sesji
tmux attach -t hermes
 
# Sprawdź czy działa (bez attach)
tmux list-sessions
# hermes: 2 windows (created ...)
```

### 6.3 Alternatywa: screen

```bash
# Start
screen -S hermes
hermes gateway start
# Ctrl+A, D — detach
 
# Nowe okno na guardian
screen -S guardian
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
# Ctrl+A, D — detach
 
# Reattach
screen -r hermes
screen -r guardian
 
# Lista sesji
screen -ls
```

### 6.4 Alternatywa: systemd (pełny autostart)

Jeśli VPS restartuje się — tmux nie przeżyje. systemd uruchomi procesy automatycznie.

```bash
# Utwórz plik serwisu: hermes gateway
sudo tee /etc/systemd/system/hermes-gateway.service << 'EOF'
[Unit]
Description=Hermes Agent Telegram Gateway
After=network-online.target
Wants=network-online.target
 
[Service]
Type=simple
User=niggvis
WorkingDirectory=/home/niggvis/projects/hermes-agent-niggvis-crypto
EnvironmentFile=/home/niggvis/.hermes/.env
ExecStart=/home/niggvis/.local/bin/hermes gateway start
Restart=on-failure
RestartSec=10
 
[Install]
WantedBy=multi-user.target
EOF
 
# Utwórz plik serwisu: guardian
sudo tee /etc/systemd/system/hermes-guardian.service << 'EOF'
[Unit]
Description=Hermes Guardian — Price Monitor
After=network-online.target
Wants=network-online.target
 
[Service]
Type=simple
User=niggvis
WorkingDirectory=/home/niggvis/.hermes/skills/trade-executor/scripts
EnvironmentFile=/home/niggvis/.hermes/.env
ExecStart=/home/niggvis/projects/hermes-agent-niggvis-crypto/venv/bin/python3 guardian.py --watch --no-tui
Restart=on-failure
RestartSec=30
 
[Install]
WantedBy=multi-user.target
EOF
 
# Włącz i uruchom
sudo systemctl daemon-reload
sudo systemctl enable hermes-gateway hermes-guardian
sudo systemctl start hermes-gateway hermes-guardian
 
# Status
sudo systemctl status hermes-gateway
sudo systemctl status hermes-guardian
 
# Logi
journalctl -u hermes-gateway -f
journalctl -u hermes-guardian -f
```

> **Rekomendacja**: Na początek tmux (łatwiejszy debug). Jak działa stabilnie → systemd.
> Oba podejścia można łączyć: systemd do gateway, tmux do guardiana (bo ma TUI).

### 6.5 Aktualizacja na VPS

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git pull origin main
bash custom-files/install-skills.sh
 
# Jeśli systemd:
sudo systemctl restart hermes-gateway hermes-guardian
 
# Jeśli tmux:
tmux send-keys -t hermes:0 C-c
tmux send-keys -t hermes:0 'hermes gateway start' Enter
tmux send-keys -t hermes:1 C-c
tmux send-keys -t hermes:1 'python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch --history 5' Enter
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
│   ├── trading-config.yaml            ← trading config (SL/TP/sizing/Jupiter)
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
│   ├── USER.md                        ← profil Damiana (agent tworzy/aktualizuje)
│   └── trading-config.yaml            ← trading config (install-skills.sh kopiuje)
├── secrets/
│   └── trading-wallet.json            ← keypair dedykowanego walleta
├── skills/
│   ├── solana/                        ← Solana blockchain skill
│   ├── crypto-scanner/                ← skanowanie tokenów
│   ├── trade-executor/                ← executor + Jupiter + guardian
│   ├── trade-journal/                 ← journal + learning
│   ├── onchain-analyzer/              ← analiza bezpieczeństwa tokenów
│   └── risk-manager/                  ← limity, kill switch
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

### "Jupiter swap failed"
```bash
# Sprawdź balance walleta
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
 
# Za mało SOL? Doładuj wallet.
# Slippage za niski? Zwiększ w trading-config.yaml:
#   jupiter.slippage_bps: 2000  (20%)
 
# Token nieaktywny? Sprawdź na DEXScreener czy ma liquidity.
```

### "Guardian: price unavailable"
```bash
# DEXScreener może mieć rate limit. Zwiększ interval:
python3 guardian.py --watch --interval 180
 
# Sprawdź ręcznie czy token istnieje:
curl -s 'https://api.dexscreener.com/tokens/v1/solana/<address>' | head -c 200
```

---
