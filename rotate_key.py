#!/usr/bin/env python3
"""
API Key Rotation Tool

Handles secure rotation of subkeys while preserving historical data and maintaining
reporting continuity.

Usage:
    # Revoke a key (keep historical data)
    python3 rotate_key.py --revoke OLD_KEY --reason "Key compromised"
    
    # Rotate a key (revoke old, generate new)
    python3 rotate_key.py --rotate OLD_KEY --prefix fie_alice --reason "Regular rotation"
    
    # Generate replacement manually
    python3 rotate_key.py --replace OLD_KEY NEW_KEY --reason "Team restructure"

Key Lifecycle States:
    - active: Key is currently in use (default)
    - revoked: Key disabled, but historical data preserved
    - replaced: Key disabled and replaced by another key
"""

import argparse
import json
import os
import secrets
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Tuple


def load_env_file():
    """Load environment variables from credentials.env if it exists."""
    env_paths = [
        '/etc/oai-to-circuit/credentials.env',
        'credentials.env',
        '/opt/oai-to-circuit/credentials.env',
    ]
    
    for env_path in env_paths:
        if os.path.exists(env_path):
            print(f"✓ Loading credentials from: {env_path}")
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        if key not in os.environ:
                            os.environ[key] = value
            return env_path
    
    return None


def generate_subkey(prefix: str) -> str:
    """Generate a secure subkey with the given prefix."""
    random_part = secrets.token_urlsafe(32)
    random_part = random_part.replace('-', '').replace('_', '')[:32]
    return f"{prefix}_{random_part}"


def get_quotas_path() -> str:
    """Find the quotas.json file."""
    paths = [
        '/etc/oai-to-circuit/quotas.json',
        'quotas.json',
        '/opt/oai-to-circuit/quotas.json'
    ]
    for path in paths:
        if os.path.exists(path):
            return path
    raise FileNotFoundError("Could not find quotas.json")


def get_db_path() -> str:
    """Find the quota.db file."""
    # Try environment variable first
    db_path = os.getenv('QUOTA_DB_PATH')
    if db_path and os.path.exists(db_path):
        return db_path
    
    # Try common locations
    possible_paths = [
        '/var/lib/oai-to-circuit/quota.db',
        '/opt/oai-to-circuit/quota.db',
        'quota.db',
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            return path
    
    # Default to /var/lib location (standard for systemd service)
    return '/var/lib/oai-to-circuit/quota.db'


def get_key_info(db_path: str, subkey: str) -> Optional[Dict]:
    """Get information about a key from the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get name info
    cursor.execute(
        "SELECT friendly_name, email, description, created_at FROM subkey_names WHERE subkey=?",
        (subkey,)
    )
    row = cursor.fetchone()
    
    if not row:
        conn.close()
        return None
    
    # Get usage stats
    cursor.execute(
        """SELECT SUM(requests), SUM(total_tokens) 
           FROM usage WHERE subkey=?""",
        (subkey,)
    )
    usage_row = cursor.fetchone()
    
    # Get rotation info if it exists
    cursor.execute(
        """SELECT status, revoked_at, revoke_reason, replaced_by, user_id 
           FROM key_lifecycle WHERE subkey=?""",
        (subkey,)
    )
    lifecycle_row = cursor.fetchone()
    
    conn.close()
    
    info = {
        'subkey': subkey,
        'friendly_name': row[0],
        'email': row[1],
        'description': row[2],
        'created_at': row[3],
        'total_requests': usage_row[0] if usage_row and usage_row[0] else 0,
        'total_tokens': usage_row[1] if usage_row and usage_row[1] else 0,
    }
    
    if lifecycle_row:
        info.update({
            'status': lifecycle_row[0],
            'revoked_at': lifecycle_row[1],
            'revoke_reason': lifecycle_row[2],
            'replaced_by': lifecycle_row[3],
            'user_id': lifecycle_row[4],
        })
    else:
        info['status'] = 'active'
    
    return info


def ensure_lifecycle_table(db_path: str):
    """Create key_lifecycle table if it doesn't exist."""
    # Ensure directory exists
    db_dir = os.path.dirname(db_path)
    if db_dir and not os.path.exists(db_dir):
        try:
            os.makedirs(db_dir, mode=0o755, exist_ok=True)
        except PermissionError:
            print(f"\n✗ ERROR: Cannot create directory {db_dir}")
            print(f"  Run with appropriate permissions or as root")
            raise
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
    except sqlite3.OperationalError as e:
        print(f"\n✗ ERROR: Cannot open database: {db_path}")
        print(f"  Error: {e}")
        print(f"\n  Possible solutions:")
        print(f"  1. Check file permissions: ls -l {db_path}")
        print(f"  2. Check directory permissions: ls -ld {db_dir}")
        print(f"  3. Run as appropriate user: sudo -u oai-bridge ...")
        print(f"  4. Set QUOTA_DB_PATH environment variable")
        raise
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS key_lifecycle (
            subkey TEXT PRIMARY KEY,
            user_id TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            revoked_at TIMESTAMP,
            revoke_reason TEXT,
            replaced_by TEXT,
            replaces TEXT,
            FOREIGN KEY (replaced_by) REFERENCES key_lifecycle(subkey),
            FOREIGN KEY (replaces) REFERENCES key_lifecycle(subkey)
        )
    """)
    
    # Create index for faster lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_id 
        ON key_lifecycle(user_id)
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_status 
        ON key_lifecycle(status)
    """)
    
    conn.commit()
    conn.close()


