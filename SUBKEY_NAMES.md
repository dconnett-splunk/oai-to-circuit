# Subkey Name Mapping Guide

## Overview

The subkey name mapping system allows you to:
- **Generate reports with human-readable names** instead of raw subkeys
- **Keep actual subkeys private** in reports and logs
- **Track who is associated with each key** without exposing the key itself

This is useful for:
- Creating usage reports for management
- Sharing statistics without revealing sensitive keys
- Tracking team/individual usage by name

## Quick Start

### 1. Initialize the Names Table (One-Time Setup)

```bash
# On your server
cd /opt/oai-to-circuit
python3 add_subkey_names_table.py --init
```

### 2. Add Name Mappings

```bash
# Map the FIE Dave subkey to a friendly name
python3 add_subkey_names_table.py --add \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave (FIE Team)" \
  --description "Field Innovation Engineering"

# Add more mappings
python3 add_subkey_names_table.py --add \
  --subkey "team_alpha_kL9pX2mN7vR4tQ8wY1zJ5hF3" \
  --name "Team Alpha" \
  --description "Development Team"

python3 add_subkey_names_table.py --add \
  --subkey "alice_xK9mP2nR7vL4tQ8wY1zN5jH3" \
  --name "Alice Johnson" \
  --description "Senior Engineer"
```

### 3. Generate Reports

```bash
# Summary report (shows totals by name)
python3 generate_usage_report.py --summary

# Detailed report (shows per-model usage)
python3 generate_usage_report.py --detailed

# Usage by model
python3 generate_usage_report.py --by-model

# All reports
python3 generate_usage_report.py --all

# Export to CSV
python3 generate_usage_report.py --detailed --csv monthly_report.csv
```

## Database Schema

The `subkey_names` table stores the mappings:

```sql
CREATE TABLE subkey_names (
    subkey TEXT PRIMARY KEY,
    friendly_name TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Managing Mappings

### List All Mappings

```bash
python3 add_subkey_names_table.py --list
```

Output:
```
Friendly Name                  Subkey Prefix             Description                    Created
========================================================================================================================
Alice Johnson                  alice_xK9mP2nR7vL4t...    Senior Engineer                2024-01-15 10:30:00
Dave (FIE Team)                fie_dave_jhKaCh88Cg...    Field Innovation Engineering   2024-01-15 11:00:00
Team Alpha                     team_alpha_kL9pX2mN...    Development Team               2024-01-15 09:45:00
```

### Update a Mapping

To update, just run `--add` again with the same subkey:

```bash
python3 add_subkey_names_table.py --add \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \
  --name "Dave Smith (FIE)" \
  --description "Field Innovation Engineering - Senior"
```

### Remove a Mapping

```bash
python3 add_subkey_names_table.py --remove \
  --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g"
```

## Report Examples

### Summary Report

```
==================================================================================
                     OpenAI Bridge Usage Report - Summary
                       Generated: 2024-01-15 14:30:00
==================================================================================

User/Team                      Total Requests   Total Tokens   Models Used   Description
--------------------------------------------------------------------------------------------------
Dave (FIE Team)                           450        125,430             2   Field Innovation...
Team Alpha                                320         89,120             3   Development Team
Alice Johnson                             180         45,200             1   Senior Engineer
--------------------------------------------------------------------------------------------------
TOTAL                                     950        259,750
```

### Detailed Report

```
====================================================================================================================
                              OpenAI Bridge Usage Report - Detailed
                                Generated: 2024-01-15 14:30:00
====================================================================================================================

User/Team                      Model                Requests      Tokens   Description
--------------------------------------------------------------------------------------------------------------------
Dave (FIE Team)                gpt-4o-mini               420     115,200   Field Innovation...
Dave (FIE Team)                gpt-4o                     30      10,230   Field Innovation...
Team Alpha                     gpt-4o-mini               280      75,000   Development Team
Team Alpha                     gpt-4o                     35      12,120   Development Team
Team Alpha                     claude-3.5-sonnet           5       2,000   Development Team
Alice Johnson                  gpt-4o-mini               180      45,200   Senior Engineer
```

### Model Usage Report

```
================================================================================
                             Usage by Model
================================================================================

