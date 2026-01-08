# Migration Guide: Adding Email Field to subkey_names

## What Changed

We've added an optional `email` field to the `subkey_names` table to make it easier to contact users or identify them in reports.

## Do I Need to Migrate?

**If you already have the `subkey_names` table:**

SQLite will **not** automatically add the new column to existing tables. You need to either:
1. Add the column manually (recommended)
2. Drop and recreate the table (loses data)

**If you don't have the table yet:**

Just run the init command and you'll get the new schema automatically:

```bash
sudo python3 add_subkey_names_table.py --init --db /var/lib/oai-to-circuit/quota.db
```

## Migration Steps (For Existing Tables)

### Step 1: Check if you have the email column

```bash
sudo sqlite3 /var/lib/oai-to-circuit/quota.db ".schema subkey_names"
```

If you see `email TEXT` in the output, you're already migrated! Otherwise, continue.

### Step 2: Add the email column

```bash
sudo sqlite3 /var/lib/oai-to-circuit/quota.db \
  "ALTER TABLE subkey_names ADD COLUMN email TEXT;"
```

### Step 3: Verify it worked

```bash
sudo sqlite3 /var/lib/oai-to-circuit/quota.db ".schema subkey_names"
```

You should now see:

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

### Step 4: (Optional) Add emails to existing entries

```bash
# Update an existing entry with an email
sudo python3 add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "David Connett" \
  --email "dconnett@example.com" \
  --description "Lead Developer"
```

This will update the existing entry with the email (the `ON CONFLICT` clause handles updates).

## No Downtime Required

The migration is backward compatible:
- Old code will ignore the email column
- New code handles NULL emails gracefully
- No service restart needed for the migration itself

## Rollback

If you need to remove the email column (unlikely):

```bash
# SQLite doesn't support DROP COLUMN in old versions
# You'd need to recreate the table without the email field
# (Not recommended unless absolutely necessary)
```

## Complete Example

```bash
# 1. Check current schema
sudo sqlite3 /var/lib/oai-to-circuit/quota.db ".schema subkey_names"

# 2. Add email column if missing
sudo sqlite3 /var/lib/oai-to-circuit/quota.db \
  "ALTER TABLE subkey_names ADD COLUMN email TEXT;"

# 3. Verify
sudo sqlite3 /var/lib/oai-to-circuit/quota.db ".schema subkey_names"

# 4. Add your entry with email
sudo python3 add_subkey_names_table.py --add \
  --db /var/lib/oai-to-circuit/quota.db \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "David Connett" \
  --email "dconnett@cisco.com" \
  --description "Lead Developer"

# 5. Verify it's there
sudo python3 add_subkey_names_table.py --list \
  --db /var/lib/oai-to-circuit/quota.db
```

## Future Deployments

When you restart the service or deploy to a new server:
- The QuotaManager will create the table with the email field automatically
- No manual migration needed on fresh installs
- Existing tables on running servers need the manual migration above

