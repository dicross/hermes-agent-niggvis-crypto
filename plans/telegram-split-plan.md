# Plan: Rozdzielenie powiadomień Telegram na osobne czaty

## Kontekst
Obecnie system Hermes korzysta z jednego identyfikatora czatu (`chat_id`) dla Telegrama`), co powoduje, że wszystkie komunikaty (interakcje z Agentem, powiadomienia z zadań Cron oraz alerty z Guardiana) trafiają do jednego miejsca. 

Celem jest rozdzielenie tych strumieni na trzy osobne cele:
1. **Agent (Główny czat)**: Komunikacja dwustronna z Hermesem.
2. **Cron (Grupa)**: Powiadomienia z harmonogramu zadań.
3. **Guardian (Grupa)**: Alerty krytyczne (SL/TP, Kill Switch, Tier Triggers).

## Konfiguracja ID
- **Agent**: `5465931080` (Użytkownik)
- **Cron**: `-5137217844` (Grupa)
- **Guardian**: `-5101540743` (Grupa)

---

## Plan Implementacji

### Krok 0: Zabezpieczenie i wersjonowanie (Custom Files)
Aby zapewnić łatwą konfigurację na nowych maszynach i bezpieczeństwo zmian, stosujemy następujący proces dla każdego modyfikowanego pliku z rdzenia rdzenia:
1. **Kopia zapasowa**: Kopiujemy oryginalny plik z katalogu projektu do `/home/niggvis/projects/hermes-agent-niggvis-crypto/custom-files/` (zachowując strukturę katalogów).
2. **Edycja**: Wprowadzamy zmiany w pliku znajdującym się w `custom-files`.
3. **Automatyzacja**: Aktualizujemy skrypt `install-skills.sh`, aby podczas instalacji nadpisywał oryginalne pliki w `~/.hermes/` wersjami z `custom-files`.
4. **Wdrożenie**: Uruchamiamy `install-skills.sh` w celu zastosowania zmian w środowisku.

### Krok 1: Aktualizacja Konfiguracji
- **`~/.hermes/gateway.json`**: 
    - Zmiana struktury `telegram` z pojedynczego `chat_id` na obiekt `chats` zawierający mapowanie: `agent`, `cron`, `guardian`.
- **`~/.hermes/.env`**: 
    - Dodanie zmiennych środowiskowych dla nowych ID grup, aby zapewnić szybki dostęp i łatwą zmianę bez edycji JSON.

### Krok 2: Modyfikacja Warstwy Gateway (`TelegramAdapter`)
- **`gateway/platforms/telegram.py`**:
    - Aktualizacja metody `send()` tak, aby opcjonalnie przyjmowała parametr `chat_type` (np. `agent`, `cron`, `guardian`).
    - Implementacja logiki wyboru `chat_id` na podstawie `chat_type`. Jeśli typ nie jest podany, domyślnie używany będzie czat `agent`.
    - Zapewnienie kompatybilności wstecznej dla wywołań, które przekazują `chat_id` jawnie.

### Krok 3: Przekierowanie Powiadomień Cron
- **`tools/send_message_tool.py`**:
    - Modyfikacja funkcji `_get_cron_auto_delivery_target()` lub logiki wysyłki dla cronów, aby wymuszała użycie `chat_type='cron'`.
- **`~/.hermes/cron/jobs.json`**:
    - Weryfikacja, czy obecne wpisy `"deliver": "telegram"` są poprawnie interpretowane przez nowy mechanizm routingu.

### Krok 4: Przekierowanie Alertów Guardiana
- **Analiza kodu Guardiana**:
    - Znalezienie miejsca, w którym Guardian wywołuje API Telegrama.
    - Zmiana wywołania tak, aby korzystało z `chat_type='guardian'`.

### Krok 5: Testowanie i Weryfikacja
- Test wysłania wiadomości przez Agenta $\rightarrow$ Czat Agent.
- Ręczne uruchomienie zadania Cron $\rightarrow$ Grupa Cron.
- Wywołanie alertu Guardiana (np. symulacja SL) $\rightarrow$ Grupa Guardian.

---

## Ryzyka i Uwagi
- **ID Agenta**: Należy upewnić się, że używamy `5465931080` (User ID), a nie tokenu bota.
- **Uprawnienia**: Bot musi być administratorem w grupach (potwierdzone przez użytkownika).
- **Kompatybilność**: Zmiana w `gateway.json` może wymagać aktualizacji narzędzia `hermes gateway setup`, jeśli jest ono często używane.
