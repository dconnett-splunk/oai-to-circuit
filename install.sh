#!/bin/bash
#
# Installation script for oai-to-circuit
# Run with: sudo ./install.sh
#

set -e  # Exit on error

echo "=================================="
echo "OAI-to-Circuit Installation Script"
echo "=================================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Error: Please run as root (use sudo)"
    exit 1
fi

INSTALL_DIR="/opt/oai-to-circuit"
DATA_DIR="/var/lib/oai-to-circuit"
CONFIG_DIR="/etc/oai-to-circuit"
LOG_DIR="/var/log/oai-to-circuit"
SERVICE_USER="oai-bridge"

echo "📁 Creating directories..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$DATA_DIR"
mkdir -p "$CONFIG_DIR"
mkdir -p "$LOG_DIR"

echo "👤 Creating system user: $SERVICE_USER..."
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd -r -s /bin/false -d "$INSTALL_DIR" "$SERVICE_USER"
    echo "   ✓ User created"
else
    echo "   ℹ User already exists"
fi

echo "📦 Copying application files..."
cp -r oai_to_circuit "$INSTALL_DIR/"
cp rewriter.py "$INSTALL_DIR/"
cp requirements.txt "$INSTALL_DIR/"
cp backfill_hec.py "$INSTALL_DIR/"
cp add_subkey_names_table.py "$INSTALL_DIR/"
cp check_and_setup_names.py "$INSTALL_DIR/"
cp db_queries.py "$INSTALL_DIR/"
cp provision_user.py "$INSTALL_DIR/" 2>/dev/null || true
cp query "$INSTALL_DIR/" 2>/dev/null || true

echo "📝 Copying example configuration files..."
if [ ! -f "$CONFIG_DIR/quotas.json" ]; then
    if [ -f "quotas.json.example" ]; then
        cp quotas.json.example "$CONFIG_DIR/quotas.json"
        echo "   ✓ Created quotas.json from example"
    fi
fi

if [ ! -f "$CONFIG_DIR/credentials.env" ]; then
    if [ -f "credentials.env.example" ]; then
        cp credentials.env.example "$CONFIG_DIR/credentials.env"
        echo "   ✓ Created credentials.env from example"
        echo "   ⚠️  IMPORTANT: Edit $CONFIG_DIR/credentials.env with your credentials"
    fi
fi

echo "📚 Installing Python dependencies..."
cd "$INSTALL_DIR"
pip3 install -r requirements.txt

echo "🔐 Setting ownership and permissions..."
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$DATA_DIR"
chown -R "$SERVICE_USER":"$SERVICE_USER" "$LOG_DIR"
chown -R root:"$SERVICE_USER" "$CONFIG_DIR"
chmod 750 "$CONFIG_DIR"
chmod 640 "$CONFIG_DIR"/* 2>/dev/null || true

echo "🚀 Installing systemd service..."
cp oai-to-circuit.service /etc/systemd/system/
systemctl daemon-reload

echo "✅ Installation complete!"
echo ""
echo "Next steps:"
echo "1. Edit credentials: sudo nano $CONFIG_DIR/credentials.env"
echo "2. Edit quotas (optional): sudo nano $CONFIG_DIR/quotas.json"
echo "3. Enable service: sudo systemctl enable oai-to-circuit"
echo "4. Start service: sudo systemctl start oai-to-circuit"
echo "5. Check status: sudo systemctl status oai-to-circuit"
echo ""

