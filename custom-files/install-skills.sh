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
