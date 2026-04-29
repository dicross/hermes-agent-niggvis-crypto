#!/usr/bin/env bash
# nim_setup.sh — one-time setup for the NVIDIA NIM Rate Limiter Proxy
# Works on WSL2 (Ubuntu) and any Linux VPS.
# Run once, restart VS Code, then: sudo python3 ~/nim_proxy.py
set -e

CERT_DIR="$HOME/.nim-proxy"
CERT_FILE="$CERT_DIR/nim_cert.pem"
KEY_FILE="$CERT_DIR/nim_key.pem"
HOSTS_ENTRY="127.0.0.1 integrate.api.nvidia.com"

echo ""
echo "+--------------------------------------------------+"
echo "|   NVIDIA NIM Rate Limiter -- One-Time Setup      |"
echo "+--------------------------------------------------+"
echo ""

# ── 1. Certificate directory ──────────────────────────────────
mkdir -p "$CERT_DIR"
chmod 700 "$CERT_DIR"

# ── 2. Self-signed TLS certificate ───────────────────────────
echo "[1/4] Generating self-signed certificate..."

# Create openssl config with Subject Alternative Name
cat > "$CERT_DIR/openssl.cnf" <<EOF
[req]
default_bits       = 2048
prompt             = no
default_md         = sha256
distinguished_name = dn
x509_extensions    = v3_req

[dn]
CN = integrate.api.nvidia.com

[v3_req]
subjectAltName = DNS:integrate.api.nvidia.com
EOF

openssl req -x509 -newkey rsa:2048 \
  -keyout "$KEY_FILE" \
  -out    "$CERT_FILE" \
  -days   365 \
  -nodes \
  -config "$CERT_DIR/openssl.cnf" 2>/dev/null

chmod 600 "$KEY_FILE"
echo "      Certificate saved to: $CERT_DIR"

# ── 3. System trust store ─────────────────────────────────────
echo "[2/4] Adding certificate to system trust store..."
sudo cp "$CERT_FILE" /usr/local/share/ca-certificates/nim-proxy.crt
sudo update-ca-certificates --quiet
echo "      System store updated."

# ── 4. Node.js trust (VS Code extension host) ─────────────────
echo "[3/4] Configuring Node.js certificate trust..."
MARKER="# nim-proxy: NODE_EXTRA_CA_CERTS"

add_to_file() {
    local FILE="$1"
    if [ -f "$FILE" ] && ! grep -q "$MARKER" "$FILE"; then
        printf '\n%s\nexport NODE_EXTRA_CA_CERTS="%s"\n' "$MARKER" "$CERT_FILE" >> "$FILE"
        echo "      Added to $FILE"
    fi
}

add_to_file "$HOME/.bashrc"
add_to_file "$HOME/.zshrc"
add_to_file "$HOME/.profile"

# VS Code Server picks up env from ~/.vscode-server/server-env-setup (Remote SSH)
VSCODE_ENV="$HOME/.vscode-server/server-env-setup"
if [ -d "$HOME/.vscode-server" ]; then
    if ! grep -q "$MARKER" "$VSCODE_ENV" 2>/dev/null; then
        printf '#!/usr/bin/env bash\n%s\nexport NODE_EXTRA_CA_CERTS="%s"\n' "$MARKER" "$CERT_FILE" >> "$VSCODE_ENV"
        chmod +x "$VSCODE_ENV"
        echo "      Added to ~/.vscode-server/server-env-setup"
    fi
fi

# ── 5. /etc/hosts ─────────────────────────────────────────────
echo "[4/4] Updating /etc/hosts..."
if ! grep -q "integrate.api.nvidia.com" /etc/hosts; then
    echo "$HOSTS_ENTRY" | sudo tee -a /etc/hosts > /dev/null
    echo "      Added: $HOSTS_ENTRY"
else
    echo "      Entry already present."
fi

echo ""
echo "+--------------------------------------------------+"
echo "|   Setup complete!                                |"
echo "+--------------------------------------------------+"
echo "|  1. source ~/.bashrc  (or restart terminal)      |"
echo "|  2. Restart VS Code completely                   |"
echo "|  3. sudo python3 ~/nim_proxy.py                  |"
echo "+--------------------------------------------------+"
echo "|  To undo all changes: bash ~/nim_undo.sh         |"
echo "+--------------------------------------------------+"
echo ""
