# Database Query Tools - "Stored Procedures" for SQLite

Since SQLite doesn't support stored procedures, we provide two alternatives:

1. **SQL Views** - Pre-defined queries in the database
2. **Python Functions** - Common queries wrapped in easy-to-use commands
3. **Shell Wrapper** - Quick command-line access

## Quick Start

### Option 1: Shell Wrapper (Easiest)

```bash
# Show database summary
./query summary

# Top 10 users
./query top

# Top 20 users
./query top 20

# Details for specific user
./query user "fie_dave%"

# Model usage
./query models

# Users without names
./query nonames

# Run raw SQL
./query sql "SELECT * FROM v_top_users LIMIT 5"
```

### Option 2: Python Script

```bash
# Summary
python3 db_queries.py summary

# Top users
python3 db_queries.py top-users --limit 20

# User details
python3 db_queries.py user-detail "fie_dave%"

# Model usage
python3 db_queries.py model-usage

# Users without names
python3 db_queries.py users-without-names
```

### Option 3: SQL Views (Most Flexible)

First, create the views:

```bash
sudo sqlite3 /var/lib/oai-to-circuit/quota.db < create_views.sql
```

Then query them:

```bash
# Top users
sqlite3 -header -column /var/lib/oai-to-circuit/quota.db \
  "SELECT * FROM v_top_users LIMIT 10;"

# Users without names
sqlite3 -header -column /var/lib/oai-to-circuit/quota.db \
  "SELECT * FROM v_users_without_names;"

# Overall stats
sqlite3 -header -column /var/lib/oai-to-circuit/quota.db \
  "SELECT * FROM v_overall_stats;"

# User details
sqlite3 -header -column /var/lib/oai-to-circuit/quota.db \
  "SELECT * FROM v_user_detail WHERE subkey LIKE 'fie_dave%';"
```

## Available Queries

### 1. Database Summary

Shows overall statistics:
- Total users
- Users with friendly names
- Total models available
- Total requests and tokens
- Average tokens per request

**Usage:**
```bash
./query summary
# or
python3 db_queries.py summary
# or
sqlite3 -header -column $DB "SELECT * FROM v_overall_stats;"
```

**Output:**
```
=== Database Summary ===

Total Users:      3
Users with Names: 1 (33%)
Total Models:     2
Total Requests:   4
Total Tokens:     1,495
Avg Tokens/Req:   373
```

### 2. Top Users

Shows top N users by request count with friendly names.

**Usage:**
```bash
./query top 20
# or
python3 db_queries.py top-users --limit 20
# or
sqlite3 -header -column $DB "SELECT * FROM v_top_users LIMIT 20;"
```

**Output:**
```
=== Top 10 Users by Requests ===

User              Email                   Requests  Tokens  Avg/Req
----------------  ----------------------  --------  ------  -------
David Connett     dconnett@cisco.com      3         835     278.33
fie_tom_*******                           1         660     660.00
```

### 3. User Detail

Shows detailed per-model usage for a specific user.

**Usage:**
```bash
./query user "fie_dave%"
# or
python3 db_queries.py user-detail "fie_dave%"
# or
sqlite3 -header -column $DB "SELECT * FROM v_user_detail WHERE subkey LIKE 'fie_dave%';"
```

**Output:**
```
=== User: David Connett ===
Email: dconnett@cisco.com
Description: Lead Developer

Model        Requests  Prompt  Completion  Total  Avg/Req
-----------  --------  ------  ----------  -----  -------
gpt-4o-mini  2         120     41          161    80.50
gpt-5        1         585     89          674    674.00

Totals: 3 requests, 835 tokens
```

### 4. Model Usage

Shows statistics for each model across all users.

**Usage:**
```bash
./query models
# or
python3 db_queries.py model-usage
# or
sqlite3 -header -column $DB "SELECT * FROM v_model_usage;"
```

**Output:**
```
=== Usage by Model ===

Model        Users  Requests  Tokens  Avg/Req
-----------  -----  --------  ------  -------
gpt-4o-mini  2      3         321     107.00
gpt-5        2      2         1334    667.00
```

### 5. Users Without Names

Shows users that need friendly names assigned.

**Usage:**
```bash
./query nonames
# or
python3 db_queries.py users-without-names
# or
sqlite3 -header -column $DB "SELECT * FROM v_users_without_names;"
```

**Output:**
```
=== Users Without Friendly Names ===

Subkey                                    Requests  Tokens
----------------------------------------  --------  ------
fie_tom_********************************  3         835

Found 1 user(s) without names.
Add names with:
  python3 add_subkey_names_table.py --add --subkey "KEY" --name "Name" --email "email@example.com"
```

### 6. Recent Activity

Shows most active users (by request count).

**Usage:**
```bash
./query recent 10
# or
python3 db_queries.py recent-activity --limit 10
```

### 7. User Models

Shows which models a specific user has used.

**Usage:**
```bash
python3 db_queries.py user-models "fie_dave%"
```

## Available SQL Views

After running `create_views.sql`, you have these views:

