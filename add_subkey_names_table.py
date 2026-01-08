#!/usr/bin/env python3
"""
Add a subkey_names table to the quota database for friendly name mapping.

This allows you to:
- Generate reports with human-readable names
- Keep actual subkeys private
- Track which person/team is associated with each key
"""

import argparse
import sqlite3
import sys


def add_names_table(db_path: str) -> None:
    """Add the subkey_names table to the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subkey_names (
            subkey TEXT PRIMARY KEY,
            friendly_name TEXT NOT NULL,
            email TEXT,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create index on friendly_name for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_friendly_name 
        ON subkey_names(friendly_name)
    """)
    
    conn.commit()
    conn.close()
    
    print(f"✓ Created subkey_names table in {db_path}")


def add_name_mapping(db_path: str, subkey: str, friendly_name: str, email: str = "", description: str = "") -> None:
    """Add or update a name mapping for a subkey."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO subkey_names (subkey, friendly_name, email, description)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(subkey) DO UPDATE SET
            friendly_name = excluded.friendly_name,
            email = excluded.email,
            description = excluded.description,
            updated_at = CURRENT_TIMESTAMP
    """, (subkey, friendly_name, email, description))
    
    conn.commit()
    conn.close()
    
    email_display = f" <{email}>" if email else ""
    print(f"✓ Mapped '{subkey[:20]}...' → '{friendly_name}'{email_display}")


def list_mappings(db_path: str) -> None:
    """List all name mappings."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT friendly_name, email, subkey, description, created_at
        FROM subkey_names
        ORDER BY friendly_name
    """)
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("No name mappings found.")
        return
    
    print(f"\n{'Friendly Name':<25} {'Email':<30} {'Subkey Prefix':<25} {'Description':<25}")
    print("=" * 120)
    
    for name, email, subkey, desc, created in rows:
        email_display = (email[:27] + "...") if email and len(email) > 30 else (email or "")
        subkey_prefix = subkey[:22] + "..." if len(subkey) > 25 else subkey
        desc_short = (desc[:22] + "...") if desc and len(desc) > 25 else (desc or "")
        print(f"{name:<25} {email_display:<30} {subkey_prefix:<25} {desc_short:<25}")


def remove_mapping(db_path: str, subkey: str) -> None:
    """Remove a name mapping."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM subkey_names WHERE subkey = ?", (subkey,))
    
    if cursor.rowcount == 0:
        print(f"✗ No mapping found for subkey: {subkey}")
    else:
        print(f"✓ Removed mapping for subkey: {subkey[:20]}...")
    
    conn.commit()
    conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Manage friendly name mappings for subkeys",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create the table (run once on setup)
  python add_subkey_names_table.py --init

  # Add a name mapping
  python add_subkey_names_table.py --add \\
    --subkey "fie_dave_jhKaCh88CgkSfl_p7RN01jv82dkOL90g" \\
    --name "Dave (FIE Team)" \\
    --email "dave@example.com" \\
    --description "Field Innovation Engineering"

  # List all mappings
  python add_subkey_names_table.py --list

  # Remove a mapping
  python add_subkey_names_table.py --remove --subkey "fie_dave_..."
        """
    )
    
    parser.add_argument(
        "--db",
        default="/var/lib/oai-to-circuit/quota.db",
        help="Path to quota database (default: /var/lib/oai-to-circuit/quota.db)"
    )
    
    # Actions
    action_group = parser.add_mutually_exclusive_group(required=True)
    action_group.add_argument("--init", action="store_true", help="Initialize the names table")
    action_group.add_argument("--add", action="store_true", help="Add a name mapping")
    action_group.add_argument("--list", action="store_true", help="List all mappings")
    action_group.add_argument("--remove", action="store_true", help="Remove a mapping")
    
    # Arguments for --add
    parser.add_argument("--subkey", help="Subkey to map")
    parser.add_argument("--name", help="Friendly name")
    parser.add_argument("--email", default="", help="Optional email address")
    parser.add_argument("--description", default="", help="Optional description")
    
    args = parser.parse_args()
    
    try:
        if args.init:
            add_names_table(args.db)
        
        elif args.add:
            if not args.subkey or not args.name:
                print("Error: --add requires --subkey and --name", file=sys.stderr)
                sys.exit(1)
            add_name_mapping(args.db, args.subkey, args.name, args.email, args.description)
        
        elif args.list:
            list_mappings(args.db)
        
        elif args.remove:
            if not args.subkey:
                print("Error: --remove requires --subkey", file=sys.stderr)
                sys.exit(1)
            remove_mapping(args.db, args.subkey)
    
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

