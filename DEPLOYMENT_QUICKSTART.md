# Deployment Quick Start

Quick reference for deploying the OpenAI to Circuit Bridge with systemd.

## Prerequisites

- Linux system with systemd
- Python 3.9+
- Root/sudo access

## Quick Install

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
sudo nano /etc/oai-to-circuit/credentials.env  # Edit with your credentials
sudo chmod 640 /etc/oai-to-circuit/credentials.env

# 5. Configure quotas (optional)
sudo cp quotas.json.example /etc/oai-to-circuit/quotas.json
sudo nano /etc/oai-to-circuit/quotas.json  # Edit quota rules
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

## Essential Commands

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
sudo nano /etc/oai-to-circuit/credentials.env
sudo systemctl restart oai-to-circuit

# View recent logs
sudo journalctl -u oai-to-circuit -n 100
```

## Firewall (if needed)

```bash
# RHEL/CentOS/Fedora
sudo firewall-cmd --permanent --add-port=12000/tcp
sudo firewall-cmd --permanent --add-port=12443/tcp  # if using HTTPS
sudo firewall-cmd --reload

# Ubuntu/Debian
sudo ufw allow 12000/tcp
sudo ufw allow 12443/tcp  # if using HTTPS
```

## HTTPS Setup (Optional)

```bash
# Generate self-signed cert (development)
cd /opt/oai-to-circuit
sudo -u oai-bridge python3 generate_cert.py

# Or copy CA-signed certificates
sudo cp /path/to/cert.pem /etc/oai-to-circuit/cert.pem
sudo cp /path/to/key.pem /etc/oai-to-circuit/key.pem
sudo chown oai-bridge:oai-bridge /etc/oai-to-circuit/*.pem
sudo chmod 600 /etc/oai-to-circuit/key.pem

# Edit service to use SSL
sudo nano /etc/systemd/system/oai-to-circuit.service
# Change ExecStart line to: ExecStart=/usr/bin/python3 /opt/oai-to-circuit/rewriter.py --ssl

sudo systemctl daemon-reload
sudo systemctl restart oai-to-circuit
```

## Splunk HEC Setup (Optional)

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

## Troubleshooting

### Service won't start
```bash
# Check logs for errors
sudo journalctl -u oai-to-circuit -n 50

# Common issues:
# - Missing credentials in /etc/oai-to-circuit/credentials.env
# - Permission issues on /var/lib/oai-to-circuit
# - Port already in use
```

### Check if running
```bash
sudo systemctl is-active oai-to-circuit
curl http://localhost:12000/health
```

### Database locked
```bash
sudo systemctl stop oai-to-circuit
sudo rm /var/lib/oai-to-circuit/quota.db-journal
sudo systemctl start oai-to-circuit
```

## File Locations

- **Application**: `/opt/oai-to-circuit/`
- **Configuration**: `/etc/oai-to-circuit/credentials.env`
- **Quotas**: `/etc/oai-to-circuit/quotas.json`
- **Database**: `/var/lib/oai-to-circuit/quota.db`
- **Logs**: `journalctl -u oai-to-circuit`
- **Service**: `/etc/systemd/system/oai-to-circuit.service`

## Security Notes

- Credentials file should be mode `640` owned by `root:oai-bridge`
- Service runs as unprivileged user `oai-bridge`
- Database and logs owned by `oai-bridge`
- No hardcoded credentials in code

## Monitoring

```bash
# Real-time monitoring
watch -n 2 'systemctl status oai-to-circuit'

# Check for failures
sudo systemctl is-failed oai-to-circuit

# View all service properties
systemctl show oai-to-circuit
```

For complete documentation, see `INSTALLATION.md` and `ARCHITECTURE.md`.

