# Installation Guide

> **Navigation:** [Documentation Home](../README.md) | [Getting Started](./) | [Quick Start](quickstart.md)

> **Note**: This guide covers initial installation from scratch. For deploying updates to an existing installation, see [Deployment Guide](../deployment/deployment-guide.md).

## Systemd Service Installation

### Prerequisites

- Python 3.9 or higher
- systemd-based Linux distribution (RHEL, Ubuntu, Debian, etc.)
- Root or sudo access

### Step 1: Create System User

```bash
sudo useradd -r -s /bin/false -d /opt/oai-to-circuit oai-bridge
```

### Step 2: Install Application

```bash
# Create directories
sudo mkdir -p /opt/oai-to-circuit
sudo mkdir -p /var/lib/oai-to-circuit
sudo mkdir -p /etc/oai-to-circuit
sudo mkdir -p /var/log/oai-to-circuit

# Copy application files
sudo cp -r /path/to/oai-to-circuit/* /opt/oai-to-circuit/

# Install Python dependencies
cd /opt/oai-to-circuit
sudo pip3 install -r requirements.txt

# Set ownership
sudo chown -R oai-bridge:oai-bridge /opt/oai-to-circuit
sudo chown -R oai-bridge:oai-bridge /var/lib/oai-to-circuit
sudo chown -R oai-bridge:oai-bridge /var/log/oai-to-circuit
sudo chown -R root:oai-bridge /etc/oai-to-circuit
sudo chmod 750 /etc/oai-to-circuit
```

### Step 3: Configure Credentials

Create `/etc/oai-to-circuit/credentials.env`:

```bash
# Circuit API credentials (REQUIRED)
CIRCUIT_CLIENT_ID=your_client_id_here
CIRCUIT_CLIENT_SECRET=your_client_secret_here
CIRCUIT_APPKEY=your_app_key_here

# Splunk HEC (optional - for usage metrics)
SPLUNK_HEC_URL=https://splunk.example.com:8088/services/collector/event
SPLUNK_HEC_TOKEN=your_hec_token_here
```

**Secure the credentials file:**

```bash
sudo chmod 640 /etc/oai-to-circuit/credentials.env
sudo chown root:oai-bridge /etc/oai-to-circuit/credentials.env
```

### Step 4: Configure Quotas

Copy and edit the quotas file:

```bash
sudo cp /opt/oai-to-circuit/quotas.json.example /etc/oai-to-circuit/quotas.json
sudo vi /etc/oai-to-circuit/quotas.json
sudo chmod 640 /etc/oai-to-circuit/quotas.json
sudo chown root:oai-bridge /etc/oai-to-circuit/quotas.json
```

### Step 5: Install Systemd Unit

```bash
sudo cp /opt/oai-to-circuit/oai-to-circuit.service /etc/systemd/system/
sudo systemctl daemon-reload
```

### Step 6: Enable and Start Service

```bash
# Enable service to start on boot
sudo systemctl enable oai-to-circuit

# Start service now
sudo systemctl start oai-to-circuit

# Check status
sudo systemctl status oai-to-circuit
```

## Service Management

### View Logs

```bash
# Follow live logs
sudo journalctl -u oai-to-circuit -f

# View recent logs
sudo journalctl -u oai-to-circuit -n 100

# View logs since last boot
sudo journalctl -u oai-to-circuit -b
```

### Restart Service

```bash
sudo systemctl restart oai-to-circuit
```

### Stop Service

```bash
sudo systemctl stop oai-to-circuit
```

### Disable Service

```bash
sudo systemctl disable oai-to-circuit
```

## HTTPS Configuration (Optional)

For HTTPS support, generate certificates and update the systemd service:

```bash
# Generate self-signed cert (development)
cd /opt/oai-to-circuit
sudo -u oai-bridge python3 generate_cert.py

# Or copy your CA-signed certificates
sudo cp /path/to/cert.pem /etc/oai-to-circuit/cert.pem
sudo cp /path/to/key.pem /etc/oai-to-circuit/key.pem
sudo chown oai-bridge:oai-bridge /etc/oai-to-circuit/*.pem
sudo chmod 600 /etc/oai-to-circuit/key.pem
sudo chmod 644 /etc/oai-to-circuit/cert.pem
```

Edit the systemd unit file to use SSL:

