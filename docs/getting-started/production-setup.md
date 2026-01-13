# Production Setup: Add Your Name

This is the exact sequence of commands to run on your production system.

## Step 1: Create the Table

```bash
sudo python3 add_subkey_names_table.py --init --db /var/lib/oai-to-circuit/quota.db
```

Expected output:
```
✓ Created subkey_names table in /var/lib/oai-to-circuit/quota.db
```

## Step 2: Add Your Name

```bash
sudo python3 add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "David Connett" \
  --email "dconnett@cisco.com" \
  --description "Lead Developer"
```

Expected output:
```
✓ Mapped 'fie_dave_jhKaCh88...' → 'David Connett' <dconnett@cisco.com>
```

## Step 3: Verify It Worked

```bash
sudo python3 add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db
```

You should see your name in the output.

## Step 4: Check Active Keys

```bash
python3 check_and_setup_names.py --db /var/lib/oai-to-circuit/quota.db
```

This shows all active subkeys and which ones still need names.

## Step 5: Restart the Service

```bash
sudo systemctl restart oai-to-circuit
```

Check logs to verify it started correctly:

```bash
sudo journalctl -u oai-to-circuit -f
```

Look for:
- "Starting OpenAI to Circuit Bridge server"
- No errors about database access

## Step 6: Test It

Make a test request and check the logs:

```bash
sudo journalctl -u oai-to-circuit -n 20 | grep -i "friendly\|HEC EXPORT"
```

You should see your friendly name in the HEC export logs.

## Step 7: Update Splunk Dashboard

Upload the new dashboard to Splunk:

```bash
# Copy the file to your Splunk system, or manually paste it via Splunk Web
cat splunk_dashboard_token_usage.xml
```

In Splunk Web:
1. Go to Dashboards
2. Edit your existing dashboard or create new one
3. Click "Source" and paste the XML
4. Save

## Verification Checklist

- [ ] Table created successfully
- [ ] Your name added successfully
- [ ] Name shows up in `--list` command
- [ ] Service restarted without errors
- [ ] Logs show friendly name in HEC exports
- [ ] Splunk dashboard updated
- [ ] Dashboard shows your friendly name instead of hashed subkey

## Troubleshooting

### Permission Denied

```bash
# Check permissions
ls -la /var/lib/oai-to-circuit/quota.db

# Should be:
# -rw-r----- 1 oai-bridge oai-bridge ... quota.db

# Fix if needed:
sudo chown oai-bridge:oai-bridge /var/lib/oai-to-circuit/quota.db
sudo chmod 640 /var/lib/oai-to-circuit/quota.db
```

### Table Already Exists

This is fine! The `--init` command uses `CREATE TABLE IF NOT EXISTS` so it won't overwrite your existing table.

### Service Won't Restart

```bash
# Check status
sudo systemctl status oai-to-circuit

# View errors
sudo journalctl -u oai-to-circuit -n 100

# Common issues:
# - Database locked: Check if there's a -journal file, remove it
# - Permission issues: Check file ownership
# - Python errors: Check that all code files are in place
```

## Next Steps

After setup:

1. **Add other users' names** using the same `--add` command
2. **Check Splunk** to see your name in reports
3. **Update quotas** if needed using `quotas.json`
4. **Monitor usage** via the dashboard

## Quick Reference

```bash
# List all names
sudo python3 add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db

# Add/update a name
sudo python3 add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "YOUR_KEY" \
  --name "Your Name" \
  --email "you@example.com" \
  --description "Description"

# Remove a name
sudo python3 add_subkey_names_table.py --remove \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "YOUR_KEY"

# Check active keys
python3 check_and_setup_names.py --db /var/lib/oai-to-circuit/quota.db

# View service logs
sudo journalctl -u oai-to-circuit -f

# Restart service
sudo systemctl restart oai-to-circuit
```

