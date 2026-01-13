# Deployment Guide

> **Navigation:** [Documentation Home](../README.md) | [Getting Started](../getting-started/) | [Operations](../operations/)

This guide covers both initial deployment and ongoing update procedures for the OpenAI to Circuit Bridge.

For initial installation from scratch, see the [Installation Guide](../getting-started/installation.md).

---

## Table of Contents

- [Quick Deploy](#quick-deploy)
- [Initial System Setup](#initial-system-setup)
- [Deploying Updates](#deploying-updates)
- [Configuration Updates](#configuration-updates)
- [Rollback Procedures](#rollback-procedures)
- [Deployment Automation](#deployment-automation)
- [Zero-Downtime Deployment](#zero-downtime-deployment)
- [Troubleshooting](#troubleshooting)
- [Post-Deployment Monitoring](#post-deployment-monitoring)

---

## Quick Deploy

### Prerequisites

- Linux system with systemd
- Python 3.9+
- Root/sudo access

### Quick Install (New Installation)

```bash
# 1. Create user and directories
sudo useradd -r -s /bin/false -d /opt/oai-to-circuit oai-bridge
sudo mkdir -p /opt/oai-to-circuit /var/lib/oai-to-circuit /etc/oai-to-circuit /var/log/oai-to-circuit

# 2. Copy application
sudo cp -r . /opt/oai-to-circuit/
cd /opt/oai-to-circuit
sudo pip3 install -r requirements.txt

# 3. Set ownership
sudo chown -R oai-bridge:oai-bridge /opt/oai-to-circuit /var/lib/oai-to-circuit /var/log/oai-to-circuit
sudo chown -R root:oai-bridge /etc/oai-to-circuit
sudo chmod 750 /etc/oai-to-circuit

# 4. Configure credentials
sudo cp credentials.env.example /etc/oai-to-circuit/credentials.env
sudo vim /etc/oai-to-circuit/credentials.env  # Edit with your credentials
sudo chmod 640 /etc/oai-to-circuit/credentials.env

# 5. Configure quotas (optional)
sudo cp quotas.json.example /etc/oai-to-circuit/quotas.json
sudo vim /etc/oai-to-circuit/quotas.json  # Edit quota rules
sudo chmod 640 /etc/oai-to-circuit/quotas.json

# 6. Install and start service
sudo cp oai-to-circuit.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable oai-to-circuit
sudo systemctl start oai-to-circuit

# 7. Verify
sudo systemctl status oai-to-circuit
curl http://localhost:12000/health
```

### Quick Update (Existing Installation)

```bash
# On your server
sudo -i
cd /opt/oai-to-circuit
git pull origin main
systemctl restart oai-to-circuit

# Verify it's running
systemctl status oai-to-circuit
curl http://localhost:12000/health
```

### Essential Commands

```bash
# View logs
sudo journalctl -u oai-to-circuit -f

# Restart service
sudo systemctl restart oai-to-circuit

# Stop service
sudo systemctl stop oai-to-circuit

# Check status
sudo systemctl status oai-to-circuit

# Edit configuration
sudo vim /etc/oai-to-circuit/credentials.env
sudo systemctl restart oai-to-circuit

# View recent logs
sudo journalctl -u oai-to-circuit -n 100
```

---

## Initial System Setup

### Firewall Configuration

**RHEL/CentOS/Fedora:**
```bash
sudo firewall-cmd --permanent --add-port=12000/tcp
sudo firewall-cmd --permanent --add-port=12443/tcp  # if using HTTPS
sudo firewall-cmd --reload
```

**Ubuntu/Debian:**
```bash
sudo ufw allow 12000/tcp
sudo ufw allow 12443/tcp  # if using HTTPS
```

### HTTPS Setup (Optional)

**Generate self-signed certificate (development):**
```bash
cd /opt/oai-to-circuit
sudo -u oai-bridge python3 generate_cert.py
```

**Use CA-signed certificates (production):**
```bash
# Copy certificates
sudo cp /path/to/cert.pem /etc/oai-to-circuit/cert.pem
sudo cp /path/to/key.pem /etc/oai-to-circuit/key.pem
sudo chown oai-bridge:oai-bridge /etc/oai-to-circuit/*.pem
sudo chmod 600 /etc/oai-to-circuit/key.pem
sudo chmod 644 /etc/oai-to-circuit/cert.pem

# Edit service to use SSL
sudo vim /etc/systemd/system/oai-to-circuit.service
# Change ExecStart line to: ExecStart=/usr/bin/python3 /opt/oai-to-circuit/rewriter.py --ssl

sudo systemctl daemon-reload
sudo systemctl restart oai-to-circuit
```

### Splunk HEC Setup (Optional)

1. In Splunk Web: **Settings > Data Inputs > HTTP Event Collector > New Token**
2. Configure token:
   - Name: `oai-to-circuit-metrics`
   - Source type: `llm:usage`
   - Index: `main`
3. Copy token and add to `/etc/oai-to-circuit/credentials.env`:
   ```bash
   SPLUNK_HEC_URL=https://splunk.example.com:8088/services/collector/event
   SPLUNK_HEC_TOKEN=your-token-here
   ```
4. Restart service:
   ```bash
   sudo systemctl restart oai-to-circuit
   ```

---

## Deploying Updates

### Standard Update Procedure

#### 1. Prepare Local Changes

```bash
# Run tests locally first
pytest

# Commit your changes
git add .
git commit -m "Add feature X / Fix bug Y"
git push origin main
```

#### 2. Connect to Server

```bash
ssh your-server.example.com
sudo -i  # or use sudo for each command
```

#### 3. Stop Service (Optional but Recommended)

For zero-downtime updates, skip this step. For safety (especially database changes), stop first:

```bash
sudo systemctl stop oai-to-circuit
```

#### 4. Pull Updates

```bash
cd /opt/oai-to-circuit
git pull origin main
```

#### 5. Update Dependencies (If Changed)

```bash
# Check if requirements.txt changed
git diff HEAD@{1} HEAD -- requirements.txt

# If changed, update dependencies
pip3 install -r requirements.txt --upgrade
```

#### 6. Run Database Migrations (If Any)

```bash
# Backup first
sudo cp /var/lib/oai-to-circuit/quota.db /var/lib/oai-to-circuit/quota.db.backup

# Run migration script (if you create one)
# sudo -u oai-bridge python3 migrate.py
```

#### 7. Start/Restart Service

```bash
sudo systemctl start oai-to-circuit
# or
sudo systemctl restart oai-to-circuit
```

#### 8. Verify Deployment

```bash
# Check service status
sudo systemctl status oai-to-circuit

# Check logs for errors
sudo journalctl -u oai-to-circuit -n 50

# Test health endpoint
curl http://localhost:12000/health

# Test actual request (if you have a test subkey)
curl -H "X-Bridge-Subkey: test_key" \
     -H "Content-Type: application/json" \
     http://localhost:12000/v1/chat/completions \
     -d '{"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "test"}]}'
```

### Deployment Checklist

Use this checklist for each deployment:

- [ ] Tests pass locally (`pytest`)
- [ ] Changes committed and pushed to git
- [ ] Connected to production server
- [ ] Service stopped (if needed for safety)
- [ ] Code pulled from git
- [ ] Dependencies updated (if requirements.txt changed)
- [ ] Configuration updated (if new env vars added)
- [ ] Database backed up (if schema changes)
- [ ] Service restarted
- [ ] Health check passed
- [ ] Logs checked for errors
- [ ] Test request successful
- [ ] Monitoring dashboard checked (if using Splunk)

---

## Configuration Updates

### Adding New Environment Variables

```bash
# Edit credentials file
sudo vim /etc/oai-to-circuit/credentials.env
# Add new variables

# Restart service to apply
sudo systemctl restart oai-to-circuit
```

### Updating Quota Configuration

```bash
# Update quotas locally, commit, and push
# On server:
cd /opt/oai-to-circuit
git pull
cp quotas.json /etc/oai-to-circuit/quotas.json
systemctl restart oai-to-circuit
```

### Updating Systemd Service File

```bash
cd /opt/oai-to-circuit
git pull
cp oai-to-circuit.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart oai-to-circuit
```

---

## Rollback Procedures

### Quick Rollback

If the deployment fails:

```bash
# Stop the broken version
sudo systemctl stop oai-to-circuit

# Rollback code
cd /opt/oai-to-circuit
git log --oneline -n 5  # Find previous commit
git reset --hard <previous-commit-hash>

# Restore database if needed
sudo cp /var/lib/oai-to-circuit/quota.db.backup /var/lib/oai-to-circuit/quota.db

# Restart service
sudo systemctl start oai-to-circuit

# Verify
sudo systemctl status oai-to-circuit
curl http://localhost:12000/health
```

---

## Deployment Automation

### Automated Deployment Script

Create `/root/deploy-bridge.sh`:

```bash
#!/bin/bash
set -e  # Exit on error

INSTALL_DIR="/opt/oai-to-circuit"
SERVICE_NAME="oai-to-circuit"
BACKUP_DIR="/var/lib/oai-to-circuit/backups"

echo "=== OpenAI to Circuit Bridge Deployment ==="
echo "$(date)"

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Backup quota database
echo "Backing up quota database..."
cp /var/lib/oai-to-circuit/quota.db "$BACKUP_DIR/quota.db.$(date +%Y%m%d_%H%M%S)"

# Stop service
echo "Stopping service..."
systemctl stop "$SERVICE_NAME"

# Pull updates
echo "Pulling updates from git..."
cd "$INSTALL_DIR"
git fetch origin
PREVIOUS_COMMIT=$(git rev-parse HEAD)
git pull origin main

# Check if requirements changed
if git diff "$PREVIOUS_COMMIT" HEAD --name-only | grep -q "requirements.txt"; then
    echo "Requirements changed, updating dependencies..."
    pip3 install -r requirements.txt --upgrade
fi

# Check if systemd service changed
if git diff "$PREVIOUS_COMMIT" HEAD --name-only | grep -q "oai-to-circuit.service"; then
    echo "Systemd service changed, reloading daemon..."
    cp oai-to-circuit.service /etc/systemd/system/
    systemctl daemon-reload
fi

# Start service
echo "Starting service..."
systemctl start "$SERVICE_NAME"

# Wait for service to start
sleep 2

# Check status
if systemctl is-active --quiet "$SERVICE_NAME"; then
    echo "✓ Service started successfully"
    
    # Health check
    if curl -s http://localhost:12000/health | grep -q "healthy"; then
        echo "✓ Health check passed"
        echo "=== Deployment successful ==="
        exit 0
    else
        echo "✗ Health check failed"
        exit 1
    fi
else
    echo "✗ Service failed to start"
    echo "Rolling back..."
    cd "$INSTALL_DIR"
    git reset --hard "$PREVIOUS_COMMIT"
    systemctl start "$SERVICE_NAME"
    echo "Rolled back to previous version"
    exit 1
fi
```

Make it executable:

```bash
sudo chmod +x /root/deploy-bridge.sh
```

Use it:

```bash
sudo /root/deploy-bridge.sh
```

---

## Zero-Downtime Deployment

### Option 1: Blue-Green Deployment

Run two instances behind a load balancer:

```bash
# Deploy to blue instance
ssh blue-server
sudo -i
cd /opt/oai-to-circuit
git pull
systemctl restart oai-to-circuit

# Test blue instance
curl http://blue-server:12000/health

# Switch traffic to blue in load balancer
# (HAProxy, nginx, etc.)

# Deploy to green instance
ssh green-server
# ... repeat deployment

# Switch traffic back or keep on blue
```

### Option 2: Rolling Restart with Multiple Workers

If running multiple uvicorn workers:

```bash
# In systemd service, use:
# ExecStart=/usr/bin/python3 /opt/oai-to-circuit/rewriter.py --workers 4

# Then use systemctl reload instead of restart
sudo systemctl reload oai-to-circuit
```

---

## Troubleshooting

### Service Won't Start

```bash
# Check logs for errors
sudo journalctl -u oai-to-circuit -n 100

# Common issues:
# - Missing credentials in /etc/oai-to-circuit/credentials.env
# - Permission issues on /var/lib/oai-to-circuit
# - Ports already in use
# - Syntax error in Python code (rollback)
# - Missing dependency (pip3 install -r requirements.txt)
```

### Check if Running

```bash
sudo systemctl is-active oai-to-circuit
curl http://localhost:12000/health
```

### Database Issues

**Database locked:**
```bash
sudo systemctl stop oai-to-circuit
sudo rm /var/lib/oai-to-circuit/quota.db-journal
sudo systemctl start oai-to-circuit
```

**Database corruption:**
```bash
# Restore from backup
sudo systemctl stop oai-to-circuit
sudo cp /var/lib/oai-to-circuit/backups/quota.db.20240101_120000 /var/lib/oai-to-circuit/quota.db
sudo chown oai-bridge:oai-bridge /var/lib/oai-to-circuit/quota.db
sudo systemctl start oai-to-circuit
```

### Git Conflicts on Server

```bash
# If local changes on server conflict with remote:
cd /opt/oai-to-circuit
git stash  # Save any local changes
git pull origin main
git stash pop  # Re-apply local changes (may need manual merge)
```

### Streaming Tokens Still 0

```bash
# Check logs for SSE parser and streaming messages
sudo journalctl -u oai-to-circuit -f | grep "SSE PARSER\|STREAMING"

# Enable debug logging temporarily
sudo vim /etc/oai-to-circuit/credentials.env
# Add: LOG_LEVEL=DEBUG
sudo systemctl restart oai-to-circuit

# After testing, set back to INFO
```

---

## Post-Deployment Monitoring

### Monitor Logs in Real-Time

```bash
# Watch logs
sudo journalctl -u oai-to-circuit -f

# In another terminal, watch requests
watch -n 5 'sudo journalctl -u oai-to-circuit --since "5 minutes ago" | grep "Processing request"'
```

### Check Quota Database

```bash
sqlite3 /var/lib/oai-to-circuit/quota.db "SELECT subkey, model, requests FROM usage ORDER BY requests DESC LIMIT 10;"
```

### Check Splunk (if configured)

Navigate to Splunk and run:
```spl
index=main sourcetype=llm:usage | timechart count
```

### Verify Streaming and Cost Tracking

**Check streaming token usage:**
```spl
index=oai_circuit sourcetype="llm:usage" is_streaming=true
| table _time, model, total_tokens, prompt_tokens, completion_tokens
| head 10
```

**Check cost data:**
```spl
index=oai_circuit sourcetype="llm:usage" cost_known=true
| table _time, model, estimated_cost_usd
| head 10
```

---

## Common Deployment Scenarios

### Scenario 1: Code-Only Update (No Config Changes)

```bash
cd /opt/oai-to-circuit
git pull
systemctl restart oai-to-circuit
```

### Scenario 2: New Dependencies Added

```bash
cd /opt/oai-to-circuit
git pull
pip3 install -r requirements.txt --upgrade
systemctl restart oai-to-circuit
```

### Scenario 3: New Environment Variables

```bash
cd /opt/oai-to-circuit
git pull
vim /etc/oai-to-circuit/credentials.env
# Add: NEW_VAR=value
systemctl restart oai-to-circuit
```

### Scenario 4: Database Schema Changes

```bash
cd /opt/oai-to-circuit
systemctl stop oai-to-circuit
cp /var/lib/oai-to-circuit/quota.db /var/lib/oai-to-circuit/quota.db.backup
git pull
# Run migration script if exists
systemctl start oai-to-circuit
```

---

## Best Practices

1. **Always test locally first**: Run `pytest` before deploying
2. **Deploy during low-traffic periods**: If possible, deploy during off-hours
3. **Backup before deploying**: Especially the quota database
4. **Monitor after deployment**: Watch logs for 10-15 minutes
5. **Use version tags**: Tag releases in git for easy rollback
6. **Document changes**: Update CHANGELOG.md with each deployment
7. **Staging environment**: Test in staging before production
8. **Gradual rollout**: For major changes, use feature flags or blue-green
9. **Keep dependencies updated**: Regularly update requirements.txt
10. **Automate when stable**: Use deployment script after process is proven

---

## File Locations

- **Application**: `/opt/oai-to-circuit/`
- **Configuration**: `/etc/oai-to-circuit/credentials.env`
- **Quotas**: `/etc/oai-to-circuit/quotas.json`
- **Database**: `/var/lib/oai-to-circuit/quota.db`
- **Logs**: `journalctl -u oai-to-circuit`
- **Service**: `/etc/systemd/system/oai-to-circuit.service`
- **Backups**: `/var/lib/oai-to-circuit/backups/`

---

## Security Notes

- Credentials file should be mode `640` owned by `root:oai-bridge`
- Service runs as unprivileged user `oai-bridge`
- Database and logs owned by `oai-bridge`
- No hardcoded credentials in code
- SSL certificates should be properly secured (mode 600 for private keys)

---

## Related Documentation

- [Installation Guide](../getting-started/installation.md) - Initial setup from scratch
- [Production Setup](../getting-started/production-setup.md) - Production configuration
- [Architecture Overview](../architecture/architecture.md) - System architecture
- [Operations Guide](../operations/) - Day-to-day operations
- [Troubleshooting](../operations/diagnostic-logging.md) - Diagnostic logging

---

**For initial installation**, see [Installation Guide](../getting-started/installation.md).

**For production setup details**, see [Production Setup Guide](../getting-started/production-setup.md).

