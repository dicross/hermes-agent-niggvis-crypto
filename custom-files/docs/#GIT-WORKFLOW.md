# Hermes Agent Niggvis Crypto — Git Workflow

> Praca z gitem na 3 maszynach: WSL-PC (dev), macbook (Copilot), VPS (produkcja).
> Identyczny wzorzec jak w hermes-agent.

---

## Architektura repozytoriów

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

| Maszyna | Rola | Remotes | Operacje |
|---------|------|---------|----------|
| **WSL-PC** | Development + runtime | `origin` + `upstream` | push, pull, merge upstream |
| **macbook** | Praca z Copilotem | `origin` | push, pull |
| **VPS** | Produkcja 24/7 | `origin` | pull only |

---

## Konfiguracja per maszyna

### WSL-PC (dev)

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git remote -v
```

Powinno wyglądać tak:
```
origin    git@github.com:dicross/hermes-agent-niggvis-crypto.git (fetch)
origin    git@github.com:dicross/hermes-agent-niggvis-crypto.git (push)
upstream  https://github.com/NousResearch/hermes-agent.git (fetch)
upstream  https://github.com/NousResearch/hermes-agent.git (push)
```

Jeśli brakuje upstream:
```bash
git remote add upstream https://github.com/NousResearch/hermes-agent.git
```

Jeśli origin wskazuje na publiczne repo:
```bash
git remote set-url origin git@github.com:dicross/hermes-agent-niggvis-crypto.git
```

### macbook (Copilot)

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git remote -v
# origin  git@github.com:dicross/hermes-agent-niggvis-crypto.git
```

### VPS (setup od zera)

```bash
# 1. Klucz SSH (jeśli nie masz)
ssh-keygen -t ed25519 -C "vps-niggvis-crypto"
cat ~/.ssh/id_ed25519.pub
# → Dodaj do GitHub: Settings → SSH and GPG keys → New SSH key
 
# 2. Klonowanie
cd ~/projects
git clone git@github.com:dicross/hermes-agent-niggvis-crypto.git
cd hermes-agent-niggvis-crypto
 
# 3. (Opcjonalnie) Dodaj upstream
git remote add upstream https://github.com/NousResearch/hermes-agent.git
 
# 4. Dalej wg #INSTALLATION.md
```

---

## Codzienne operacje

### Zanim zaczniesz pracę — pull

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git pull origin main
```

### Po zakończeniu pracy — commit & push

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git add -A
git status                     # Sprawdź co się zmieni
git commit -m "opis zmian"
git push origin main
```

### Na innej maszynie — synchronizacja

```bash
cd ~/projects/hermes-agent-niggvis-crypto
git pull origin main
 
# Jeśli SOUL.md lub MEMORY.md się zmienił — skopiuj do ~/.hermes/
cp custom-files/SOUL.md ~/.hermes/SOUL.md
cp custom-files/MEMORY.md ~/.hermes/memories/MEMORY.md
 
# Jeśli pyproject.toml się zmienił — reinstall
uv pip install -e ".[all]"
```

---

## Merge z upstream (TYLKO WSL)

Gdy wyjdzie nowa wersja Hermes Agent:

```bash
cd ~/projects/hermes-agent-niggvis-crypto
 
# 1. Zapisz lokalne zmiany
git stash
 
# 2. Pobierz z upstream
git fetch upstream
 
# 3. Merge upstream/main do naszego main
git merge upstream/main
 
# 4. Rozwiąż konflikty (jeśli są — zazwyczaj w custom-files/ nie będzie)
# git mergetool
 
# 5. Przywróć stash
git stash pop
 
# 6. Test
hermes doctor
hermes --version
 
# 7. Push
git push origin main
```

> **UWAGA:** Po merge z upstream upewnij się, że `hermes doctor` działa.
> Jeśli pyproject.toml się zmienił, reinstaluj: `uv pip install -e ".[all]"`

---

## Co commitujemy, a czego nie

### ✅ Commituj (`custom-files/`)

- `custom-files/docs/` — dokumentacja
- `custom-files/config.example.yaml` — szablon config
- `custom-files/.env.example` — szablon kluczy (BEZ rzeczywistych kluczy!)
- `custom-files/SOUL.md` — persona agenta
- `custom-files/MEMORY.md` — bazowa wiedza crypto

### ❌ NIE commituj

- `~/.hermes/` — katalog per maszyna (sekrety, sesje, logi)
- `venv/` — środowisko Python
- `.env` z prawdziwymi kluczami
- `__pycache__/`, `*.pyc`
- Logi, sesje, cache

`.gitignore` w głównym katalogu powinien ignorować `venv/` i `__pycache__/`.
Reszta (upstream code) jest commitowana jako base Hermes Agent.

---

## Rozwiązywanie problemów

### Merge conflict w custom-files/

```bash
# Otwórz plik z konfliktem
# Rozwiąż ręcznie (zachowaj nasze zmiany)
git add <resolved-file>
git commit
```

### "Permission denied" na push

```bash
# Sprawdź klucz SSH
ssh -T git@github.com
# Powinno wyświetlić: Hi dicross! You've successfully authenticated...
 
# Jeśli nie — dodaj klucz:
ssh-keygen -t ed25519 -C "twoj-email"
cat ~/.ssh/id_ed25519.pub
# → Dodaj do GitHub Settings → SSH keys
```

### Chcę cofnąć merge z upstream

```bash
# OSTROŻNIE — tylko jeśli nie pushowałeś
git merge --abort         # W trakcie merge
git reset --hard HEAD~1   # Po merge (KASUJE commit)
```

---
