#!/usr/bin/env bash
# Install custom skills to ~/.hermes/skills/
# Run from repo root: bash custom-files/install-skills.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILLS_SRC="$SCRIPT_DIR/skills"
SKILLS_DST="$HOME/.hermes/skills"

if [[ ! -d "$SKILLS_SRC" ]]; then
    echo "❌ No skills directory found at $SKILLS_SRC"
    exit 1
fi

mkdir -p "$SKILLS_DST"

echo "📦 Installing custom skills to $SKILLS_DST"
echo ""

for skill_dir in "$SKILLS_SRC"/*/; do
    skill_name="$(basename "$skill_dir")"
    echo "  → $skill_name"
    rm -rf "${SKILLS_DST:?}/$skill_name"
    cp -r "$skill_dir" "$SKILLS_DST/$skill_name"
done

# Also install trading-config.yaml if not already present
TRADING_CFG_SRC="$SCRIPT_DIR/trading-config.yaml"
TRADING_CFG_DST="$HOME/.hermes/memories/trading-config.yaml"
if [[ -f "$TRADING_CFG_SRC" && ! -f "$TRADING_CFG_DST" ]]; then
    mkdir -p "$(dirname "$TRADING_CFG_DST")"
    cp "$TRADING_CFG_SRC" "$TRADING_CFG_DST"
    echo "  → trading-config.yaml installed to $TRADING_CFG_DST"
elif [[ -f "$TRADING_CFG_DST" ]]; then
    echo "  → trading-config.yaml already exists (skipped)"
fi

# Also install Solana blockchain skill from optional-skills if available
SOLANA_SRC="$SCRIPT_DIR/../optional-skills/blockchain/solana"
if [[ -d "$SOLANA_SRC" && ! -d "$SKILLS_DST/solana" ]]; then
    echo "  → solana (from optional-skills)"
    cp -r "$SOLANA_SRC" "$SKILLS_DST/solana"
fi

echo ""
echo "✅ Skills installed:"
ls -1 "$SKILLS_DST"
echo ""
echo "Test scanner: python3 $SKILLS_DST/crypto-scanner/scripts/scanner.py trending --limit 3"
echo "Test journal: python3 $SKILLS_DST/trade-journal/scripts/journal.py show"
echo ""
echo "📋 New tools:"
echo "  Guardian:  python3 $SKILLS_DST/trade-executor/scripts/guardian.py --watch"
echo "  Learning:  python3 $SKILLS_DST/trade-journal/scripts/learning.py analyze"
echo "  Cron view: python3 $SCRIPT_DIR/scripts/cron_viewer.py"
