#!/usr/bin/env python3
"""
Database query utilities - SQLite "stored procedures" equivalent.

Provides common queries as Python functions that can be called directly
or used as a library.

Usage:
    python3 db_queries.py top-users
    python3 db_queries.py user-detail fie_dave_*****
    python3 db_queries.py model-usage
"""

import argparse
import sqlite3
import sys
from typing import List, Tuple, Optional


class QuotaQueries:
    """Common queries for the quota database."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def _connect(self):
        """Get a database connection."""
        return sqlite3.connect(self.db_path)
    
    def _format_table(self, headers: List[str], rows: List[Tuple], col_widths: Optional[List[int]] = None):
        """Format results as a pretty table."""
        if not rows:
            print("No results found.")
            return
        
        # Auto-calculate column widths if not provided
        if col_widths is None:
            col_widths = [len(h) for h in headers]
            for row in rows:
                for i, val in enumerate(row):
                    col_widths[i] = max(col_widths[i], len(str(val)))
        
        # Print header
        header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
        print(header_line)
        print("-" * len(header_line))
        
        # Print rows
        for row in rows:
            print("  ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row)))
    
    def top_users(self, limit: int = 10, show_names: bool = True):
        """
        Show top users by total requests.
        
        Args:
            limit: Number of users to show
            show_names: Include friendly names if available
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        if show_names:
            query = """
                SELECT
                    COALESCE(n.friendly_name, SUBSTR(u.subkey, 1, 30)) as user,
                    COALESCE(n.email, '') as email,
                    SUM(u.requests) as total_requests,
                    SUM(u.total_tokens) as total_tokens,
                    ROUND(CAST(SUM(u.total_tokens) AS FLOAT) / SUM(u.requests), 2) as avg_tokens
                FROM usage u
                LEFT JOIN subkey_names n ON u.subkey = n.subkey
                GROUP BY u.subkey
                ORDER BY total_requests DESC
                LIMIT ?
            """
            headers = ["User", "Email", "Requests", "Tokens", "Avg/Req"]
        else:
            query = """
                SELECT
                    SUBSTR(subkey, 1, 30) as user,
                    SUM(requests) as total_requests,
                    SUM(total_tokens) as total_tokens,
                    ROUND(CAST(SUM(total_tokens) AS FLOAT) / SUM(requests), 2) as avg_tokens
                FROM usage
                GROUP BY subkey
                ORDER BY total_requests DESC
                LIMIT ?
            """
            headers = ["User", "Requests", "Tokens", "Avg/Req"]
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        print(f"\n=== Top {limit} Users by Requests ===\n")
        self._format_table(headers, rows)
    
    def user_detail(self, subkey_pattern: str, show_name: bool = True):
        """
        Show detailed usage for a specific user.
        
        Args:
            subkey_pattern: Subkey or pattern (use % for wildcard)
            show_name: Include friendly name if available
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        # First get user info
        if show_name:
            cursor.execute("""
                SELECT friendly_name, email, description
                FROM subkey_names
                WHERE subkey LIKE ?
            """, (subkey_pattern,))
            name_info = cursor.fetchone()
            if name_info:
                print(f"\n=== User: {name_info[0]} ===")
                if name_info[1]:
                    print(f"Email: {name_info[1]}")
                if name_info[2]:
                    print(f"Description: {name_info[2]}")
                print()
        
        # Get usage by model
        query = """
            SELECT
                model,
                requests,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                ROUND(CAST(total_tokens AS FLOAT) / requests, 2) as avg_tokens
            FROM usage
            WHERE subkey LIKE ?
            ORDER BY requests DESC
        """
        
        cursor.execute(query, (subkey_pattern,))
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            print(f"No usage found for pattern: {subkey_pattern}")
            return
        
        headers = ["Model", "Requests", "Prompt", "Completion", "Total", "Avg/Req"]
        self._format_table(headers, rows)
        
        # Print totals
        total_requests = sum(r[1] for r in rows)
        total_tokens = sum(r[4] for r in rows)
        print(f"\nTotals: {total_requests:,} requests, {total_tokens:,} tokens")
    
    def model_usage(self):
        """Show usage statistics by model."""
        conn = self._connect()
        cursor = conn.cursor()
        
        query = """
            SELECT
                model,
                COUNT(DISTINCT subkey) as unique_users,
                SUM(requests) as total_requests,
                SUM(total_tokens) as total_tokens,
                ROUND(CAST(SUM(total_tokens) AS FLOAT) / SUM(requests), 2) as avg_tokens
            FROM usage
            GROUP BY model
            ORDER BY total_requests DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        print("\n=== Usage by Model ===\n")
        headers = ["Model", "Users", "Requests", "Tokens", "Avg/Req"]
        self._format_table(headers, rows)
    
    def users_without_names(self):
        """Show users that don't have friendly names assigned."""
        conn = self._connect()
        cursor = conn.cursor()
        
        query = """
            SELECT
                SUBSTR(u.subkey, 1, 40) as subkey,
                SUM(u.requests) as requests,
                SUM(u.total_tokens) as tokens
            FROM usage u
            LEFT JOIN subkey_names n ON u.subkey = n.subkey
            WHERE n.subkey IS NULL
            GROUP BY u.subkey
            ORDER BY requests DESC
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        conn.close()
        
        print("\n=== Users Without Friendly Names ===\n")
        headers = ["Subkey", "Requests", "Tokens"]
        self._format_table(headers, rows)
        
        if rows:
            print(f"\nFound {len(rows)} user(s) without names.")
            print("Add names with:")
            print('  python3 add_subkey_names_table.py --add --subkey "KEY" --name "Name" --email "email@example.com"')
    
    def recent_activity(self, limit: int = 10):
        """
        Show recent activity (requires timestamp tracking).
        Note: Current schema doesn't track individual request timestamps.
        This shows overall activity by user.
        """
        conn = self._connect()
        cursor = conn.cursor()
        
        query = """
            SELECT
                COALESCE(n.friendly_name, SUBSTR(u.subkey, 1, 25)) as user,
                u.model,
                u.requests,
                u.total_tokens
            FROM usage u
            LEFT JOIN subkey_names n ON u.subkey = n.subkey
            ORDER BY u.requests DESC
            LIMIT ?
        """
        
        cursor.execute(query, (limit,))
        rows = cursor.fetchall()
        conn.close()
        
        print(f"\n=== Recent Activity (Top {limit} by usage) ===\n")
        headers = ["User", "Model", "Requests", "Tokens"]
        self._format_table(headers, rows)
    
    def user_models(self, subkey_pattern: str):
        """Show which models a user has access to."""
        conn = self._connect()
        cursor = conn.cursor()
        
        query = """
            SELECT DISTINCT
                model,
                requests,
                total_tokens
            FROM usage
            WHERE subkey LIKE ?
            ORDER BY requests DESC
        """
        
        cursor.execute(query, (subkey_pattern,))
        rows = cursor.fetchall()
        conn.close()
        
        print(f"\n=== Models Used by {subkey_pattern} ===\n")
        headers = ["Model", "Requests", "Tokens"]
        self._format_table(headers, rows)
    
    def summary(self):
        """Show overall database summary."""
        conn = self._connect()
        cursor = conn.cursor()
        
        # Total stats
        cursor.execute("""
            SELECT
                COUNT(DISTINCT subkey) as total_users,
                COUNT(DISTINCT model) as total_models,
                SUM(requests) as total_requests,
                SUM(total_tokens) as total_tokens
            FROM usage
        """)
        total_stats = cursor.fetchone()
        
        # Users with names
        cursor.execute("""
            SELECT COUNT(DISTINCT u.subkey)
            FROM usage u
            INNER JOIN subkey_names n ON u.subkey = n.subkey
        """)
        users_with_names = cursor.fetchone()[0]
        
        conn.close()
        
        print("\n=== Database Summary ===\n")
        print(f"Total Users:      {total_stats[0]:,}")
        print(f"Users with Names: {users_with_names:,} ({users_with_names * 100 // total_stats[0] if total_stats[0] > 0 else 0}%)")
        print(f"Total Models:     {total_stats[1]:,}")
        print(f"Total Requests:   {total_stats[2]:,}")
        print(f"Total Tokens:     {total_stats[3]:,}")
        print(f"Avg Tokens/Req:   {total_stats[3] // total_stats[2] if total_stats[2] > 0 else 0:,}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Query the quota database with common queries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Available queries:
  summary              Overall database summary
  top-users           Top users by request count
  user-detail PATTERN Detailed usage for a specific user
  model-usage         Usage statistics by model
  users-without-names Users that need friendly names
  recent-activity     Recent activity summary
  user-models PATTERN Models used by a specific user

Examples:
  python3 db_queries.py summary
  python3 db_queries.py top-users --limit 20
  python3 db_queries.py user-detail "fie_dave_%"
  python3 db_queries.py model-usage
  python3 db_queries.py users-without-names
        """
    )
    
    parser.add_argument(
        "query",
        choices=["summary", "top-users", "user-detail", "model-usage", 
                 "users-without-names", "recent-activity", "user-models"],
        help="Query to run"
    )
    
    parser.add_argument(
        "pattern",
        nargs="?",
        help="Pattern for user-detail or user-models queries"
    )
    
    parser.add_argument(
        "--db",
        default="/var/lib/oai-to-circuit/quota.db",
        help="Path to database (default: /var/lib/oai-to-circuit/quota.db)"
    )
    
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Limit for top-users query (default: 10)"
    )
    
    parser.add_argument(
        "--no-names",
        action="store_true",
        help="Don't show friendly names (show raw subkeys)"
    )
    
    args = parser.parse_args()
    
    # Validate pattern requirements
    if args.query in ["user-detail", "user-models"] and not args.pattern:
        print(f"Error: {args.query} requires a pattern argument", file=sys.stderr)
        sys.exit(1)
    
    # Create queries object
    queries = QuotaQueries(args.db)
    
    # Run the requested query
    try:
        if args.query == "summary":
            queries.summary()
        elif args.query == "top-users":
            queries.top_users(limit=args.limit, show_names=not args.no_names)
        elif args.query == "user-detail":
            queries.user_detail(args.pattern, show_name=not args.no_names)
        elif args.query == "model-usage":
            queries.model_usage()
        elif args.query == "users-without-names":
            queries.users_without_names()
        elif args.query == "recent-activity":
            queries.recent_activity(limit=args.limit)
        elif args.query == "user-models":
            queries.user_models(args.pattern)
    
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

