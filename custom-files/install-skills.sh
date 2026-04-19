#!/usr/bin/env bash
# Install custom skills, configs, and core files to ~/.hermes/
# Run from repo root: bash custom-files/install-skills.sh

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

echo "📦 Installing Niggvis Crypto Trading Agent"
echo "   Target: $HERMES_DIR"
echo ""

# --- Core files (ALWAYS overwrite — these define the agent) ---
echo "🧠 Core files:"

# SOUL.md — agent personality
if [[ -f "$SCRIPT_DIR/SOUL.md" ]]; then
    cp "$SCRIPT_DIR/SOUL.md" "$HERMES_DIR/SOUL.md"
    echo "  → SOUL.md (updated)"
fi

# MEMORY.md — knowledge base
if [[ -f "$SCRIPT_DIR/MEMORY.md" ]]; then
    cp "$SCRIPT_DIR/MEMORY.md" "$HERMES_DIR/memories/MEMORY.md"
    echo "  → MEMORY.md (updated)"
fi

# trading-config.yaml — ALWAYS overwrite to get latest defaults
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

echo ""

# --- Skills ---
echo "🔧 Skills:"

# --- Skills ---
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
echo "✅ Installation complete!"
echo ""
echo "Skills installed:"
ls -1 "$SKILLS_DST"
echo ""
echo "Core files:"
echo "  SOUL.md           → $HERMES_DIR/SOUL.md"
echo "  MEMORY.md         → $HERMES_DIR/memories/MEMORY.md"
echo "  trading-config    → $HERMES_DIR/memories/trading-config.yaml"
echo ""
echo "Quick test:"
echo "  python3 $SKILLS_DST/crypto-scanner/scripts/scanner.py trending --limit 3"
echo "  python3 $SKILLS_DST/trade-executor/scripts/jupiter_swap.py wallet"
echo "  python3 $SKILLS_DST/trade-executor/scripts/guardian.py --watch"
