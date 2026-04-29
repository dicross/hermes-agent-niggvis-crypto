#!/usr/bin/env bash
# nim_undo.sh — reverts all changes made by nim_setup.sh
set -e

echo ""
echo "[1/3] Removing /etc/hosts entry..."
sudo sed -i '/integrate\.api\.nvidia\.com/d' /etc/hosts
echo "      Done."

echo "[2/3] Removing system certificate..."
sudo rm -f /usr/local/share/ca-certificates/nim-proxy.crt
sudo update-ca-certificates --quiet
echo "      Done."

echo "[3/3] Removing NODE_EXTRA_CA_CERTS from shell profiles..."
for FILE in "$HOME/.bashrc" "$HOME/.zshrc" "$HOME/.profile"; do
    if [ -f "$FILE" ]; then
        sed -i '/# nim-proxy: NODE_EXTRA_CA_CERTS/d' "$FILE"
        sed -i '/NODE_EXTRA_CA_CERTS.*nim-proxy/d' "$FILE"
    fi
done
VSCODE_ENV="$HOME/.vscode-server/server-env-setup"
if [ -f "$VSCODE_ENV" ]; then
    sed -i '/# nim-proxy: NODE_EXTRA_CA_CERTS/d' "$VSCODE_ENV"
    sed -i '/NODE_EXTRA_CA_CERTS.*nim-proxy/d' "$VSCODE_ENV"
fi
echo "      Done."

echo ""
echo "All changes reverted. Restart VS Code to apply."
echo ""