```bash
sudo vi /etc/systemd/system/oai-to-circuit.service
```

Change the `ExecStart` line to:

```
ExecStart=/usr/bin/python3 /opt/oai-to-circuit/rewriter.py --ssl
```

Then reload and restart:

```bash
sudo systemctl daemon-reload
sudo systemctl restart oai-to-circuit
```

## Firewall Configuration

Open the required ports:

```bash
# HTTP (port 12000)
sudo firewall-cmd --permanent --add-port=12000/tcp

# HTTPS (port 12443) - if using SSL
sudo firewall-cmd --permanent --add-port=12443/tcp

# Reload firewall
sudo firewall-cmd --reload
```

For Ubuntu/Debian using ufw:

```bash
sudo ufw allow 12000/tcp
sudo ufw allow 12443/tcp  # if using SSL
```

## Health Check

Verify the service is running:

```bash
curl http://localhost:12000/health
```

Expected response:

```json
{
  "status": "healthy",
  "service": "OpenAI to Circuit Bridge",
  "credentials_configured": true,
  "appkey_configured": true
}
```

## Splunk HEC Integration

When `SPLUNK_HEC_URL` and `SPLUNK_HEC_TOKEN` are configured, the bridge will automatically send usage metrics to Splunk.

### Splunk Event Format

Events are sent as JSON with the following structure:

```json
{
  "time": 1703001234.567,
  "event": {
    "subkey": "team_member_alice",
    "model": "gpt-4o-mini",
    "requests": 1,
    "prompt_tokens": 150,
    "completion_tokens": 200,
    "total_tokens": 350,
    "timestamp": "2024-12-18T10:30:45.123456Z"
  },
  "source": "oai-to-circuit",
  "sourcetype": "llm:usage",
  "index": "main"
}
```

### Create Splunk HEC Token

1. Log in to Splunk Web
2. Navigate to **Settings > Data Inputs > HTTP Event Collector**
3. Click **New Token**
4. Configure:
   - Name: `oai-to-circuit-metrics`
   - Source type: `llm:usage`
   - Index: `main` (or your preferred index)
5. Copy the generated token to `/etc/oai-to-circuit/credentials.env`

## Troubleshooting

### Service fails to start

Check logs for errors:

```bash
sudo journalctl -u oai-to-circuit -n 50
```

Common issues:
- Missing credentials in `/etc/oai-to-circuit/credentials.env`
- Permission issues on `/var/lib/oai-to-circuit`
- Python dependencies not installed
- Ports already in use

### Quota database locked

If the database is locked:

```bash
sudo systemctl stop oai-to-circuit
sudo rm /var/lib/oai-to-circuit/quota.db-journal
sudo systemctl start oai-to-circuit
```

### Splunk metrics not appearing

Check Splunk HEC connectivity:

```bash
curl -k https://splunk.example.com:8088/services/collector/event \
  -H "Authorization: Splunk YOUR_HEC_TOKEN" \
  -d '{"event": "test"}'
```

Enable debug logging to see HEC requests:

```bash
# Add to /etc/oai-to-circuit/credentials.env
LOGLEVEL=DEBUG
```

## Monitoring

Monitor service health with systemd:

```bash
# Check if service is running
systemctl is-active oai-to-circuit

# Check if service is enabled
systemctl is-enabled oai-to-circuit

# Get detailed status
systemctl status oai-to-circuit
```

Set up monitoring alerts for service failures:

```bash
# Example: Send email on service failure
sudo vi /etc/systemd/system/oai-to-circuit-alert@.service
```

## Backup

Regularly backup the quota database:

```bash
# Manual backup
sudo cp /var/lib/oai-to-circuit/quota.db /backup/quota.db.$(date +%Y%m%d)

# Automated daily backup (crontab)
0 2 * * * cp /var/lib/oai-to-circuit/quota.db /backup/quota.db.$(date +\%Y\%m\%d)
```

---

## Related Documentation

- [Quick Start Guide](quickstart.md) - Get started in 5 minutes
- [Production Setup](production-setup.md) - Production best practices
- [Deployment Guide](../deployment/deployment-guide.md) - Deploying updates
- [Architecture Overview](../architecture/architecture.md) - System design
- [Subkey Management](../operations/subkey-management.md) - Managing API keys

**[← Back to Documentation Home](../README.md)**

