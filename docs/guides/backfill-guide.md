# Backfill Guide

> **Navigation:** [Documentation Home](../README.md) | [Guides](../guides/) | [Operations](../operations/)

Guide for backfilling historical usage data to Splunk HEC and managing data migrations.

---

## Table of Contents

- [Overview](#overview)
- [Backfilling HEC Events](#backfilling-hec-events)
- [Database Migration for Email Support](#database-migration-for-email-support)
- [Backfilling with Email Field](#backfilling-with-email-field)
- [True-Up and Data Reconciliation](#true-up-and-data-reconciliation)
- [Troubleshooting](#troubleshooting)

---

## Overview

Backfilling is the process of re-sending historical usage data to Splunk HEC or updating the local database with new fields. This is useful when:

- Adding new fields to Splunk events (e.g., `friendly_name`, `email`)
- Fixing bugs in token tracking or cost calculations
- Reconciling data gaps between local DB and Splunk
- Migrating database schema with new columns

---

## Backfilling HEC Events

### Purpose

Re-send historical usage data from application logs to Splunk HEC with updated fields or corrected data.

### Prerequisites

1. **Splunk HEC configured** in `credentials.env`:
   ```bash
   SPLUNK_HEC_URL=https://splunk.example.com:8088/services/collector/event
   SPLUNK_HEC_TOKEN=your-token-here
   ```

2. **Application logs available** via journalctl or log files

### Basic Backfill

**Extract recent logs:**

```bash
sudo journalctl -u oai-to-circuit --since "2 days ago" > recent_logs.txt
```

**Dry run (preview without sending):**

```bash
python backfill_hec.py --dry-run < recent_logs.txt
```

**Actually send the data:**

```bash
python backfill_hec.py < recent_logs.txt
```

### Backfill from Specific Date Range

```bash
# Extract logs from specific date range
sudo journalctl -u oai-to-circuit \
  --since "2026-01-01" \
  --until "2026-01-31" > january_logs.txt

# Backfill
python backfill_hec.py < january_logs.txt
```

### Backfill with Friendly Names

The backfill script automatically looks up friendly names from the `subkey_names` table:

```bash
# First, ensure names are set up (if not already)
python check_and_setup_names.py
python add_subkey_names_table.py --add \
  --subkey "your_key" \
  --name "User Name" \
  --email "user@example.com"

# Extract logs
sudo journalctl -u oai-to-circuit --since "2 days ago" > recent_logs.txt

# Backfill (will include friendly_name and email fields)
python backfill_hec.py < recent_logs.txt
```

---

## Database Migration for Email Support

### Adding Email Field to subkey_names Table

The database schema was updated to include an `email` field in the `subkey_names` table. If you have an existing database, you need to run a migration.

### Migration Script

The `add_subkey_names_table.py` script automatically handles the migration:

```bash
# Check if migration is needed
python add_subkey_names_table.py --list

# If you see an error about missing 'email' column, run:
python add_subkey_names_table.py --migrate

# Or for production database:
python add_subkey_names_table.py --migrate --db /var/lib/oai-to-circuit/quota.db
```

### Manual Migration (Advanced)

If you need to manually add the email column:

```bash
sqlite3 /var/lib/oai-to-circuit/quota.db <<EOF
-- Add email column if it doesn't exist
ALTER TABLE subkey_names ADD COLUMN email TEXT;

-- Verify
.schema subkey_names
EOF
```

### Verify Migration

```bash
python add_subkey_names_table.py --list --db /var/lib/oai-to-circuit/quota.db
```

Expected schema:
```sql
CREATE TABLE subkey_names (
    subkey TEXT PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    email TEXT,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Backfilling with Email Field

### Step-by-Step Process

**Step 1: Run Migration**

```bash
python add_subkey_names_table.py --migrate --db /var/lib/oai-to-circuit/quota.db
```

**Step 2: Add Email to Existing Mappings**

```bash
# Update existing mappings with email addresses
python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave (FIE Team)" \
  --email "dave@example.com" \
  --description "Field Innovation Engineering"

python add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "team_alpha_kL9pX2mN7vR4tQ8wY1zJ5hF3" \
  --name "Team Alpha" \
  --email "team-alpha@example.com" \
  --description "Development Team"
```

**Step 3: Extract Historical Logs**

```bash
# Extract logs from the time period you want to backfill
sudo journalctl -u oai-to-circuit \
  --since "2026-01-01" \
  --until "2026-01-15" > january_first_half.txt
```

**Step 4: Backfill with Email**

```bash
# The backfill script will now include email field from subkey_names
python backfill_hec.py < january_first_half.txt
```

**Step 5: Verify in Splunk**

```spl
index=oai_circuit sourcetype="llm:usage" 
| where isnotnull(email)
| table _time, friendly_name, email, model, total_tokens
| head 10
```

### Backfill Script with Custom Options

```bash
# Backfill with specific date override
python backfill_hec.py \
  --date 2026-01-15 \
  --db /var/lib/oai-to-circuit/quota.db \
  < logs.txt

# Dry run with verbose output
python backfill_hec.py --dry-run --verbose < logs.txt
```

---

## True-Up and Data Reconciliation

### When to Use True-Up

Use the true-up process when you need to reconcile data discrepancies between:
- Azure API reported usage (source of truth)
- Splunk HEC logged usage
- Local database usage

See the [True-Up Guide](trueup-guide.md) for detailed information on reconciling usage data.

### Quick True-Up Process

**Step 1: Identify Discrepancies**

Compare Azure API data with Splunk:

```spl
index=oai_circuit sourcetype="llm:usage" 
  earliest="2026-01-01T00:00:00" 
  latest="2026-02-01T00:00:00"
| eval month=strftime(_time, "%Y-%m-01")
| stats 
    sum(total_tokens) as "Total Tokens"
    sum(prompt_tokens) as "Prompt Tokens"
    sum(completion_tokens) as "Completion Tokens"
    by model, month
| eval tier="prem_tier"
| rename model as "Model", month as "Month", tier as "Tier"
| table "Model" "Month" "Tier" "Total Tokens" "Prompt Tokens" "Completion Tokens"
| sort - "Total Tokens"
```

**Step 2: Create Correction Events**

Use the backfill script to send correction events:

```python
# Example: backfill_january_2026.py
from oai_to_circuit.splunk_hec import SplunkHEC
import os

# Load config
hec = SplunkHEC(
    url=os.getenv("SPLUNK_HEC_URL"),
    token=os.getenv("SPLUNK_HEC_TOKEN")
)

# Send correction event
hec.send_usage_event(
    subkey="egai-prd-sales-backfill",
    model="gpt-4o-mini",
    requests=0,  # Don't inflate request count
    prompt_tokens=0,
    completion_tokens=0,
    total_tokens=3683,  # Missing token count
    timestamp="2026-01-15T00:00:00Z",
    backfill=True  # Mark as backfill
)
```

**Step 3: Verify Corrections**

```spl
index=oai_circuit sourcetype="llm:usage" backfill=true
| table _time, model, total_tokens
```

---

## Troubleshooting

### Backfill Events Not Appearing in Splunk

**1. Check HEC connectivity:**

```bash
curl -k "https://your-splunk:8088/services/collector/health"
```

**2. Check the script output for errors:**

```bash
python backfill_hec.py --verbose < logs.txt
```

**3. Search for backfill events:**

```spl
index=oai_circuit sourcetype="llm:usage" backfill=true
```

**4. Check Splunk indexer logs** for any ingestion errors

### Database Migration Fails

**"Table already exists" error:**

The migration is safe to re-run. If you see this error, the table already has the schema.

**"Database is locked" error:**

Stop the service temporarily:

```bash
sudo systemctl stop oai-to-circuit
python add_subkey_names_table.py --migrate
sudo systemctl start oai-to-circuit
```

### Email Field Not Showing in Splunk

**1. Verify email is in database:**

```bash
sqlite3 /var/lib/oai-to-circuit/quota.db \
  "SELECT subkey, friendly_name, email FROM subkey_names;"
```

**2. Restart service to pick up new schema:**

```bash
sudo systemctl restart oai-to-circuit
```

**3. Make a new request and check:**

```spl
index=oai_circuit sourcetype="llm:usage" 
| where isnotnull(email)
| table _time, friendly_name, email
| head 1
```

### Numbers Still Don't Match After True-Up

**Expected variance:**
- Splunk captures real-time usage
- Azure API reports may be delayed
- Splunk should show MORE data than Azure (more up-to-date)

**Only backfill if:**
- Splunk shows LESS data than Azure (missing events)
- There was a known bug during that time period
- You need to add missing fields (friendly_name, email)

### Duplicate Events in Splunk

Backfill events are marked with `backfill=true`. To exclude duplicates:

```spl
index=oai_circuit sourcetype="llm:usage" backfill!=true
| stats sum(total_tokens) by model
```

Or to see only original events (exclude backfills):

```spl
index=oai_circuit sourcetype="llm:usage" 
| where isnull(backfill) OR backfill=false
| stats sum(total_tokens) by model
```

---

## Best Practices

### Before Backfilling

1. **Always run with --dry-run first** to preview what will be sent
2. **Backup your database** before schema migrations
3. **Extract logs to a file** rather than piping journalctl directly
4. **Verify HEC connectivity** before large backfills

### During Backfilling

5. **Monitor Splunk ingestion** for errors or slowdowns
6. **Rate limit large backfills** to avoid overwhelming HEC
7. **Mark backfill events** with `backfill=true` for tracking
8. **Use specific date ranges** rather than "since beginning of time"

### After Backfilling

9. **Verify data arrived** in Splunk with queries
10. **Compare totals** with expected numbers
11. **Document what was backfilled** and why
12. **Clean up temporary log files** to save disk space

---

## Common Backfill Scenarios

### Scenario 1: Add Friendly Names to Historical Data

```bash
# 1. Add name mappings
python add_subkey_names_table.py --add \
  --subkey "user_key" \
  --name "User Name" \
  --email "user@example.com"

# 2. Extract last week's logs
sudo journalctl -u oai-to-circuit --since "7 days ago" > last_week.txt

# 3. Backfill
python backfill_hec.py < last_week.txt
```

### Scenario 2: Fix Missing Token Counts

```bash
# Extract logs from the affected time period
sudo journalctl -u oai-to-circuit \
  --since "2026-01-10" \
  --until "2026-01-12" > fix_tokens.txt

# Backfill with corrected data
python backfill_hec.py < fix_tokens.txt
```

### Scenario 3: Migrate to New Schema

```bash
# 1. Stop service
sudo systemctl stop oai-to-circuit

# 2. Backup database
cp /var/lib/oai-to-circuit/quota.db /backup/quota.db.$(date +%Y%m%d)

# 3. Run migration
python add_subkey_names_table.py --migrate --db /var/lib/oai-to-circuit/quota.db

# 4. Add email to existing mappings
python add_subkey_names_table.py --add \
  --subkey "key1" --name "Name1" --email "email1@example.com"

# 5. Start service
sudo systemctl start oai-to-circuit

# 6. Backfill recent data with new fields
sudo journalctl -u oai-to-circuit --since "1 day ago" > recent.txt
python backfill_hec.py < recent.txt
```

---

## Related Documentation

- [True-Up Guide](trueup-guide.md) - Reconciling usage data with Azure API
- [Subkey Management](../operations/subkey-management.md) - Managing subkeys and friendly names
- [Diagnostic Logging](../operations/diagnostic-logging.md) - Troubleshooting with logs
- [Database Queries](../operations/database-queries.md) - SQL query examples

---

**For data reconciliation**, see the [True-Up Guide](trueup-guide.md).

**For Splunk dashboard setup**, see [Dashboard Features](../operations/dashboard-features.md).

