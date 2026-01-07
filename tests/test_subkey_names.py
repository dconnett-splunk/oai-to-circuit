"""Tests for subkey name mapping functionality."""

import tempfile
import sqlite3
from pathlib import Path


def test_names_table_creation():
    """Test that the names table can be created."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table
        
        add_names_table(tf.name)
        
        # Verify table exists
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='subkey_names'
        """)
        assert cursor.fetchone() is not None
        conn.close()


def test_add_name_mapping():
    """Test adding a name mapping."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table, add_name_mapping
        
        add_names_table(tf.name)
        add_name_mapping(tf.name, "test_key_123", "Test User", "Test description")
        
        # Verify mapping was added
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT friendly_name, description 
            FROM subkey_names 
            WHERE subkey='test_key_123'
        """)
        row = cursor.fetchone()
        conn.close()
        
        assert row is not None
        assert row[0] == "Test User"
        assert row[1] == "Test description"


def test_update_name_mapping():
    """Test updating an existing name mapping."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table, add_name_mapping
        
        add_names_table(tf.name)
        add_name_mapping(tf.name, "test_key_123", "Original Name", "Original desc")
        add_name_mapping(tf.name, "test_key_123", "Updated Name", "Updated desc")
        
        # Verify mapping was updated
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT friendly_name, description 
            FROM subkey_names 
            WHERE subkey='test_key_123'
        """)
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == "Updated Name"
        assert row[1] == "Updated desc"


def test_remove_name_mapping():
    """Test removing a name mapping."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table, add_name_mapping, remove_mapping
        
        add_names_table(tf.name)
        add_name_mapping(tf.name, "test_key_123", "Test User", "Test")
        remove_mapping(tf.name, "test_key_123")
        
        # Verify mapping was removed
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM subkey_names WHERE subkey='test_key_123'")
        row = cursor.fetchone()
        conn.close()
        
        assert row is None


def test_report_with_names():
    """Test that reports show friendly names."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table, add_name_mapping
        from oai_to_circuit.quota import QuotaManager
        
        # Setup
        add_names_table(tf.name)
        add_name_mapping(tf.name, "user1_key", "Alice", "Team A")
        
        # Add usage data
        quotas = {"user1_key": {"gpt-4o-mini": {"requests": 100}}}
        qm = QuotaManager(db_path=tf.name, quotas=quotas)
        qm.record_usage("user1_key", "gpt-4o-mini", request_inc=5, total_tokens=1000)
        
        # Verify we can query with names
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(n.friendly_name, u.subkey) as name,
                u.requests,
                u.total_tokens
            FROM usage u
            LEFT JOIN subkey_names n ON u.subkey = n.subkey
        """)
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == "Alice"  # Shows name, not raw key
        assert row[1] == 5
        assert row[2] == 1000


def test_report_without_name_falls_back_to_subkey():
    """Test that reports fall back to subkey if no name mapping exists."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        from add_subkey_names_table import add_names_table
        from oai_to_circuit.quota import QuotaManager
        
        # Setup without adding name mapping
        add_names_table(tf.name)
        
        quotas = {"user2_key": {"gpt-4o-mini": {"requests": 100}}}
        qm = QuotaManager(db_path=tf.name, quotas=quotas)
        qm.record_usage("user2_key", "gpt-4o-mini", request_inc=3, total_tokens=500)
        
        # Verify fallback to raw subkey
        conn = sqlite3.connect(tf.name)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                COALESCE(n.friendly_name, u.subkey) as name
            FROM usage u
            LEFT JOIN subkey_names n ON u.subkey = n.subkey
        """)
        row = cursor.fetchone()
        conn.close()
        
        assert row[0] == "user2_key"  # Shows raw key when no mapping

