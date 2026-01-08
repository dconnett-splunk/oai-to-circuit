# Subkey Names Setup Guide

This guide walks you through setting up friendly names for your subkeys and ensuring they're exported to Splunk HEC.

## What Changed

We've added support for friendly names throughout the system:

1. **Database**: The `subkey_names` table is now automatically created by `QuotaManager`
2. **QuotaManager**: New `get_friendly_name()` method to look up names
3. **SplunkHEC**: Events now include a `friendly_name` field when available
4. **App**: Automatically looks up and includes names in all HEC events
5. **Backfill**: The backfill script now includes names when re-sending historical data

## Quick Start

### Step 1: Check Current State

Run the check script to see which subkeys are active and which ones need names:

```bash
# For local development
python check_and_setup_names.py --local

# For production (default path: /var/lib/oai-to-circuit/quota.db)
python check_and_setup_names.py

# Or specify a custom database path
python check_and_setup_names.py --db /path/to/quota.db
```

This will show you:
- ✓ Whether the `subkey_names` table exists (it should now be auto-created)
- All active subkeys from the usage table
- Which ones have names and which ones don't
- Commands to add names to unnamed keys

### Step 2: Add Names to Active Keys

For each active subkey without a name, run:

```bash
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "your_actual_subkey_here" \
  --name "Friendly Name (Team)" \
  --email "user@example.com" \
  --description "Optional description"
```

**Examples:**

```bash
# Example 1: Dave from FIE team
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave (FIE Team)" \
  --email "dave@example.com" \
  --description "Field Innovation Engineering"

# Example 2: ML Team
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "team_ml_xK9pLm3nQr8sT2vW5yZ1aB4cD7eF0gH6" \
  --name "ML Team" \
  --email "ml-team@example.com" \
  --description "Machine Learning Research"
```

### Step 3: Verify Names Were Added

List all name mappings:

```bash
python add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db
```

Or run the check script again:

```bash
python check_and_setup_names.py
```

### Step 4: Restart the Service (if needed)

If you're running the service, restart it to ensure it picks up the new database schema:

```bash
sudo systemctl restart oai-to-circuit
```

Check the logs to verify it's working:

```bash
sudo journalctl -u oai-to-circuit -f
```

### Step 5: Verify HEC Events Include Names

Make a test request and check the Splunk HEC logs. You should see the `friendly_name` field in the events:

```json
{
  "subkey": "sha256:1a2b3c4d5e6f7890",
  "friendly_name": "Dave (FIE Team)",
  "model": "gpt-4o-mini",
  "requests": 1,
  "prompt_tokens": 150,
  "completion_tokens": 50,
  "total_tokens": 200,
  "timestamp": "2026-01-08T12:34:56.789Z"
}
```

## Managing Names

### List All Mappings

```bash
python add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db
```

### Update an Existing Name

Just run the `--add` command again with the same subkey:

```bash
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave Smith (FIE)" \
  --email "dave.smith@example.com" \
  --description "Updated description"
```

### Remove a Name Mapping

```bash
python add_subkey_names_table.py --remove \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g"
```

## Backfilling Historical Data

If you want to re-send historical HEC events with the new friendly names:

```bash
# Extract recent logs
sudo journalctl -u oai-to-circuit --since "2 days ago" > recent_logs.txt

# Backfill with names (dry run first)
python backfill_hec.py --dry-run < recent_logs.txt

# Actually send the data
python backfill_hec.py < recent_logs.txt
```

The backfill script will now automatically look up and include friendly names for each subkey.

## SQLite Stored Procedures?

**Answer**: No, SQLite does not support stored procedures like PostgreSQL or MySQL. However, we don't need them! 

Instead, we use:
- Python methods in `QuotaManager` for business logic
- Simple SQL queries with JOINs for reports
- SQLite triggers if we need database-level automation (not needed yet)

## Splunk Dashboard Updates

Your Splunk dashboard can now use the `friendly_name` field for better reporting:

```spl
index=oai_circuit sourcetype="llm:usage"
| stats sum(total_tokens) as total_tokens, sum(requests) as requests by friendly_name, model
| sort -total_tokens
```

If you want to show the name when available, or fall back to the hashed subkey:

```spl
index=oai_circuit sourcetype="llm:usage"
| eval display_name=coalesce(friendly_name, subkey)
| stats sum(total_tokens) as total_tokens, sum(requests) as requests by display_name, model
| sort -total_tokens
```

See which users need names added:

```spl
index=oai_circuit sourcetype="llm:usage"
| eval has_name=if(isnotnull(friendly_name), "Has Name", "Needs Name")
| stats sum(total_tokens) as tokens, sum(requests) as requests by subkey, has_name
| where has_name="Needs Name"
| sort -tokens
```

## Troubleshooting

### Table doesn't exist

The `subkey_names` table is now automatically created when the service starts. If you're using an old database, just restart the service or run:

```bash
python add_subkey_names_table.py --init --db /var/lib/oai-to-circuit/quota.db
```

### Names not showing up in HEC events

1. Check that names are in the database:
   ```bash
   sqlite3 /var/lib/oai-to-circuit/quota.db "SELECT * FROM subkey_names;"
   ```

2. Restart the service:
   ```bash
   sudo systemctl restart oai-to-circuit
   ```

3. Check logs for errors:
   ```bash
   sudo journalctl -u oai-to-circuit -n 100
   ```

### Permission denied on database

Make sure the database file is readable by the service:

```bash
sudo chown oai-bridge:oai-bridge /var/lib/oai-to-circuit/quota.db
sudo chmod 640 /var/lib/oai-to-circuit/quota.db
```

## Security Notes

- **Subkeys are still hashed** in Splunk HEC exports (using SHA-256)
- **Friendly names are NOT hashed** - they're meant to be human-readable
- Store friendly names that are appropriate for your logging/monitoring system
- Don't include sensitive information in friendly names
- The raw subkeys are only in your local database, never in Splunk

## Next Steps

1. Run `check_and_setup_names.py` to see current state
2. Add names for all active subkeys
3. Restart the service if needed
4. Update your Splunk dashboards to use the `friendly_name` field
5. Consider backfilling historical data if you want names in old events

## Files Changed

- `oai_to_circuit/quota.py` - Added `get_friendly_name()` method and auto-creates table
- `oai_to_circuit/splunk_hec.py` - Added `friendly_name` parameter to events
- `oai_to_circuit/app.py` - Looks up and passes names to HEC
- `backfill_hec.py` - Includes names when backfilling
- `check_and_setup_names.py` - New script to check current state
- `add_subkey_names_table.py` - Existing script (unchanged)

All changes are backward compatible - if no name is found, the system continues to work as before.