Model                      Total Requests    Total Tokens   Unique Users
--------------------------------------------------------------------------------
gpt-4o-mini                           880         235,400              3
gpt-4o                                 65          22,350              2
claude-3.5-sonnet                       5           2,000              1
```

## Export to CSV

Generate a CSV file for Excel/spreadsheets:

```bash
python3 generate_usage_report.py --detailed --csv monthly_usage.csv
```

Output `monthly_usage.csv`:
```csv
User/Team,Model,Requests,Prompt Tokens,Completion Tokens,Total Tokens,Description
Dave (FIE Team),gpt-4o-mini,420,65200,50000,115200,Field Innovation Engineering
Dave (FIE Team),gpt-4o,30,5800,4430,10230,Field Innovation Engineering
Team Alpha,gpt-4o-mini,280,42000,33000,75000,Development Team
...
```

## Integration with Deployment

### Add to Your Deployment Workflow

1. **After generating a new subkey**, immediately add a name mapping:

```bash
# Generate key
SUBKEY=$(python3 generate_subkeys.py --prefix "new_user" | head -1)

# Add mapping
python3 add_subkey_names_table.py --add \
  --subkey "$SUBKEY" \
  --name "New User Name" \
  --description "Department/Role"
```

2. **Before revoking a subkey**, you can keep the mapping for historical reports:
   - The mapping will remain in `subkey_names` even after the key is removed from `quotas.json`
   - Historical reports will still show the friendly name

### Bulk Import Mappings

Create a script to import multiple mappings:

```bash
#!/bin/bash

# Import mappings from a CSV file
# Format: subkey,name,description

while IFS=',' read -r subkey name description; do
    python3 add_subkey_names_table.py --add \
      --subkey "$subkey" \
      --name "$name" \
      --description "$description"
done < mappings.csv
```

## Security Considerations

### What's Protected
- ✅ **Subkeys are never shown in reports** (only friendly names)
- ✅ **Mappings are stored only on the server** (not in git)
- ✅ **Database permissions** protect the mappings (readable only by root/oai-bridge)

### What to Remember
- ⚠️ **The database still contains raw subkeys** in the `usage` table
- ⚠️ **Anyone with DB access can see the mappings**
- ⚠️ **Use proper file permissions** on quota.db (should be 640, owned by oai-bridge)

### Best Practices
1. **Don't commit mappings to git** - they're server-side only
2. **Restrict DB access** - only root and oai-bridge user
3. **Use descriptive names** that don't reveal sensitive info
4. **Regular audits** - verify mappings are up-to-date

## Troubleshooting

### "No such table: subkey_names"

Run the initialization:
```bash
python3 add_subkey_names_table.py --init
```

### "Database is locked"

The service might be writing to it. Stop briefly:
```bash
sudo systemctl stop oai-to-circuit
python3 add_subkey_names_table.py --add ...
sudo systemctl start oai-to-circuit
```

### Reports show raw subkeys instead of names

You haven't added a mapping for that subkey yet:
```bash
python3 add_subkey_names_table.py --list  # Check existing mappings
python3 add_subkey_names_table.py --add --subkey "..." --name "..."
```

## Automation

### Cron Job for Weekly Reports

```bash
# Add to crontab (crontab -e)
0 9 * * 1 /opt/oai-to-circuit/generate_usage_report.py --all > /tmp/weekly_report.txt && mail -s "Weekly API Usage Report" admin@example.com < /tmp/weekly_report.txt
```

### Monthly CSV Export

```bash
# First day of each month at 8 AM
0 8 1 * * /opt/oai-to-circuit/generate_usage_report.py --detailed --csv /backup/usage-$(date +\%Y-\%m).csv
```

## Example Complete Workflow

```bash
# 1. Generate key for new user
SUBKEY=$(python3 generate_subkeys.py --prefix "john" | head -1)
echo "Generated subkey: $SUBKEY"

# 2. Add to quotas
# (edit quotas.json, add the key with limits)

# 3. Add name mapping
python3 add_subkey_names_table.py --add \
  --subkey "$SUBKEY" \
  --name "John Doe" \
  --description "Marketing Team"

# 4. Share key with user
# (send securely)

# 5. Generate report after usage
python3 generate_usage_report.py --summary

# Output shows "John Doe" instead of raw key!
```

That's it! Your reports now use friendly names while keeping subkeys private.