def revoke_key(db_path: str, quotas_path: str, subkey: str, reason: str, replaced_by: Optional[str] = None) -> bool:
    """Revoke a key (soft delete - preserves historical data)."""
    
    # Get key info
    info = get_key_info(db_path, subkey)
    if not info:
        print(f"✗ ERROR: Key not found in database: {subkey}")
        return False
    
    if info['status'] != 'active':
        print(f"✗ ERROR: Key is already {info['status']}")
        return False
    
    # Update key_lifecycle table
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    status = 'replaced' if replaced_by else 'revoked'
    
    # Get or create user_id
    user_id = info.get('user_id')
    if not user_id:
        # Use email or friendly_name as user_id
        user_id = info['email'] or info['friendly_name']
    
    cursor.execute("""
        INSERT OR REPLACE INTO key_lifecycle 
        (subkey, user_id, status, revoked_at, revoke_reason, replaced_by)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        subkey,
        user_id,
        status,
        datetime.now(timezone.utc).isoformat(),
        reason,
        replaced_by,
    ))
    
    conn.commit()
    conn.close()
    
    # Remove from quotas.json (or set to zero)
    with open(quotas_path, 'r') as f:
        quotas = json.load(f)
    
    if subkey in quotas:
        # Set all quotas to 0 instead of deleting (preserves structure)
        for model in quotas[subkey]:
            quotas[subkey][model] = {"requests": 0, "total_tokens": 0}
        
        # Add a comment about revocation
        quotas[f"_REVOKED_{subkey}"] = {
            "revoked_at": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
        }
        
        with open(quotas_path, 'w') as f:
            json.dump(quotas, f, indent=2)
        
        print(f"✓ Set quotas to 0 for revoked key in {quotas_path}")
    
    return True


def activate_key(db_path: str, subkey: str, replaces: Optional[str] = None, user_id: Optional[str] = None) -> bool:
    """Mark a key as active in the lifecycle table."""
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # If replacing another key, get its user_id
    if replaces and not user_id:
        cursor.execute("SELECT user_id FROM key_lifecycle WHERE subkey=?", (replaces,))
        row = cursor.fetchone()
        if row:
            user_id = row[0]
    
    # If still no user_id, try to get from subkey_names
    if not user_id:
        cursor.execute("SELECT email, friendly_name FROM subkey_names WHERE subkey=?", (subkey,))
        row = cursor.fetchone()
        if row:
            user_id = row[0] or row[1]
    
    cursor.execute("""
        INSERT OR REPLACE INTO key_lifecycle 
        (subkey, user_id, status, replaces)
        VALUES (?, ?, 'active', ?)
    """, (subkey, user_id, replaces))
    
    conn.commit()
    conn.close()
    
    return True


def main():
    parser = argparse.ArgumentParser(
        description='API Key Rotation Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Revoke a compromised key
  %(prog)s --revoke fie_alice_old123 --reason "Key compromised"
  
  # Rotate a key (revoke old, generate new)
  %(prog)s --rotate fie_alice_old123 --prefix fie_alice --reason "Regular rotation"
  
  # Replace with a specific new key
  %(prog)s --replace fie_alice_old123 fie_alice_new456 --reason "Manual replacement"
  
  # Show key status
  %(prog)s --status fie_alice_old123
        """
    )
    
    parser.add_argument('--revoke', metavar='SUBKEY', 
                        help='Revoke a key (preserves historical data)')
    parser.add_argument('--rotate', metavar='SUBKEY',
                        help='Rotate a key (revoke old, generate new)')
    parser.add_argument('--replace', nargs=2, metavar=('OLD_KEY', 'NEW_KEY'),
                        help='Replace old key with specific new key')
    parser.add_argument('--status', metavar='SUBKEY',
                        help='Show status of a key')
    parser.add_argument('--prefix', 
                        help='Prefix for new key (required with --rotate)')
    parser.add_argument('--reason', required=False,
                        help='Reason for rotation/revocation')
    parser.add_argument('--yes', action='store_true',
                        help='Skip confirmation prompts')
    
    args = parser.parse_args()
    
    print("="*80)
    print("API KEY ROTATION TOOL")
    print("="*80)
    
    # Load environment
    load_env_file()
    
    try:
        quotas_path = get_quotas_path()
        db_path = get_db_path()
        print(f"✓ Quotas file: {quotas_path}")
        print(f"✓ Database: {db_path}")
    except FileNotFoundError as e:
        print(f"\n✗ ERROR: {e}")
        return 1
    
    # Ensure lifecycle table exists
    ensure_lifecycle_table(db_path)
    
    # Handle --status
    if args.status:
        info = get_key_info(db_path, args.status)
        if not info:
            print(f"\n✗ Key not found: {args.status}")
            return 1
        
        print(f"\nKey Information:")
        print("-"*80)
        print(f"Subkey:        {info['subkey']}")
        print(f"Name:          {info['friendly_name']}")
        print(f"Email:         {info.get('email', 'N/A')}")
        print(f"Status:        {info['status'].upper()}")
        print(f"Created:       {info.get('created_at', 'Unknown')}")
        print(f"Total Usage:   {info['total_requests']} requests, {info['total_tokens']:,} tokens")
        
        if info['status'] != 'active':
            print(f"\nRevocation Details:")
            print(f"  Revoked At:  {info.get('revoked_at', 'N/A')}")
            print(f"  Reason:      {info.get('revoke_reason', 'N/A')}")
            if info.get('replaced_by'):
                print(f"  Replaced By: {info['replaced_by']}")
        
        return 0
    
    # Handle --revoke
    if args.revoke:
        if not args.reason:
            print("\n✗ ERROR: --reason is required when revoking a key")
            return 1
        
        info = get_key_info(db_path, args.revoke)
        if not info:
            print(f"\n✗ ERROR: Key not found: {args.revoke}")
            return 1
        
        print(f"\nRevoking Key:")
        print("-"*80)
        print(f"Subkey: {args.revoke}")
        print(f"Name:   {info['friendly_name']} <{info.get('email', 'N/A')}>")
        print(f"Usage:  {info['total_requests']} requests, {info['total_tokens']:,} tokens")
        print(f"Reason: {args.reason}")
        print("\n⚠️  Historical data will be preserved for reporting")
        print("⚠️  This key will immediately stop working")
        
        if not args.yes:
            response = input("\nConfirm revocation? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return 0
        
        if revoke_key(db_path, quotas_path, args.revoke, args.reason):
            print(f"\n✓ Key successfully revoked: {args.revoke}")
            print(f"\nTo view historical data:")
            print(f"  python3 rotate_key.py --status {args.revoke}")
            return 0
        else:
            return 1
    
    # Handle --rotate
    if args.rotate:
        if not args.prefix:
            print("\n✗ ERROR: --prefix is required when rotating a key")
            return 1
        if not args.reason:
            print("\n✗ ERROR: --reason is required when rotating a key")
            return 1
        
        old_key = args.rotate
        info = get_key_info(db_path, old_key)
        if not info:
            print(f"\n✗ ERROR: Key not found: {old_key}")
            return 1
        
        # Generate new key
        new_key = generate_subkey(args.prefix)
        
        print(f"\nRotating Key:")
        print("-"*80)
        print(f"Old Key: {old_key}")
        print(f"  Name:  {info['friendly_name']} <{info.get('email', 'N/A')}>")
        print(f"  Usage: {info['total_requests']} requests, {info['total_tokens']:,} tokens")
        print(f"\nNew Key: {new_key}")
        print(f"  Prefix: {args.prefix}")
        print(f"\nReason: {args.reason}")
        
        if not args.yes:
            response = input("\nConfirm rotation? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return 0
        
        # Revoke old key
        if not revoke_key(db_path, quotas_path, old_key, args.reason, replaced_by=new_key):
            return 1
        
        # Add new key to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO subkey_names (subkey, friendly_name, email, description)
            VALUES (?, ?, ?, ?)
        """, (
            new_key,
            info['friendly_name'],
            info.get('email'),
            f"Replacement for {old_key[:20]}... ({args.reason})"
        ))
        conn.commit()
        conn.close()
        
        # Mark new key as active
        activate_key(db_path, new_key, replaces=old_key)
        
        # Add to quotas.json with same quotas as old key
        with open(quotas_path, 'r') as f:
            quotas = json.load(f)
        
        # Copy quotas from old key (before they were zeroed)
        # Note: This requires the quotas.json to still have the old config
        # In production, you might want to store the original quotas separately
        
        print(f"\n✓ Key rotation complete!")
        print(f"\n⚠️  IMPORTANT: Update your quotas.json to add the new key:")
        print(f"  {new_key}: {{ ... copy quotas from old key ... }}")
        print(f"\n⚠️  Distribute the new key to the user:")
        print(f"  New Key: {new_key}")
        print(f"\n✓ Old key revoked and historical data preserved")
        
        return 0
    
    # Handle --replace
    if args.replace:
        old_key, new_key = args.replace
        if not args.reason:
            print("\n✗ ERROR: --reason is required when replacing a key")
            return 1
        
        old_info = get_key_info(db_path, old_key)
        if not old_info:
            print(f"\n✗ ERROR: Old key not found: {old_key}")
            return 1
        
        new_info = get_key_info(db_path, new_key)
        if not new_info:
            print(f"\n✗ ERROR: New key not found in database. Add it first with provision_user.py")
            return 1
        
        print(f"\nReplacing Key:")
        print("-"*80)
        print(f"Old: {old_key}")
        print(f"     {old_info['friendly_name']} <{old_info.get('email', 'N/A')}>")
        print(f"New: {new_key}")
        print(f"     {new_info['friendly_name']} <{new_info.get('email', 'N/A')}>")
        print(f"\nReason: {args.reason}")
        
        if not args.yes:
            response = input("\nConfirm replacement? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted.")
                return 0
        
        if revoke_key(db_path, quotas_path, old_key, args.reason, replaced_by=new_key):
            activate_key(db_path, new_key, replaces=old_key)
            print(f"\n✓ Key replacement complete!")
            return 0
        else:
            return 1
    
    # No action specified
    print("\n✗ ERROR: Must specify one of: --revoke, --rotate, --replace, or --status")
    print("Run with --help for usage examples")
    return 1


if __name__ == "__main__":
    sys.exit(main())

