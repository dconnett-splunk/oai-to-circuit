#!/bin/bash
#
# Update script for oai-to-circuit
# Run with: sudo ./update.sh
#

set -e  # Exit on error

echo "=============================="
echo "OAI-to-Circuit Update Script"
echo "=============================="
echo ""

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo "❌ Error: Please run as root (use sudo)"
    exit 1
fi

INSTALL_DIR="/opt/oai-to-circuit"
SERVICE_USER="oai-bridge"
SERVICE_NAME="oai-to-circuit"

# Check if installation exists
if [ ! -d "$INSTALL_DIR" ]; then
    echo "❌ Error: Installation not found at $INSTALL_DIR"
    echo "   Run install.sh first"
    exit 1
fi

echo "📦 Updating application files..."

# Backup current installation
BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
echo "   Creating backup: $BACKUP_DIR"
cp -r "$INSTALL_DIR" "$BACKUP_DIR"

# Copy updated files
echo "   Copying Python modules..."
mkdir -p "$INSTALL_DIR/oai_to_circuit"
cp -r oai_to_circuit/*.py "$INSTALL_DIR/oai_to_circuit/"

if [ -d "oai_to_circuit/admin" ]; then
    echo "   Copying admin package and assets..."
    mkdir -p "$INSTALL_DIR/oai_to_circuit/admin"
    cp -r oai_to_circuit/admin/* "$INSTALL_DIR/oai_to_circuit/admin/"
fi

echo "   Copying utility scripts..."
cp rewriter.py "$INSTALL_DIR/" 2>/dev/null || true
cp backfill_hec.py "$INSTALL_DIR/" 2>/dev/null || true
cp add_subkey_names_table.py "$INSTALL_DIR/" 2>/dev/null || true
cp check_and_setup_names.py "$INSTALL_DIR/" 2>/dev/null || true
cp db_queries.py "$INSTALL_DIR/" 2>/dev/null || true
cp provision_user.py "$INSTALL_DIR/" 2>/dev/null || true
cp query "$INSTALL_DIR/" 2>/dev/null || true

echo "🔐 Fixing ownership..."
chown -R "$SERVICE_USER":"$SERVICE_USER" "$INSTALL_DIR"

echo "🔄 Restarting service..."
systemctl restart "$SERVICE_NAME"

echo "⏳ Waiting for service to start..."
sleep 2

# Check service status
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✅ Update complete! Service is running."
    echo ""
    echo "📊 Service status:"
    systemctl status "$SERVICE_NAME" --no-pager -l | head -15
    echo ""
    echo "📜 Recent logs:"
    journalctl -u "$SERVICE_NAME" -n 10 --no-pager
else
    echo "⚠️  Update complete but service is not running!"
    echo "   Check logs: sudo journalctl -u $SERVICE_NAME -n 50"
    exit 1
fi

echo ""
echo "Backup saved at: $BACKUP_DIR"
echo "To rollback: sudo cp -r $BACKUP_DIR/* $INSTALL_DIR/ && sudo systemctl restart $SERVICE_NAME"
echo ""