| View | Description |
|------|-------------|
| `v_user_summary` | Complete user info with totals and names |
| `v_top_users` | Pre-sorted by requests (just add LIMIT) |
| `v_model_usage` | Statistics per model |
| `v_users_without_names` | Users needing friendly names |
| `v_user_detail` | Per-model breakdown (use with WHERE) |
| `v_overall_stats` | Single-row database summary |

## Advanced Queries

### Find Heavy Users (>1000 tokens)

```bash
./query sql "SELECT * FROM v_top_users WHERE tokens > 1000 LIMIT 10;"
```

### Users of Specific Model

```bash
./query sql "SELECT DISTINCT user, email, requests, tokens 
FROM v_user_detail 
WHERE model = 'gpt-4o' 
ORDER BY requests DESC;"
```

### Top Users by Model

```bash
./query sql "WITH user_totals AS (
  SELECT subkey, SUM(requests) as total_req
  FROM usage
  GROUP BY subkey
  ORDER BY total_req DESC
  LIMIT 10
)
SELECT
  COALESCE(n.friendly_name, SUBSTR(u.subkey, 1, 30)) as user,
  u.model,
  u.requests,
  u.total_tokens
FROM usage u
JOIN user_totals ut ON u.subkey = ut.subkey
LEFT JOIN subkey_names n ON u.subkey = n.subkey
ORDER BY ut.total_req DESC, u.requests DESC;"
```

### Users by Email Domain

```bash
./query sql "SELECT 
  SUBSTR(email, INSTR(email, '@') + 1) as domain,
  COUNT(*) as users,
  SUM(total_requests) as requests
FROM v_user_summary
WHERE email IS NOT NULL
GROUP BY domain
ORDER BY users DESC;"
```

## Installation

### 1. Create the SQL Views (Optional but Recommended)

```bash
sudo sqlite3 /var/lib/oai-to-circuit/quota.db < create_views.sql
```

### 2. Make Scripts Executable

```bash
chmod +x db_queries.py query
```

### 3. Add to PATH (Optional)

```bash
# Add to ~/.bashrc or ~/.zshrc
export PATH="$PATH:/path/to/oai-to-circuit"

# Or create symlinks
sudo ln -s /path/to/oai-to-circuit/query /usr/local/bin/oai-query
```

## Environment Variables

Set these to avoid typing `--db` every time:

```bash
export QUOTA_DB_PATH="/var/lib/oai-to-circuit/quota.db"
```

## Integration with Reports

### Daily Email Report

```bash
#!/bin/bash
# /etc/cron.daily/oai-report

DB="/var/lib/oai-to-circuit/quota.db"
EMAIL="admin@example.com"

{
  echo "OAI-to-Circuit Daily Report"
  echo "==========================="
  echo ""
  python3 /path/to/db_queries.py summary --db "$DB"
  echo ""
  python3 /path/to/db_queries.py top-users --limit 20 --db "$DB"
  echo ""
  python3 /path/to/db_queries.py model-usage --db "$DB"
  echo ""
  python3 /path/to/db_queries.py users-without-names --db "$DB"
} | mail -s "OAI Daily Report" "$EMAIL"
```

### CSV Export

```bash
# Export top users to CSV
sqlite3 -header -csv /var/lib/oai-to-circuit/quota.db \
  "SELECT * FROM v_top_users LIMIT 100;" > top_users.csv
```

### JSON Export

```bash
# Export to JSON
sqlite3 /var/lib/oai-to-circuit/quota.db \
  "SELECT json_group_array(json_object(
    'user', user,
    'requests', requests,
    'tokens', tokens
  )) FROM v_top_users LIMIT 10;"
```

## Troubleshooting

### Permission Denied

```bash
# Run with sudo if needed
sudo ./query summary

# Or fix permissions
sudo chmod 644 /var/lib/oai-to-circuit/quota.db
sudo usermod -a -G oai-bridge $USER
```

### Views Don't Exist

```bash
# Create them
sudo sqlite3 /var/lib/oai-to-circuit/quota.db < create_views.sql

# Verify
./query views
```

### Python Script Not Found

```bash
# Use full path
python3 /path/to/oai-to-circuit/db_queries.py summary

# Or add to PATH
export PATH="$PATH:/path/to/oai-to-circuit"
```

## Performance

All queries are optimized:
- Views use LEFT JOIN for name lookups (fast)
- Indexes exist on primary keys
- GROUP BY uses indexed columns
- Python script reuses patterns from views

For large databases (>10K users), consider:
- Adding index on `usage.subkey`
- Using LIMIT in queries
- Running reports off-hours

## Files

- `db_queries.py` - Python query functions
- `create_views.sql` - SQL view definitions
- `query` - Shell wrapper for easy access
- `DATABASE_QUERIES.md` - This file

## See Also

- `add_subkey_names_table.py` - Manage friendly names
- `check_and_setup_names.py` - Check which users need names
- `generate_usage_report.py` - Full reporting tool
- `SUBKEY_NAMES_SETUP.md` - Setup guide

