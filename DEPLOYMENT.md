# Deployment Guide

## Deploying Updates to Existing Installation

This guide covers deploying code updates to a running server installation.

For initial setup from scratch, see [INSTALLATION.md](INSTALLATION.md).

## Quick Deploy (Standard Update)

```bash
# On your development machine
cd /path/to/oai-to-circuit
git add .
git commit -m "Description of changes"
git push origin main

# On your server
sudo -i
cd /opt/oai-to-circuit
git pull origin main
systemctl restart oai-to-circuit

# Verify it's running
systemctl status oai-to-circuit
curl http://localhost:12000/health
```

## Detailed Deployment Steps

### 1. Prepare Local Changes

```bash
# Run tests locally first
pytest

# Commit your changes
git add .
git commit -m "Add feature X / Fix bug Y"
git push origin main  # or your branch
```

### 2. Connect to Server

```bash
ssh your-server.example.com
sudo -i  # or use sudo for each command
```

### 3. Stop Service (Optional but Recommended)

For zero-downtime updates, skip this step. For safety (especially database changes), stop first:

```bash
sudo systemctl stop oai-to-circuit
```

### 4. Pull Updates

```bash
cd /opt/oai-to-circuit
git pull origin main
```

### 5. Update Dependencies (If Changed)

```bash
# Check if requirements.txt changed
git diff HEAD@{1} HEAD -- requirements.txt

# If changed, update dependencies
pip3 install -r requirements.txt --upgrade
```

### 6. Update Configuration (If Needed)

If you added new environment variables:

```bash
sudo nano /etc/oai-to-circuit/credentials.env
# Add new variables
```

If you changed the systemd service file:

```bash
sudo cp oai-to-circuit.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### 7. Run Database Migrations (If Any)

Currently there are no migrations, but if you've modified the quota database schema:

```bash
# Backup first
sudo cp /var/lib/oai-to-circuit/quota.db /var/lib/oai-to-circuit/quota.db.backup

# Run migration script (if you create one)
# sudo -u oai-bridge python3 migrate.py
```

### 8. Start/Restart Service

```bash
sudo systemctl start oai-to-circuit
# or
sudo systemctl restart oai-to-circuit
```

### 9. Verify Deployment

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

## Deployment Checklist

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

## Rollback Procedure

If the deployment fails:

### Quick Rollback

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

## Automated Deployment Script

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

## Zero-Downtime Deployment (Advanced)

For high-availability setups:

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

If running multiple uvicorn workers, restart one at a time:

```bash
# In systemd service, use:
# ExecStart=/usr/bin/python3 /opt/oai-to-circuit/rewriter.py --workers 4

# Then use systemctl reload instead of restart
sudo systemctl reload oai-to-circuit
```

## Environment-Specific Deployments

### Development Server

```bash
cd /opt/oai-to-circuit
git checkout develop
git pull origin develop
systemctl restart oai-to-circuit-dev
```

### Staging Server

```bash
cd /opt/oai-to-circuit
git checkout staging
git pull origin staging
# Run additional tests
pytest
systemctl restart oai-to-circuit-staging
```

### Production Server

```bash
cd /opt/oai-to-circuit
git checkout main
git pull origin main
# Extra caution: backup first
cp /var/lib/oai-to-circuit/quota.db /backup/quota.db.$(date +%Y%m%d_%H%M%S)
systemctl restart oai-to-circuit
# Monitor closely after deployment
journalctl -u oai-to-circuit -f
```

## Post-Deployment Monitoring

After deploying, monitor for 10-15 minutes:

```bash
# Watch logs in real-time
sudo journalctl -u oai-to-circuit -f

# In another terminal, watch requests
watch -n 5 'sudo journalctl -u oai-to-circuit --since "5 minutes ago" | grep "Processing request"'

# Check quota database
sqlite3 /var/lib/oai-to-circuit/quota.db "SELECT subkey, model, requests FROM usage ORDER BY requests DESC LIMIT 10;"

# Check Splunk (if configured)
# Navigate to Splunk and run:
# index=main sourcetype=llm:usage | timechart count
```

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
nano /etc/oai-to-circuit/credentials.env
# Add: NEW_VAR=value
systemctl restart oai-to-circuit
```

### Scenario 4: Quota Configuration Update

```bash
# Update quotas.json locally, commit, push
# On server:
cd /opt/oai-to-circuit
git pull
cp quotas.json /etc/oai-to-circuit/quotas.json
systemctl restart oai-to-circuit
```

### Scenario 5: Systemd Service Update

```bash
cd /opt/oai-to-circuit
git pull
cp oai-to-circuit.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart oai-to-circuit
```

## Troubleshooting Deployments

### Service won't start after update

```bash
# Check logs
sudo journalctl -u oai-to-circuit -n 100

# Common issues:
# - Syntax error in Python code (rollback)
# - Missing dependency (pip3 install -r requirements.txt)
# - Permission issue (chown -R oai-bridge:oai-bridge /opt/oai-to-circuit)
```

### Quota database corruption

```bash
# Restore from backup
sudo systemctl stop oai-to-circuit
sudo cp /var/lib/oai-to-circuit/backups/quota.db.20240101_120000 /var/lib/oai-to-circuit/quota.db
sudo chown oai-bridge:oai-bridge /var/lib/oai-to-circuit/quota.db
sudo systemctl start oai-to-circuit
```

### Git conflicts on server

```bash
# If local changes on server conflict with remote:
cd /opt/oai-to-circuit
git stash  # Save any local changes
git pull origin main
git stash pop  # Re-apply local changes (may need manual merge)
```

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

## CI/CD Integration (Future)

Example GitHub Actions workflow (`.github/workflows/deploy.yml`):

```yaml
name: Deploy to Production

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SSH_PRIVATE_KEY }}
          script: |
            cd /opt/oai-to-circuit
            git pull origin main
            pip3 install -r requirements.txt --upgrade
            systemctl restart oai-to-circuit
            sleep 3
            curl -f http://localhost:12000/health || exit 1
```

## Support

For deployment issues:
1. Check logs: `sudo journalctl -u oai-to-circuit -n 100`
2. Verify configuration: `sudo cat /etc/oai-to-circuit/credentials.env`
3. Test manually: `python3 /opt/oai-to-circuit/rewriter.py` (as oai-bridge user)
4. Rollback if needed: `git reset --hard <previous-commit>`

