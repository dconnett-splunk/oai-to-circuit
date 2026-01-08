# Summary of Changes: Friendly Names for Subkeys in HEC Events

## Overview

All changes have been completed to support friendly names for subkeys throughout the system, including automatic export to Splunk HEC events.

## Questions Answered

### 1. Does SQLite support stored procedures?

**No**, SQLite does not support stored procedures in the traditional sense like PostgreSQL or MySQL. However, this is not a limitation for our use case:

- We use Python methods in the `QuotaManager` class for business logic
- We use simple SQL queries with JOINs for reporting
- We can use SQLite triggers if needed for database-level automation (not currently needed)
- We can create Python functions and register them with SQLite using `create_function()` if needed

### 2. Did we add the names table to existing databases?

**Yes**, the `subkey_names` table is now automatically created:

- The `QuotaManager._init_db()` method now creates the `subkey_names` table on startup
- This means any existing database will get the table when the service restarts
- The table includes an index on `friendly_name` for fast lookups
- No manual migration needed - it's backward compatible

### 3. How to check active keys and attach names?

**Use the new `check_and_setup_names.py` script**:

```bash
# Check current state
python check_and_setup_names.py

# Add names to keys
python add_subkey_names_table.py --add \
  --subkey "your_key_here" \
  --name "Friendly Name" \
  --description "Description"
```

### 4. Are names exported to HEC?

**Yes**, all HEC events now include friendly names when available:

- Usage events include `friendly_name` field
- Error events include `friendly_name` field
- Backfill script includes names when re-sending historical data
- Names are looked up automatically - no manual intervention needed

## Files Modified

### 1. `oai_to_circuit/quota.py`
- ✅ Added automatic creation of `subkey_names` table in `_init_db()`
- ✅ Added `get_friendly_name(subkey)` method to look up names
- ✅ Creates index on `friendly_name` for performance

### 2. `oai_to_circuit/splunk_hec.py`
- ✅ Added `friendly_name` parameter to `send_usage_event()`
- ✅ Added `friendly_name` parameter to `send_error_event()`
- ✅ Includes `friendly_name` in event data when provided

### 3. `oai_to_circuit/app.py`
- ✅ Looks up friendly name before sending usage events
- ✅ Looks up friendly name before sending error events
- ✅ Passes friendly name to HEC client

### 4. `backfill_hec.py`
- ✅ Imports `QuotaManager` to access name lookups
- ✅ Looks up friendly name for each subkey during backfill
- ✅ Passes friendly name to HEC when re-sending events
- ✅ Shows friendly name in console output during backfill

## Files Created

### 1. `check_and_setup_names.py` (NEW)
A utility script to:
- Check if the `subkey_names` table exists
- List all active subkeys from the usage table
- Show which keys have names and which don't
- Provide commands to add names to unnamed keys
- Display summary statistics

Usage:
```bash
python check_and_setup_names.py              # Production DB
python check_and_setup_names.py --local      # Local quota.db
python check_and_setup_names.py --db /path   # Custom path
```

### 2. `SUBKEY_NAMES_SETUP.md` (NEW)
Complete guide covering:
- What changed in the system
- Step-by-step setup instructions
- How to manage names (add, update, remove, list)
- How to backfill historical data with names
- Splunk dashboard query examples
- Troubleshooting guide
- Security notes

## How It Works

### Flow for New Requests

1. User makes request with subkey in header
2. `app.py` processes the request
3. After recording usage, it calls `quota_manager.get_friendly_name(subkey)`
4. If a name exists, it's passed to `splunk_hec.send_usage_event(..., friendly_name=name)`
5. HEC event includes both hashed subkey AND friendly name
6. Splunk can now display reports using human-readable names

### Flow for Backfilling

1. Parse log lines to extract event data
2. For each event, look up friendly name using `quota_manager.get_friendly_name()`
3. Send to HEC with the friendly name included
4. Historical data now has names attached

### Database Schema

```sql
-- Automatically created by QuotaManager
CREATE TABLE IF NOT EXISTS subkey_names (
    subkey TEXT PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    email TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_friendly_name 
ON subkey_names(friendly_name);
```

### Example HEC Event (Before)

```json
{
  "subkey": "sha256:1a2b3c4d5e6f7890",
  "model": "gpt-4o-mini",
  "requests": 1,
  "prompt_tokens": 150,
  "completion_tokens": 50,
  "total_tokens": 200,
  "timestamp": "2026-01-08T12:34:56.789Z"
}
```

### Example HEC Event (After)

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

## Next Steps

### 1. Check Current State
```bash
python check_and_setup_names.py
```

### 2. Add Names to Active Keys
Use the commands provided by the check script, or manually:
```bash
python add_subkey_names_table.py --add \
  --subkey "your_key" \
  --name "Your Name (Team)" \
  --email "your.email@example.com" \
  --description "Description"
```

### 3. Restart Service (if running)
```bash
sudo systemctl restart oai-to-circuit
sudo journalctl -u oai-to-circuit -f
```

### 4. Update Splunk Dashboards
Use the `friendly_name` field in your queries:
```spl
index=oai_circuit sourcetype="llm:usage"
| stats sum(total_tokens) as total_tokens by friendly_name, model
| sort -total_tokens
```

### 5. Backfill Historical Data (Optional)
```bash
sudo journalctl -u oai-to-circuit --since "7 days ago" > logs.txt
python backfill_hec.py < logs.txt
```

## Backward Compatibility

✅ **All changes are backward compatible:**

- If no friendly name exists, the system works as before
- Old databases automatically get the new table on restart
- HEC events without names are still valid
- Existing Splunk queries continue to work
- No breaking changes to any APIs or interfaces

## Testing

To test locally:

1. Create a test database:
   ```bash
   python -c "from oai_to_circuit.quota import QuotaManager; QuotaManager('test.db', {})"
   ```

2. Add a test name:
   ```bash
   python add_subkey_names_table.py --add --db test.db \
     --subkey "test_key_123" --name "Test User"
   ```

3. Verify lookup works:
   ```bash
   python -c "from oai_to_circuit.quota import QuotaManager; qm = QuotaManager('test.db', {}); print(qm.get_friendly_name('test_key_123'))"
   ```

## Security Considerations

- ✅ Subkeys are still hashed (SHA-256) in HEC exports
- ✅ Friendly names are NOT hashed (they're meant to be readable)
- ✅ Raw subkeys never leave your database
- ⚠️ Choose appropriate friendly names for your logging system
- ⚠️ Don't include sensitive information in friendly names

## Performance Impact

- Minimal: Single SELECT query per request (cached by SQLite)
- Index on `friendly_name` ensures fast lookups
- No impact if name doesn't exist (returns None immediately)
- Database connection pooling handled by SQLite

## Monitoring

Check that names are working:

```bash
# View recent HEC events in logs
sudo journalctl -u oai-to-circuit -n 100 | grep "HEC EXPORT"

# Query database directly
sqlite3 /var/lib/oai-to-circuit/quota.db \
  "SELECT u.subkey, n.friendly_name, SUM(u.requests) 
   FROM usage u 
   LEFT JOIN subkey_names n ON u.subkey = n.subkey 
   GROUP BY u.subkey;"
```

## Support

For issues or questions:
1. Check `SUBKEY_NAMES_SETUP.md` for detailed setup guide
2. Run `check_and_setup_names.py` to diagnose issues
3. Check service logs: `sudo journalctl -u oai-to-circuit -n 100`
4. Verify database: `sqlite3 /var/lib/oai-to-circuit/quota.db ".tables"`

