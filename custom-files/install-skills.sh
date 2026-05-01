#!/usr/bin/env bash
# Install custom skills, configs, and core files to ~/.hermes/
#
# Usage:
#   bash install-skills.sh              # Interactive — asks what to install
#   bash install-skills.sh --full       # Everything (first install / reset)
#   bash install-skills.sh --skills     # Skills + config only (preserves SOUL/MEMORY)
#   bash install-skills.sh --config     # Only trading-config.yaml
#
# SOUL.md and MEMORY.md are overwritten ONLY with --full or when confirmed.
# Hermes learns by updating these files — overwriting loses learned patterns.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"
SKILLS_DST="$HOME/.hermes/skills"
HERMES_DIR="$HOME/.hermes"

if [[ ! -d "$SKILLS_SRC" ]]; then
    echo "❌ No skills directory found at $SKILLS_SRC"
    exit 1
fi

mkdir -p "$SKILLS_DST"
mkdir -p "$HERMES_DIR/memories"
mkdir -p "$HERMES_DIR/secrets"

# --- Parse arguments ---
MODE=""
case "${1:-}" in
    --full)   MODE="full" ;;
    --skills) MODE="skills" ;;
    --config) MODE="config" ;;
    --help|-h)
        echo "Usage: install-skills.sh [--full|--skills|--config]"
        echo ""
        echo "  --full     Install everything (skills + SOUL + MEMORY + config)"
        echo "  --skills   Install skills + trading-config only (safe for updates)"
        echo "  --config   Only update trading-config.yaml"
        echo "  (no flag)  Interactive — asks what to do"
        exit 0
        ;;
    "") MODE="ask" ;;
    *)
        echo "Unknown option: $1. Use --help for usage."
        exit 1
        ;;
esac

# --- Interactive mode ---
if [[ "$MODE" == "ask" ]]; then
    echo "📦 Niggvis Crypto Agent Installer"
    echo ""
    echo "  1) Full install (skills + SOUL.md + MEMORY.md + config)"
    echo "     ⚠️  Overwrites SOUL.md and MEMORY.md — resets agent learning"
    echo ""
    echo "  2) Update skills + config only (recommended for updates)"
    echo "     ✅ Preserves SOUL.md and MEMORY.md (keeps learned patterns)"
    echo ""
    echo "  3) Config only (just trading-config.yaml)"
    echo ""
    read -rp "Choose [1/2/3] (default: 2): " choice
    case "${choice:-2}" in
        1) MODE="full" ;;
        2) MODE="skills" ;;
        3) MODE="config" ;;
        *)
            echo "Invalid choice. Exiting."
            exit 1
            ;;
    esac
    echo ""
fi

echo "📦 Installing Niggvis Crypto Trading Agent (mode: $MODE)"
echo "   Target: $HERMES_DIR"
echo ""

# --- Core files (only in full mode) ---
if [[ "$MODE" == "full" ]]; then
    echo "🧠 Core files:"

    # SOUL.md — agent personality
    if [[ -f "$SCRIPT_DIR/SOUL.md" ]]; then
        cp "$SCRIPT_DIR/SOUL.md" "$HERMES_DIR/SOUL.md"
        echo "  → SOUL.md (overwritten)"
    fi

    # MEMORY.md — knowledge base
    if [[ -f "$SCRIPT_DIR/MEMORY.md" ]]; then
        cp "$SCRIPT_DIR/MEMORY.md" "$HERMES_DIR/memories/MEMORY.md"
        echo "  → MEMORY.md (overwritten)"
    fi

    echo ""
else
    echo "🧠 Core files: SKIPPED (preserving agent learning)"
    # First install: copy if files don't exist yet
    if [[ -f "$SCRIPT_DIR/SOUL.md" && ! -f "$HERMES_DIR/SOUL.md" ]]; then
        cp "$SCRIPT_DIR/SOUL.md" "$HERMES_DIR/SOUL.md"
        echo "  → SOUL.md (first install)"
    fi
    if [[ -f "$SCRIPT_DIR/MEMORY.md" && ! -f "$HERMES_DIR/memories/MEMORY.md" ]]; then
        cp "$SCRIPT_DIR/MEMORY.md" "$HERMES_DIR/memories/MEMORY.md"
        echo "  → MEMORY.md (first install)"
    fi
    echo ""
fi

# --- Config (full + skills + config modes) ---
if [[ "$MODE" != "skip" ]]; then
    echo "⚙️ Config:"

    # trading-config.yaml — always update (agent proposes changes via Telegram anyway)
    if [[ -f "$SCRIPT_DIR/trading-config.yaml" ]]; then
        cp "$SCRIPT_DIR/trading-config.yaml" "$HERMES_DIR/memories/trading-config.yaml"
        echo "  → trading-config.yaml (updated)"
    fi

    # .env — only if not exists (contains secrets)
    if [[ -f "$SCRIPT_DIR/.env.example" && ! -f "$HERMES_DIR/.env" ]]; then
        cp "$SCRIPT_DIR/.env.example" "$HERMES_DIR/.env"
        echo "  → .env (created from template — EDIT WITH YOUR KEYS)"
    fi

    # config.yaml — only if not exists (user may have customized)
    if [[ -f "$SCRIPT_DIR/config.example.yaml" && ! -f "$HERMES_DIR/config.yaml" ]]; then
        cp "$SCRIPT_DIR/config.example.yaml" "$HERMES_DIR/config.yaml"
        echo "  → config.yaml (created from template)"
    fi

    # gateway.json — always update (contains chat routing config)
    if [[ -f "$SCRIPT_DIR/gateway.json" ]]; then
        cp "$SCRIPT_DIR/gateway.json" "$HERMES_DIR/gateway.json"
        echo "  → gateway.json (updated — chat routing: agent/cron/guardian)"
    fi

    # cron/jobs.json — always update (deliver targets point to split chats)
    if [[ -f "$SCRIPT_DIR/cron/jobs.json" ]]; then
        mkdir -p "$HERMES_DIR/cron"
        cp "$SCRIPT_DIR/cron/jobs.json" "$HERMES_DIR/cron/jobs.json"
        echo "  → cron/jobs.json (updated — deliver targets)"
    fi

    echo ""
fi

# --- Skills (full + skills modes) ---
if [[ "$MODE" == "full" || "$MODE" == "skills" ]]; then
    echo "🔧 Skills:"

    for skill_dir in "$SKILLS_SRC"/*/; do
        skill_name="$(basename "$skill_dir")"
        echo "  → $skill_name"
        rm -rf "${SKILLS_DST:?}/$skill_name"
        cp -r "$skill_dir" "$SKILLS_DST/$skill_name"
    done

    # Also install Solana blockchain skill from optional-skills if available
    SOLANA_SRC="$SCRIPT_DIR/../optional-skills/blockchain/solana"
    if [[ -d "$SOLANA_SRC" && ! -d "$SKILLS_DST/solana" ]]; then
        echo "  → solana (from optional-skills)"
        cp -r "$SOLANA_SRC" "$SKILLS_DST/solana"
    fi

    echo ""
fi

echo "✅ Installation complete! (mode: $MODE)"
echo ""
if [[ "$MODE" == "full" || "$MODE" == "skills" ]]; then
    echo "Skills installed:"
    ls -1 "$SKILLS_DST"
    echo ""
fi
echo "Quick test:"
echo "  python3 $SKILLS_DST/crypto-scanner/scripts/scanner.py trending --limit 3"
echo "  python3 $SKILLS_DST/trade-executor/scripts/guardian.py --watch"
