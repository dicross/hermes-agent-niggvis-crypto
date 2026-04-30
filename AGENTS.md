# AGENTS.md

This file provides guidance to agents when working with code in this repository.

## Key Commands
- Run tests (hermetic CI environment): `scripts/run_tests.sh` [test_path]
- Run specific test: `scripts/run_tests.sh tests/agent/test_foo.py::test_x`
- TUI development (ui-tui): `npm run dev` (watch), `npm run lint`, `npm run fmt`, `npm test`
- Deploy skills/config: `bash custom-files/install-skills.sh --skills` (from project root)
- Update cron jobs: `python3 custom-files/setup-cron.py`
- Start agent CLI: `hermes`
- Start messaging gateway: `hermes gateway start`
- Configure agent: `hermes config set <key> <value>`
- Update agent: `hermes update` (or use package manager for managed installs)

## Code Style & Patterns
- Python: Use `get_hermes_home()` from `hermes_constants` for all HERMES_HOME paths (never hardcode `~/.hermes`)
- User-facing paths: Use `display_hermes_home()` for profile-aware paths
- TUI: Follow TypeScript/React (Ink) patterns in `ui-tui/` directory
- New tools: Create `tools/your_tool.py` with `registry.register()` and add to `toolsets.py`
- Configuration: Add to `DEFAULT_CONFIG` in `hermes_cli/config.py` and bump `_config_version`
- Environment variables: Add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` with metadata
- Skins: Pure YAML in `~/.hermes/skins/`; built-in skins in `_BUILTIN_SKINS` (`skin_engine.py`)
- Prompt caching: Never alter context mid-conversation, change toolsets, or reload memories
- Working directory: CLI uses `.`; messaging uses `MESSAGING_CWD` (from `terminal.cwd` in config)
- Background notifications: Control via `display.background_process_notifications` in config
- Agent loop: Synchronous in `run_conversation()` (`run_agent.py`)
- Tool handlers: Must return JSON string; auto-discovered from `tools/*.py`
- Agent-level tools: Intercepted by `run_agent.py` before `handle_function_call()` (see `todo_tool.py`)
- Plugins: Skills, context engines, etc. loaded from `~/.hermes/plugins/` or built-in

# Niggvis — Crypto Trading Agent on Solana (Hermes Agent fork)
 
## Project Overview
 
This is a private fork of [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent)
customized as an autonomous crypto trading agent on Solana. Agent name: **Niggvis**.
Owner: **Damian**. Repo: `dicross/hermes-agent-niggvis-crypto`.
 
The agent runs 24/7 on WSL, executes real on-chain trades via Jupiter API,
monitors positions with an adaptive guardian, and communicates through Telegram.
 
## Repository Structure
 
```
custom-files/                          # ALL customization lives here
├── SOUL.md                            # Agent persona (crypto trader personality)
├── MEMORY.md                          # Agent knowledge base (tools, APIs, rules)
├── trading-config.yaml                # Central trading config (→ ~/.hermes/memories/)
├── setup-cron.py                      # Cron job definitions (token-scan, reports, evaluator)
├── install-skills.sh                  # Deploys skills + config to ~/.hermes/
├── docs/
│   ├── #CHEATSHEET.md                 # CLI commands, skills, cron reference
│   └── #INSTALLATION.md              # Full setup guide (repos, remotes, deploy)
└── skills/
    ├── trade-executor/scripts/
    │   ├── executor.py                # Buy/sell/portfolio/config-propose (main entry)
    │   ├── guardian.py                # Price monitor, tiered exits, TUI dashboard
    │   └── jupiter_swap.py            # Low-level Jupiter on-chain swaps
    ├── crypto-scanner/scripts/
    │   └── scanner.py                 # DEXScreener trending/scan/search/metas
    ├── onchain-analyzer/scripts/
    │   └── analyzer.py                # Safety score, holders, liquidity analysis
    ├── risk-manager/scripts/
    │   └── risk_manager.py            # Risk checks, daily P&L, kill switch
    └── trade-journal/scripts/
        ├── journal.py                 # Trade log: show/stats/export/close
        └── learning.py                # Self-learning: patterns from trade history
```
 
## Runtime File Locations (on WSL at ~/.hermes/)
 
| File | Path | Purpose |
|------|------|---------|
| Trading config | `~/.hermes/memories/trading-config.yaml` | All risk/sizing/filter params |
| Trade journal | `~/.hermes/memories/trade-journal.json` | Trade history (JSON, not .md!) |
| Trade learnings | `~/.hermes/memories/trade-learnings.json` | Patterns from learning.py |
| Risk state | `~/.hermes/memories/risk-state.json` | Kill switch, daily P&L tracking |
| Config proposals | `~/.hermes/memories/config-proposals.json` | Pending config changes |
| Wallet keypair | `~/.hermes/secrets/trading-wallet.json` | Solana keypair (NEVER commit) |
| Gateway config | `~/.hermes/gateway.json` | Telegram bot token + chat_id |
| Cron jobs | `~/.hermes/cron/jobs.json` | Scheduled job definitions |
| Pending evals | `~/.hermes/cron/pending-evaluations/<id>.json` | Per-trade LLM eval requests |
| Guardian log | `~/.hermes/cron/guardian.log` | Guardian alerts log |
| Guardian lock | `~/.hermes/cron/.guardian.lock` | Prevents duplicate guardian |
| Buy lock | `~/.hermes/cron/.executor-buy.lock` | Prevents duplicate buys |
| Skills dir | `~/.hermes/skills/` | Deployed skill scripts |
| SOUL persona | `~/.hermes/SOUL.md` | Agent personality |
| MEMORY | `~/.hermes/memories/MEMORY.md` | Agent knowledge base |
 
## Architecture & Data Flow
 
```
┌─────────────────────────────────────────────────────────────┐
│                    HERMES CRON SCHEDULER                     │
│  token-scan (15m) │ position-check (30m) │ reports (daily)  │
│  position-evaluator (paused, triggered by guardian)          │
└────────┬──────────┬──────────────────────┬──────────────────┘
         │          │                      │
         ▼          ▼                      ▼
┌────────────┐ ┌──────────┐        ┌──────────────┐
│ executor.py│ │scanner.py│        │ learning.py  │
│ buy/sell   │ │ trending │        │ patterns     │
└─────┬──────┘ └──────────┘        └──────────────┘
      │
      ├── analyzer.py analyze (safety 0-100)
      ├── risk_manager.py check (limits, P&L, dups)
      ├── jupiter_swap.py buy/sell (on-chain)
      └── journal.py (log trade)
 
┌─────────────────────────────────────────────────────────────┐
│              GUARDIAN (standalone, no LLM)                    │
│  Runs in tmux, adaptive interval (idle 30s / active 5s /    │
│  hot 1s). Batch price fetch rotating DEXScreener ↔ Jupiter. │
│                                                              │
│  Each tick:                                                  │
│  1. Batch fetch prices (all open positions, 1 API call)     │
│  2. For each position:                                      │
│     a. Check tiered exits (ratchet SL up, trigger eval)     │
│     b. Check evaluation timeout → apply default strategy     │
│     c. Execute exit_strategy (trailing/hold/partial/hard_tp) │
│     d. Check stop-loss (effective SL = max of all floors)   │
│  3. Wallet sync (every 5m, if enabled)                      │
│  4. Render TUI dashboard                                    │
│  5. Compute adaptive interval for next tick                  │
│                                                              │
│  Triggers: position-evaluator cron job on tier crossing      │
│  Sends: Telegram alerts for SL, TP, trailing, tier, evals   │
└─────────────────────────────────────────────────────────────┘
```
 
## Tiered Exit System (replaces flat trailing stops)
 
Config in `trading-config.yaml` → `risk.exit_tiers`:
 
```yaml
exit_tiers:
  - trigger_pct: 50       # At +50% profit
    action: move_sl        # Mechanically move SL floor
    new_sl_pct: 0          # to break-even (0% = entry price)
  - trigger_pct: 100      # At +100% profit (2x)
    action: evaluate       # Move SL + trigger LLM evaluator
    new_sl_pct: 20         # SL floor at +20% profit minimum
 
default_exit_strategy:     # If evaluator fails/times out (5 min)
  type: trailing
  trailing_pct: 25
  trailing_from_pct: 200
```
 
LLM evaluator writes one of 4 strategies to journal:
- **hold** — keep position, set review_at_pct for re-evaluation
- **trailing** — trailing stop (trailing_pct from trailing_from_pct)
- **partial_sell** — sell X%, hold rest with new strategy
- **hard_tp** — sell 100% at specific P&L target
 
Guardian executes strategies mechanically. Evaluator only decides.
Concurrent evaluations supported: per-trade files in `pending-evaluations/`.
 
## Dump Guard (executor.py buy flow)
 
Three layers of protection before buying:
1. **Classic drop**: blocks if h24 or h6 ≤ -max_24h_drop_pct (currently 60%)
2. **Post-pump dump**: calculates implied ATH drop from h24/h6 ratio
   - Example: h24=+3456%, h6=+60% → drop from peak ~95% → BLOCKED
3. **Active crash**: blocks if h1 ≤ -(max_24h_drop_pct / 2), i.e. -30%
 
## Multi-Provider Price Rotation (guardian.py)
 
Guardian rotates price providers each tick to avoid rate limits:
- Tick 1: DEXScreener (300 RPM, provides MC + liquidity)
- Tick 2: Jupiter Price API (600 RPM, faster, no MC/liquidity)
- Tick 3: DEXScreener... (cycle)
- On failure: automatic fallback to the other provider
- HTTP timeout: 5 seconds (prevents stale-price hangs)
 
## Key Commands (all use full paths on WSL)
 
```bash
# Trading
python3 ~/.hermes/skills/trade-executor/scripts/executor.py buy --token <ADDR> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <N> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py sell --id <N> --pct 50 --reason "partial"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py portfolio
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-propose --key <K> --value <V> --reason "why"
python3 ~/.hermes/skills/trade-executor/scripts/executor.py config-apply --index <N>
 
# Guardian (run in tmux)
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --dry-run
 
# Scanning & Analysis
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py trending --limit 10
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py scan --min-liq 10000
python3 ~/.hermes/skills/crypto-scanner/scripts/scanner.py metas
python3 ~/.hermes/skills/onchain-analyzer/scripts/analyzer.py analyze <ADDR> --full
 
# Journal & Learning
python3 ~/.hermes/skills/trade-journal/scripts/journal.py show --status open
python3 ~/.hermes/skills/trade-journal/scripts/journal.py stats --days 7
python3 ~/.hermes/skills/trade-journal/scripts/learning.py update
python3 ~/.hermes/skills/trade-journal/scripts/learning.py patterns
 
# Risk
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py status
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py kill --reason "why"
python3 ~/.hermes/skills/risk-manager/scripts/risk_manager.py resume
 
# Jupiter (low-level)
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py wallet
python3 ~/.hermes/skills/trade-executor/scripts/jupiter_swap.py balance --token <ADDR>
```
 
## Current Trading Config (key values)
 
| Parameter | Value | Location |
|-----------|-------|----------|
| Mode | `real` | root |
| Position size | 5% of wallet | `position_sizing.position_pct` |
| Min trade | 0.015 SOL | `position_sizing.min_trade_sol` |
| Max trade | 0.5 SOL | `position_sizing.max_trade_sol` |
| Max positions | 5 | `position_sizing.max_positions` |
| Stop loss | -30% | `risk.stop_loss_pct` |
| Tier 1 | +50% → SL to break-even | `risk.exit_tiers[0]` |
| Tier 2 | +100% → SL +20% + LLM eval | `risk.exit_tiers[1]` |
| Default strategy | trailing 25% from 200% | `risk.default_exit_strategy` |
| Eval timeout | 5 min | `risk.evaluation_timeout_minutes` |
| Daily loss limit | -20% | `risk.daily_loss_limit_pct` |
| Max 24h drop | 60% | `risk.max_24h_drop_pct` |
| Min safety score | 60/100 | `filters.min_safety_score` |
| Min liquidity | $15,000 | `filters.min_liquidity_usd` |
| Slippage | 500 bps (5%) | `jupiter.slippage_bps` |
| Guardian idle | 30s | `guardian.interval_idle` |
| Guardian active | 5s | `guardian.interval_active` |
| Guardian hot | 1s | `guardian.interval_hot` |
| Wallet sync | disabled | `guardian.wallet_sync_enabled` |
| Rebuy cooldown | 240 min | `risk.rebuy_cooldown_minutes` |
 
## Cron Jobs
 
| Job | Schedule | Deliver | Purpose |
|-----|----------|---------|---------|
| `token-scan` | every 15m | telegram | Scan trending, auto-buy if passes filters |
| `position-check` | every 30m | telegram | Backup SL/TP check (guardian is primary) |
| `trend-analysis` | every 4h | local | Market trend analysis, category tracking |
| `morning-report` | 08:00 UTC | telegram | Portfolio + risk status + plan |
| `daily-summary` | 23:00 UTC | telegram | Recap + learning.py + config-propose |
| `weekly-recap` | Sun 10:00 | telegram | Weekly stats + patterns + config-propose |
| `position-evaluator` | paused | telegram | LLM evaluator (triggered by guardian) |
 
## Buy Pipeline (executor.py buy)
 
```
1. Position sizing (auto from wallet balance × position_pct)
2. Reserve guard (refuse if wallet drops below min_wallet_balance)
3. Fetch price from DEXScreener (_get_token_info)
4. Dump guard — 3 checks:
   a. Classic drop: min(h24, h6) ≤ -60%
   b. Post-pump dump: implied peak-to-current drop ≥ 60%
   c. Active crash: h1 ≤ -30%
5. Safety check — analyzer.py analyze (full 0-100 score, NOT safety which is 45 max)
6. Risk check — risk_manager.py check (limits, daily P&L, cooldown, duplicates)
7. Jupiter swap (on-chain, irreversible in real mode)
8. Log to trade-journal.json
```
 
IMPORTANT: Do NOT run `analyzer.py safety` manually before buy — it gives max 45/45
(contract-only) which always gets blocked by min_safety_score: 60. Use `executor.py buy`
which internally runs the full `analyze` command (0-100 score).
 
## API Endpoints Used
 
| API | Base URL | Rate Limit | Used For |
|-----|----------|------------|----------|
| DEXScreener | `api.dexscreener.com` | 300 RPM | Token data, batch prices, trending |
| Jupiter Swap | `lite-api.jup.ag/swap/v1` | — | On-chain swaps |
| Jupiter Price | `api.jup.ag/price/v2` | 600 RPM | Batch price fetch (rotation) |
| Solana RPC | `api.mainnet-beta.solana.com` | rate limited | Balance, token accounts |
| Birdeye | `public-api.birdeye.so` | public | Token analytics (optional) |
 
DEXScreener batch endpoint: `/tokens/v1/solana/{addr1,addr2,...}` (comma-separated)
Jupiter Price batch: `/price/v2?ids=addr1,addr2,...`
Always add `User-Agent` header — Python urllib gets 403 without it.
 
## Environment Details
 
| Detail | Value |
|--------|-------|
| Platform | WSL (Ubuntu) on Windows |
| User | niggvis |
| Python venv | `~/projects/hermes-agent-niggvis-crypto/.venv/bin/python3` |
| SSH passphrase | `zorba-mac` |
| Wallet address | `HKbB4dPBAkdKgB2j2ZcKoand1q6WpCeBHf1MTk4TU89q` |
| Blockchain | Solana mainnet |
| Model | NVIDIA NIM `qwen/qwen3-next-80b-a3b-instruct` (40 RPM limit!) |
| Timezone | Europe/Warsaw |
| Language | Polish (crypto terms in English) |
| Git remote | `git@github.com:dicross/hermes-agent-niggvis-crypto.git` |
 
## Critical Rules
 
### Config Changes
- NEVER edit trading-config.yaml directly — always use `config-propose` → Telegram → Damian approves → `config-apply`
- NEVER edit Python scripts in `~/.hermes/skills/` at runtime
- Config changes require human approval via Telegram
 
### Trading Safety
- NEVER buy without on-chain analysis passing (safety ≥ 60)
- NEVER exceed max_trade_sol or max_positions
- NEVER ignore kill switch or daily loss limit
- Mint authority active → DO NOT BUY
- Freeze authority active → DO NOT BUY
- LP unlocked → DO NOT BUY
- Top holder > 15% → DO NOT BUY
 
### Guardian
- Runs in tmux session, must survive SSH disconnect
- File lock prevents duplicate instances
- No LLM calls — pure API + math for speed
- Tiered SL only ratchets UP, never down
- Trailing stop checks PEAK P&L (not current) to decide if activated
 
## Deployment
 
```bash
# On WSL — deploy changes from repo to ~/.hermes/
cd ~/projects/hermes-agent-niggvis-crypto
git pull
bash custom-files/install-skills.sh --skills   # Deploy skills + config
python3 custom-files/setup-cron.py              # Update cron jobs
 
# Restart guardian after code changes
# In tmux: Ctrl+C, then:
python3 ~/.hermes/skills/trade-executor/scripts/guardian.py --watch
```
 
## Journal Reset (fresh start)
 
```bash
echo '{"trades": [], "next_id": 1}' > ~/.hermes/memories/trade-journal.json
rm -f ~/.hermes/memories/trade-learnings.json
rm -f ~/.hermes/cron/pending-evaluations/*.json
rm -f ~/.hermes/cron/.guardian.lock
rm -f ~/.hermes/cron/.executor-buy.lock
# Do NOT touch: trading-config.yaml, MEMORY.md, secrets/, risk-state.json
```
 
## Trade Journal Format
 
```json
{
  "trades": [
    {
      "id": 1,
      "status": "open|closed",
      "token": "SYMBOL",
      "address": "mint_address",
      "entry_price": 0.001234,
      "amount_sol": 0.015,
      "entry_time": "2026-04-22T12:00:00+02:00",
      "exit_price": null,
      "exit_time": null,
      "exit_reason": null,
      "pnl_pct": null,
      "pnl_sol": null,
      "reason": "why bought",
      "tiers_triggered": [0],
      "effective_sl_pct": 0,
      "peak_pnl_pct": 65.4,
      "evaluation_pending": false,
      "evaluation_requested_at": null,
      "exit_strategy": {
        "type": "trailing",
        "trailing_pct": 25,
        "trailing_from_pct": 200,
        "sl_pct": 20,
        "reason": "LLM evaluation reason"
      }
    }
  ],
  "next_id": 2
}
```


# Hermes Agent - Development Guide

Instructions for AI coding assistants and developers working on the hermes-agent codebase.

## Development Environment

```bash
source venv/bin/activate  # ALWAYS activate before running Python
```

## Project Structure

```
hermes-agent/
├── run_agent.py          # AIAgent class — core conversation loop
├── model_tools.py        # Tool orchestration, discover_builtin_tools(), handle_function_call()
├── toolsets.py           # Toolset definitions, _HERMES_CORE_TOOLS list
├── cli.py                # HermesCLI class — interactive CLI orchestrator
├── hermes_state.py       # SessionDB — SQLite session store (FTS5 search)
├── agent/                # Agent internals
│   ├── prompt_builder.py     # System prompt assembly
│   ├── context_compressor.py # Auto context compression
│   ├── prompt_caching.py     # Anthropic prompt caching
│   ├── auxiliary_client.py   # Auxiliary LLM client (vision, summarization)
│   ├── model_metadata.py     # Model context lengths, token estimation
│   ├── models_dev.py         # models.dev registry integration (provider-aware context)
│   ├── display.py            # KawaiiSpinner, tool preview formatting
│   ├── skill_commands.py     # Skill slash commands (shared CLI/gateway)
│   └── trajectory.py         # Trajectory saving helpers
├── hermes_cli/           # CLI subcommands and setup
│   ├── main.py           # Entry point — all `hermes` subcommands
│   ├── config.py         # DEFAULT_CONFIG, OPTIONAL_ENV_VARS, migration
│   ├── commands.py       # Slash command definitions + SlashCommandCompleter
│   ├── callbacks.py      # Terminal callbacks (clarify, sudo, approval)
│   ├── setup.py          # Interactive setup wizard
│   ├── skin_engine.py    # Skin/theme engine — CLI visual customization
│   ├── skills_config.py  # `hermes skills` — enable/disable skills per platform
│   ├── tools_config.py   # `hermes tools` — enable/disable tools per platform
│   ├── skills_hub.py     # `/skills` slash command (search, browse, install)
│   ├── models.py         # Model catalog, provider model lists
│   ├── model_switch.py   # Shared /model switch pipeline (CLI + gateway)
│   └── auth.py           # Provider credential resolution
├── tools/                # Tool implementations (one file per tool)
│   ├── registry.py       # Central tool registry (schemas, handlers, dispatch)
│   ├── approval.py       # Dangerous command detection
│   ├── terminal_tool.py  # Terminal orchestration
│   ├── process_registry.py # Background process management
│   ├── file_tools.py     # File read/write/search/patch
│   ├── web_tools.py      # Web search/extract (Parallel + Firecrawl)
│   ├── browser_tool.py   # Browserbase browser automation
│   ├── code_execution_tool.py # execute_code sandbox
│   ├── delegate_tool.py  # Subagent delegation
│   ├── mcp_tool.py       # MCP client (~1050 lines)
│   └── environments/     # Terminal backends (local, docker, ssh, modal, daytona, singularity)
├── gateway/              # Messaging platform gateway
│   ├── run.py            # Main loop, slash commands, message dispatch
│   ├── session.py        # SessionStore — conversation persistence
│   └── platforms/        # Adapters: telegram, discord, slack, whatsapp, homeassistant, signal, qqbot
├── ui-tui/               # Ink (React) terminal UI — `hermes --tui`
│   ├── src/entry.tsx        # TTY gate + render()
│   ├── src/app.tsx          # Main state machine and UI
│   ├── src/gatewayClient.ts # Child process + JSON-RPC bridge
│   ├── src/app/             # Decomposed app logic (event handler, slash handler, stores, hooks)
│   ├── src/components/      # Ink components (branding, markdown, prompts, pickers, etc.)
│   ├── src/hooks/           # useCompletion, useInputHistory, useQueue, useVirtualHistory
│   └── src/lib/             # Pure helpers (history, osc52, text, rpc, messages)
├── tui_gateway/          # Python JSON-RPC backend for the TUI
│   ├── entry.py             # stdio entrypoint
│   ├── server.py            # RPC handlers and session logic
│   ├── render.py            # Optional rich/ANSI bridge
│   └── slash_worker.py      # Persistent HermesCLI subprocess for slash commands
├── acp_adapter/          # ACP server (VS Code / Zed / JetBrains integration)
├── cron/                 # Scheduler (jobs.py, scheduler.py)
├── environments/         # RL training environments (Atropos)
├── tests/                # Pytest suite (~3000 tests)
└── batch_runner.py       # Parallel batch processing
```

**User config:** `~/.hermes/config.yaml` (settings), `~/.hermes/.env` (API keys)

## File Dependency Chain

```
tools/registry.py  (no deps — imported by all tool files)
       ↑
tools/*.py  (each calls registry.register() at import time)
       ↑
model_tools.py  (imports tools/registry + triggers tool discovery)
       ↑
run_agent.py, cli.py, batch_runner.py, environments/
```

---

## AIAgent Class (run_agent.py)

```python
class AIAgent:
    def __init__(self,
        model: str = "anthropic/claude-opus-4.6",
        max_iterations: int = 90,
        enabled_toolsets: list = None,
        disabled_toolsets: list = None,
        quiet_mode: bool = False,
        save_trajectories: bool = False,
        platform: str = None,           # "cli", "telegram", etc.
        session_id: str = None,
        skip_context_files: bool = False,
        skip_memory: bool = False,
        # ... plus provider, api_mode, callbacks, routing params
    ): ...

    def chat(self, message: str) -> str:
        """Simple interface — returns final response string."""

    def run_conversation(self, user_message: str, system_message: str = None,
                         conversation_history: list = None, task_id: str = None) -> dict:
        """Full interface — returns dict with final_response + messages."""
```

### Agent Loop

The core loop is inside `run_conversation()` — entirely synchronous:

```python
while api_call_count < self.max_iterations and self.iteration_budget.remaining > 0:
    response = client.chat.completions.create(model=model, messages=messages, tools=tool_schemas)
    if response.tool_calls:
        for tool_call in response.tool_calls:
            result = handle_function_call(tool_call.name, tool_call.args, task_id)
            messages.append(tool_result_message(result))
        api_call_count += 1
    else:
        return response.content
```

Messages follow OpenAI format: `{"role": "system/user/assistant/tool", ...}`. Reasoning content is stored in `assistant_msg["reasoning"]`.

---

## CLI Architecture (cli.py)

- **Rich** for banner/panels, **prompt_toolkit** for input with autocomplete
- **KawaiiSpinner** (`agent/display.py`) — animated faces during API calls, `┊` activity feed for tool results
- `load_cli_config()` in cli.py merges hardcoded defaults + user config YAML
- **Skin engine** (`hermes_cli/skin_engine.py`) — data-driven CLI theming; initialized from `display.skin` config key at startup; skins customize banner colors, spinner faces/verbs/wings, tool prefix, response box, branding text
- `process_command()` is a method on `HermesCLI` — dispatches on canonical command name resolved via `resolve_command()` from the central registry
- Skill slash commands: `agent/skill_commands.py` scans `~/.hermes/skills/`, injects as **user message** (not system prompt) to preserve prompt caching

### Slash Command Registry (`hermes_cli/commands.py`)

All slash commands are defined in a central `COMMAND_REGISTRY` list of `CommandDef` objects. Every downstream consumer derives from this registry automatically:

- **CLI** — `process_command()` resolves aliases via `resolve_command()`, dispatches on canonical name
- **Gateway** — `GATEWAY_KNOWN_COMMANDS` frozenset for hook emission, `resolve_command()` for dispatch
- **Gateway help** — `gateway_help_lines()` generates `/help` output
- **Telegram** — `telegram_bot_commands()` generates the BotCommand menu
- **Slack** — `slack_subcommand_map()` generates `/hermes` subcommand routing
- **Autocomplete** — `COMMANDS` flat dict feeds `SlashCommandCompleter`
- **CLI help** — `COMMANDS_BY_CATEGORY` dict feeds `show_help()`

### Adding a Slash Command

1. Add a `CommandDef` entry to `COMMAND_REGISTRY` in `hermes_cli/commands.py`:
```python
CommandDef("mycommand", "Description of what it does", "Session",
           aliases=("mc",), args_hint="[arg]"),
```
2. Add handler in `HermesCLI.process_command()` in `cli.py`:
```python
elif canonical == "mycommand":
    self._handle_mycommand(cmd_original)
```
3. If the command is available in the gateway, add a handler in `gateway/run.py`:
```python
if canonical == "mycommand":
    return await self._handle_mycommand(event)
```
4. For persistent settings, use `save_config_value()` in `cli.py`

**CommandDef fields:**
- `name` — canonical name without slash (e.g. `"background"`)
- `description` — human-readable description
- `category` — one of `"Session"`, `"Configuration"`, `"Tools & Skills"`, `"Info"`, `"Exit"`
- `aliases` — tuple of alternative names (e.g. `("bg",)`)
- `args_hint` — argument placeholder shown in help (e.g. `"<prompt>"`, `"[name]"`)
- `cli_only` — only available in the interactive CLI
- `gateway_only` — only available in messaging platforms
- `gateway_config_gate` — config dotpath (e.g. `"display.tool_progress_command"`); when set on a `cli_only` command, the command becomes available in the gateway if the config value is truthy. `GATEWAY_KNOWN_COMMANDS` always includes config-gated commands so the gateway can dispatch them; help/menus only show them when the gate is open.

**Adding an alias** requires only adding it to the `aliases` tuple on the existing `CommandDef`. No other file changes needed — dispatch, help text, Telegram menu, Slack mapping, and autocomplete all update automatically.

---

## TUI Architecture (ui-tui + tui_gateway)

The TUI is a full replacement for the classic (prompt_toolkit) CLI, activated via `hermes --tui` or `HERMES_TUI=1`.

### Process Model

```
hermes --tui
  └─ Node (Ink)  ──stdio JSON-RPC──  Python (tui_gateway)
       │                                  └─ AIAgent + tools + sessions
       └─ renders transcript, composer, prompts, activity
```

TypeScript owns the screen. Python owns sessions, tools, model calls, and slash command logic.

### Transport

Newline-delimited JSON-RPC over stdio. Requests from Ink, events from Python. See `tui_gateway/server.py` for the full method/event catalog.

### Key Surfaces

| Surface | Ink component | Gateway method |
|---------|---------------|----------------|
| Chat streaming | `app.tsx` + `messageLine.tsx` | `prompt.submit` → `message.delta/complete` |
| Tool activity | `thinking.tsx` | `tool.start/progress/complete` |
| Approvals | `prompts.tsx` | `approval.respond` ← `approval.request` |
| Clarify/sudo/secret | `prompts.tsx`, `maskedPrompt.tsx` | `clarify/sudo/secret.respond` |
| Session picker | `sessionPicker.tsx` | `session.list/resume` |
| Slash commands | Local handler + fallthrough | `slash.exec` → `_SlashWorker`, `command.dispatch` |
| Completions | `useCompletion` hook | `complete.slash`, `complete.path` |
| Theming | `theme.ts` + `branding.tsx` | `gateway.ready` with skin data |

### Slash Command Flow

1. Built-in client commands (`/help`, `/quit`, `/clear`, `/resume`, `/copy`, `/paste`, etc.) handled locally in `app.tsx`
2. Everything else → `slash.exec` (runs in persistent `_SlashWorker` subprocess) → `command.dispatch` fallback

### Dev Commands

```bash
cd ui-tui
npm install       # first time
npm run dev       # watch mode (rebuilds hermes-ink + tsx --watch)
npm start         # production
npm run build     # full build (hermes-ink + tsc)
npm run type-check # typecheck only (tsc --noEmit)
npm run lint      # eslint
npm run fmt       # prettier
npm test          # vitest
```

---

## Adding New Tools

Requires changes in **2 files**:

**1. Create `tools/your_tool.py`:**
```python
import json, os
from tools.registry import registry

def check_requirements() -> bool:
    return bool(os.getenv("EXAMPLE_API_KEY"))

def example_tool(param: str, task_id: str = None) -> str:
    return json.dumps({"success": True, "data": "..."})

registry.register(
    name="example_tool",
    toolset="example",
    schema={"name": "example_tool", "description": "...", "parameters": {...}},
    handler=lambda args, **kw: example_tool(param=args.get("param", ""), task_id=kw.get("task_id")),
    check_fn=check_requirements,
    requires_env=["EXAMPLE_API_KEY"],
)
```

**2. Add to `toolsets.py`** — either `_HERMES_CORE_TOOLS` (all platforms) or a new toolset.

Auto-discovery: any `tools/*.py` file with a top-level `registry.register()` call is imported automatically — no manual import list to maintain.

The registry handles schema collection, dispatch, availability checking, and error wrapping. All handlers MUST return a JSON string.

**Path references in tool schemas**: If the schema description mentions file paths (e.g. default output directories), use `display_hermes_home()` to make them profile-aware. The schema is generated at import time, which is after `_apply_profile_override()` sets `HERMES_HOME`.

**State files**: If a tool stores persistent state (caches, logs, checkpoints), use `get_hermes_home()` for the base directory — never `Path.home() / ".hermes"`. This ensures each profile gets its own state.

**Agent-level tools** (todo, memory): intercepted by `run_agent.py` before `handle_function_call()`. See `todo_tool.py` for the pattern.

---

## Adding Configuration

### config.yaml options:
1. Add to `DEFAULT_CONFIG` in `hermes_cli/config.py`
2. Bump `_config_version` (currently 5) to trigger migration for existing users

### .env variables:
1. Add to `OPTIONAL_ENV_VARS` in `hermes_cli/config.py` with metadata:
```python
"NEW_API_KEY": {
    "description": "What it's for",
    "prompt": "Display name",
    "url": "https://...",
    "password": True,
    "category": "tool",  # provider, tool, messaging, setting
},
```

### Config loaders (two separate systems):

| Loader | Used by | Location |
|--------|---------|----------|
| `load_cli_config()` | CLI mode | `cli.py` |
| `load_config()` | `hermes tools`, `hermes setup` | `hermes_cli/config.py` |
| Direct YAML load | Gateway | `gateway/run.py` |

---

## Skin/Theme System

The skin engine (`hermes_cli/skin_engine.py`) provides data-driven CLI visual customization. Skins are **pure data** — no code changes needed to add a new skin.

### Architecture

```
hermes_cli/skin_engine.py    # SkinConfig dataclass, built-in skins, YAML loader
~/.hermes/skins/*.yaml       # User-installed custom skins (drop-in)
```

- `init_skin_from_config()` — called at CLI startup, reads `display.skin` from config
- `get_active_skin()` — returns cached `SkinConfig` for the current skin
- `set_active_skin(name)` — switches skin at runtime (used by `/skin` command)
- `load_skin(name)` — loads from user skins first, then built-ins, then falls back to default
- Missing skin values inherit from the `default` skin automatically

### What skins customize

| Element | Skin Key | Used By |
|---------|----------|---------|
| Banner panel border | `colors.banner_border` | `banner.py` |
| Banner panel title | `colors.banner_title` | `banner.py` |
| Banner section headers | `colors.banner_accent` | `banner.py` |
| Banner dim text | `colors.banner_dim` | `banner.py` |
| Banner body text | `colors.banner_text` | `banner.py` |
| Response box border | `colors.response_border` | `cli.py` |
| Spinner faces (waiting) | `spinner.waiting_faces` | `display.py` |
| Spinner faces (thinking) | `spinner.thinking_faces` | `display.py` |
| Spinner verbs | `spinner.thinking_verbs` | `display.py` |
| Spinner wings (optional) | `spinner.wings` | `display.py` |
| Tool output prefix | `tool_prefix` | `display.py` |
| Per-tool emojis | `tool_emojis` | `display.py` → `get_tool_emoji()` |
| Agent name | `branding.agent_name` | `banner.py`, `cli.py` |
| Welcome message | `branding.welcome` | `cli.py` |
| Response box label | `branding.response_label` | `cli.py` |
| Prompt symbol | `branding.prompt_symbol` | `cli.py` |

### Built-in skins

- `default` — Classic Hermes gold/kawaii (the current look)
- `ares` — Crimson/bronze war-god theme with custom spinner wings
- `mono` — Clean grayscale monochrome
- `slate` — Cool blue developer-focused theme

### Adding a built-in skin

Add to `_BUILTIN_SKINS` dict in `hermes_cli/skin_engine.py`:

```python
"mytheme": {
    "name": "mytheme",
    "description": "Short description",
    "colors": { ... },
    "spinner": { ... },
    "branding": { ... },
    "tool_prefix": "┊",
},
```

### User skins (YAML)

Users create `~/.hermes/skins/<name>.yaml`:

```yaml
name: cyberpunk
description: Neon-soaked terminal theme

colors:
  banner_border: "#FF00FF"
  banner_title: "#00FFFF"
  banner_accent: "#FF1493"

spinner:
  thinking_verbs: ["jacking in", "decrypting", "uploading"]
  wings:
    - ["⟨⚡", "⚡⟩"]

branding:
  agent_name: "Cyber Agent"
  response_label: " ⚡ Cyber "

tool_prefix: "▏"
```

Activate with `/skin cyberpunk` or `display.skin: cyberpunk` in config.yaml.

---

## Important Policies
### Prompt Caching Must Not Break

Hermes-Agent ensures caching remains valid throughout a conversation. **Do NOT implement changes that would:**
- Alter past context mid-conversation
- Change toolsets mid-conversation
- Reload memories or rebuild system prompts mid-conversation

Cache-breaking forces dramatically higher costs. The ONLY time we alter context is during context compression.

### Working Directory Behavior
- **CLI**: Uses current directory (`.` → `os.getcwd()`)
- **Messaging**: Uses `MESSAGING_CWD` env var (default: home directory)

### Background Process Notifications (Gateway)

When `terminal(background=true, notify_on_complete=true)` is used, the gateway runs a watcher that
detects process completion and triggers a new agent turn. Control verbosity of background process
messages with `display.background_process_notifications`
in config.yaml (or `HERMES_BACKGROUND_NOTIFICATIONS` env var):

- `all` — running-output updates + final message (default)
- `result` — only the final completion message
- `error` — only the final message when exit code != 0
- `off` — no watcher messages at all

---

## Profiles: Multi-Instance Support

Hermes supports **profiles** — multiple fully isolated instances, each with its own
`HERMES_HOME` directory (config, API keys, memory, sessions, skills, gateway, etc.).

The core mechanism: `_apply_profile_override()` in `hermes_cli/main.py` sets
`HERMES_HOME` before any module imports. All 119+ references to `get_hermes_home()`
automatically scope to the active profile.

### Rules for profile-safe code

1. **Use `get_hermes_home()` for all HERMES_HOME paths.** Import from `hermes_constants`.
   NEVER hardcode `~/.hermes` or `Path.home() / ".hermes"` in code that reads/writes state.
   ```python
   # GOOD
   from hermes_constants import get_hermes_home
   config_path = get_hermes_home() / "config.yaml"

   # BAD — breaks profiles
   config_path = Path.home() / ".hermes" / "config.yaml"
   ```

2. **Use `display_hermes_home()` for user-facing messages.** Import from `hermes_constants`.
   This returns `~/.hermes` for default or `~/.hermes/profiles/<name>` for profiles.
   ```python
   # GOOD
   from hermes_constants import display_hermes_home
   print(f"Config saved to {display_hermes_home()}/config.yaml")

   # BAD — shows wrong path for profiles
   print("Config saved to ~/.hermes/config.yaml")
   ```

3. **Module-level constants are fine** — they cache `get_hermes_home()` at import time,
   which is AFTER `_apply_profile_override()` sets the env var. Just use `get_hermes_home()`,
   not `Path.home() / ".hermes"`.

4. **Tests that mock `Path.home()` must also set `HERMES_HOME`** — since code now uses
   `get_hermes_home()` (reads env var), not `Path.home() / ".hermes"`:
   ```python
   with patch.object(Path, "home", return_value=tmp_path), \
        patch.dict(os.environ, {"HERMES_HOME": str(tmp_path / ".hermes")}):
       ...
   ```

5. **Gateway platform adapters should use token locks** — if the adapter connects with
   a unique credential (bot token, API key), call `acquire_scoped_lock()` from
   `gateway.status` in the `connect()`/`start()` method and `release_scoped_lock()` in
   `disconnect()`/`stop()`. This prevents two profiles from using the same credential.
   See `gateway/platforms/telegram.py` for the canonical pattern.

6. **Profile operations are HOME-anchored, not HERMES_HOME-anchored** — `_get_profiles_root()`
   returns `Path.home() / ".hermes" / "profiles"`, NOT `get_hermes_home() / "profiles"`.
   This is intentional — it lets `hermes -p coder profile list` see all profiles regardless
   of which one is active.

## Known Pitfalls

### DO NOT hardcode `~/.hermes` paths
Use `get_hermes_home()` from `hermes_constants` for code paths. Use `display_hermes_home()`
for user-facing print/log messages. Hardcoding `~/.hermes` breaks profiles — each profile
has its own `HERMES_HOME` directory. This was the source of 5 bugs fixed in PR #3575.

### DO NOT use `simple_term_menu` for interactive menus
Rendering bugs in tmux/iTerm2 — ghosting on scroll. Use `curses` (stdlib) instead. See `hermes_cli/tools_config.py` for the pattern.

### DO NOT use `\033[K` (ANSI erase-to-EOL) in spinner/display code
Leaks as literal `?[K` text under `prompt_toolkit`'s `patch_stdout`. Use space-padding: `f"\r{line}{' ' * pad}"`.

### `_last_resolved_tool_names` is a process-global in `model_tools.py`
`_run_single_child()` in `delegate_tool.py` saves and restores this global around subagent execution. If you add new code that reads this global, be aware it may be temporarily stale during child agent runs.

### DO NOT hardcode cross-tool references in schema descriptions
Tool schema descriptions must not mention tools from other toolsets by name (e.g., `browser_navigate` saying "prefer web_search"). Those tools may be unavailable (missing API keys, disabled toolset), causing the model to hallucinate calls to non-existent tools. If a cross-reference is needed, add it dynamically in `get_tool_definitions()` in `model_tools.py` — see the `browser_navigate` / `execute_code` post-processing blocks for the pattern.

### Tests must not write to `~/.hermes/`
The `_isolate_hermes_home` autouse fixture in `tests/conftest.py` redirects `HERMES_HOME` to a temp dir. Never hardcode `~/.hermes/` paths in tests.

**Profile tests**: When testing profile features, also mock `Path.home()` so that
`_get_profiles_root()` and `_get_default_hermes_home()` resolve within the temp dir.
Use the pattern from `tests/hermes_cli/test_profiles.py`:
```python
@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    home = tmp_path / ".hermes"
    home.mkdir()
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("HERMES_HOME", str(home))
    return home
```

---

## Testing

**ALWAYS use `scripts/run_tests.sh`** — do not call `pytest` directly. The script enforces
hermetic environment parity with CI (unset credential vars, TZ=UTC, LANG=C.UTF-8,
4 xdist workers matching GHA ubuntu-latest). Direct `pytest` on a 16+ core
developer machine with API keys set diverges from CI in ways that have caused
multiple "works locally, fails in CI" incidents (and the reverse).

```bash
scripts/run_tests.sh                                  # full suite, CI-parity
scripts/run_tests.sh tests/gateway/                   # one directory
scripts/run_tests.sh tests/agent/test_foo.py::test_x  # one test
scripts/run_tests.sh -v --tb=long                     # pass-through pytest flags
```

### Why the wrapper (and why the old "just call pytest" doesn't work)

Five real sources of local-vs-CI drift the script closes:

| | Without wrapper | With wrapper |
|---|---|---|
| Provider API keys | Whatever is in your env (auto-detects pool) | All `*_API_KEY`/`*_TOKEN`/etc. unset |
| HOME / `~/.hermes/` | Your real config+auth.json | Temp dir per test |
| Timezone | Local TZ (PDT etc.) | UTC |
| Locale | Whatever is set | C.UTF-8 |
| xdist workers | `-n auto` = all cores (20+ on a workstation) | `-n 4` matching CI |

`tests/conftest.py` also enforces points 1-4 as an autouse fixture so ANY pytest
invocation (including IDE integrations) gets hermetic behavior — but the wrapper
is belt-and-suspenders.

### Running without the wrapper (only if you must)

If you can't use the wrapper (e.g. on Windows or inside an IDE that shells
pytest directly), at minimum activate the venv and pass `-n 4`:

```bash
source venv/bin/activate
python -m pytest tests/ -q -n 4
```

Worker count above 4 will surface test-ordering flakes that CI never sees.

Always run the full suite before pushing changes.
