#!/usr/bin/env python3
"""
Script to check current state of database and help set up friendly names for active keys.

This script:
1. Checks if the subkey_names table exists
2. Lists all active subkeys from the usage table
3. Shows which ones have names and which ones don't
4. Provides commands to add names to keys without them
"""

import argparse
import sqlite3
import sys
from typing import List, Tuple


def check_table_exists(db_path: str, table_name: str) -> bool:
    """Check if a table exists in the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' AND name=?
    """, (table_name,))
    
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def get_active_subkeys(db_path: str) -> List[Tuple[str, int, int]]:
    """Get all subkeys that have usage data."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT 
            subkey,
            SUM(requests) as total_requests,
            SUM(total_tokens) as total_tokens
        FROM usage
        GROUP BY subkey
        ORDER BY total_requests DESC
    """)
    
    rows = cursor.fetchall()
    conn.close()
    return rows


def get_subkey_name(db_path: str, subkey: str) -> Tuple[str, str, str]:
    """Get friendly name, email, and description for a subkey, if it exists."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT friendly_name, email, description
        FROM subkey_names
        WHERE subkey = ?
    """, (subkey,))
    
    row = cursor.fetchone()
    conn.close()
    
    if row:
        return row[0], row[1], row[2]
    return None, None, None


def main():
    parser = argparse.ArgumentParser(
        description="Check database state and list active subkeys",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument(
        "--db",
        default="/var/lib/oai-to-circuit/quota.db",
        help="Path to quota database (default: /var/lib/oai-to-circuit/quota.db)"
    )
    
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local quota.db instead of system path"
    )
    
    args = parser.parse_args()
    
    if args.local:
        db_path = "quota.db"
    else:
        db_path = args.db
    
    try:
        # Check if database exists
        try:
            conn = sqlite3.connect(db_path)
            conn.close()
            print(f"✓ Database found: {db_path}\n")
        except sqlite3.Error as e:
            print(f"✗ Cannot access database at {db_path}: {e}", file=sys.stderr)
            sys.exit(1)
        
        # Check if subkey_names table exists
        has_names_table = check_table_exists(db_path, "subkey_names")
        
        if has_names_table:
            print("✓ subkey_names table exists\n")
        else:
            print("✗ subkey_names table does NOT exist")
            print("  Run this command to create it:")
            print(f"  python add_subkey_names_table.py --init --db {db_path}\n")
            
            # Still continue to show active keys
        
        # Get all active subkeys
        active_keys = get_active_subkeys(db_path)
        
        if not active_keys:
            print("No active subkeys found in usage table.")
            return
        
        print(f"Found {len(active_keys)} active subkey(s):\n")
        print("=" * 140)
        print(f"{'Status':<8} {'Subkey':<35} {'Name':<20} {'Email':<30} {'Requests':<12} {'Tokens'}")
        print("=" * 140)
        
        unnamed_keys = []
        
        for subkey, requests, tokens in active_keys:
            # Get name if exists
            if has_names_table:
                name, email, description = get_subkey_name(db_path, subkey)
            else:
                name, email, description = None, None, None
            
            if name:
                status = "✓ NAMED"
                name_display = name[:19] if len(name) > 20 else name
                email_display = (email[:27] + "...") if email and len(email) > 30 else (email or "")
            else:
                status = "✗ NO NAME"
                name_display = "(unnamed)"
                email_display = ""
                unnamed_keys.append(subkey)
            
            # Truncate subkey for display
            subkey_display = subkey if len(subkey) <= 34 else subkey[:31] + "..."
            
            print(f"{status:<8} {subkey_display:<35} {name_display:<20} {email_display:<30} {requests:<12} {tokens:,}")
        
        print("=" * 120)
        print()
        
        # Provide commands to add names
        if unnamed_keys:
            print(f"\n⚠️  Found {len(unnamed_keys)} subkey(s) without names!\n")
            print("To add names, use these commands:\n")
            
            for subkey in unnamed_keys:
                print(f"python add_subkey_names_table.py --add \\")
                print(f"  --db {db_path} \\")
                print(f"  --subkey \"{subkey}\" \\")
                print(f"  --name \"YOUR_NAME_HERE\" \\")
                print(f"  --email \"your.email@example.com\" \\")
                print(f"  --description \"Optional description\"\n")
        else:
            print("✓ All active subkeys have friendly names assigned!")
        
        # Summary
        print("\n" + "=" * 140)
        print("SUMMARY:")
        print(f"  Total active keys: {len(active_keys)}")
        if has_names_table:
            print(f"  Keys with names:   {len(active_keys) - len(unnamed_keys)}")
            print(f"  Keys without names: {len(unnamed_keys)}")
        else:
            print(f"  Names table:       NOT CREATED (run --init first)")
        print("=" * 140)
    
    except sqlite3.Error as e:
        print(f"Database error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

